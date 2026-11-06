"""Generate draft Microsoft Fabric pipeline definitions from ADF pipelines.

Fabric pipelines have no separate dataset objects, so every dataset reference is
inlined into the activity as ``datasetSettings``, with the dataset's parameters
substituted. Linked services become ``{{CONNECTION:<name>}}`` placeholders that
can be filled with a connection-mapping file (``--connections``).
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from . import rules
from .loader import Factory

_WHOLE_PARAM = re.compile(r"^@dataset\(\)\.(\w+)$")
_INTERP_PARAM = re.compile(r"@\{dataset\(\)\.(\w+)\}")
_BARE_PARAM = re.compile(r"dataset\(\)\.(\w+)")

_DATASET_ACTIVITIES = {"Lookup", "GetMetadata", "Delete"}
_NESTED_LISTS = ("activities", "ifTrueActivities", "ifFalseActivities", "defaultActivities")


def connection_placeholder(linked_service: str) -> str:
    return "{{CONNECTION:%s}}" % linked_service


def _is_expr(v) -> bool:
    return isinstance(v, dict) and v.get("type") == "Expression" and "value" in v


def _expr_body(v) -> str:
    """Expression text without the leading '@' (used when embedding in a larger expression)."""
    s = v["value"]
    return s[1:] if s.startswith("@") else s


def substitute(node, params: dict):
    """Replace ``dataset().x`` references with the values the activity passes in."""
    if isinstance(node, list):
        return [substitute(n, params) for n in node]
    if _is_expr(node):
        return _substitute_expression(node["value"], params)
    if isinstance(node, dict):
        return {k: substitute(v, params) for k, v in node.items()}
    if isinstance(node, str) and "dataset()" in node:
        return _substitute_expression(node, params)
    return node


def _substitute_expression(text: str, params: dict):
    whole = _WHOLE_PARAM.match(text)
    if whole:
        value = params.get(whole.group(1))
        return copy.deepcopy(value) if value is not None else {"value": text, "type": "Expression"}

    dynamic = False

    def interp(m):
        nonlocal dynamic
        value = params.get(m.group(1))
        if value is None:
            dynamic = True
            return m.group(0)
        if _is_expr(value):
            dynamic = True
            return "@{%s}" % _expr_body(value)
        return str(value)

    out = _INTERP_PARAM.sub(interp, text)

    # A function-style expression such as "@concat(dataset().schema, '.', dataset().table)"
    if out.startswith("@") and not out.startswith("@{") and _BARE_PARAM.search(out):
        def bare(m):
            nonlocal dynamic
            value = params.get(m.group(1))
            if value is None:
                dynamic = True
                return m.group(0)
            if _is_expr(value):
                return _expr_body(value)
            return "'%s'" % str(value).replace("'", "''")

        out = _BARE_PARAM.sub(bare, out)
        dynamic = True

    if dynamic or "@{" in out:
        return {"value": out, "type": "Expression"}
    return out


def inline_dataset(factory: Factory, ref: dict) -> dict:
    """Build Fabric ``datasetSettings`` for an ADF dataset reference."""
    name = ref["referenceName"]
    ds = factory.datasets.get(name)
    if ds is None:
        return {"_migrationNote": f"Dataset '{name}' not found in factory"}
    params = dict(ref.get("parameters") or {})
    for pname, spec in (ds.get("parameters") or {}).items():
        if pname not in params and "defaultValue" in spec:
            params[pname] = spec["defaultValue"]
    settings = {
        "annotations": [],
        "type": ds.get("type"),
        "typeProperties": substitute(copy.deepcopy(ds.get("typeProperties", {})), params),
        "schema": ds.get("schema", []),
    }
    ls = ds.get("linkedServiceName", {}).get("referenceName")
    if ls:
        settings["externalReferences"] = {"connection": connection_placeholder(ls)}
    return settings


def convert_activity(factory: Factory, act: dict) -> dict:
    out = copy.deepcopy(act)
    atype = act.get("type")
    tp = out.setdefault("typeProperties", {})

    if "linkedServiceName" in out:
        ls = out.pop("linkedServiceName").get("referenceName")
        out["externalReferences"] = {"connection": connection_placeholder(ls)}

    if atype == "Copy":
        inputs, outputs = out.pop("inputs", []), out.pop("outputs", [])
        if inputs:
            tp.setdefault("source", {})["datasetSettings"] = inline_dataset(factory, inputs[0])
        if outputs:
            tp.setdefault("sink", {})["datasetSettings"] = inline_dataset(factory, outputs[0])
    elif atype in _DATASET_ACTIVITIES and "dataset" in tp:
        tp["datasetSettings"] = inline_dataset(factory, tp.pop("dataset"))
    elif atype == "ExecutePipeline":
        child = tp.get("pipeline", {}).get("referenceName")
        out["type"] = "InvokePipeline"
        out["typeProperties"] = {
            "operationType": "InvokeFabricPipeline",
            "workspaceId": "{{WORKSPACE_ID}}",
            "pipelineId": "{{PIPELINE:%s}}" % child,
            "waitOnCompletion": tp.get("waitOnCompletion", True),
            "parameters": tp.get("parameters", {}),
        }
        tp = out["typeProperties"]

    for key in _NESTED_LISTS:
        if key in tp:
            tp[key] = [convert_activity(factory, a) for a in tp[key]]
    for case in tp.get("cases", []):
        case["activities"] = [convert_activity(factory, a) for a in case.get("activities", [])]

    status, equivalent, note = rules.rule_for("activity", atype)
    if status == rules.BLOCKER:
        # Keep the activity so the pipeline shape is preserved, but deactivate it so
        # the draft imports and runs; the description tells the reviewer what to do.
        out["state"] = "Inactive"
        out["onInactiveMarkAs"] = "Succeeded"
        out["description"] = f"[MIGRATION BLOCKER] Replace with {equivalent}. {note}".strip()
    elif status == rules.REWORK:
        out["description"] = f"[MIGRATION REWORK] {equivalent}. {note}".strip()
    return out


def convert_pipeline(factory: Factory, name: str) -> dict:
    props = factory.pipelines[name]
    return {
        "name": name,
        "properties": {
            "description": props.get("description", ""),
            "activities": [convert_activity(factory, a) for a in props.get("activities", [])],
            "parameters": copy.deepcopy(props.get("parameters", {})),
            "variables": copy.deepcopy(props.get("variables", {})),
            "annotations": list(props.get("annotations", [])) + ["migrated-by-adf2fabric"],
        },
    }


def apply_connection_map(doc: dict, mapping: dict[str, str]) -> dict:
    """Replace ``{{CONNECTION:x}}`` / ``{{PIPELINE:x}}`` / ``{{WORKSPACE_ID}}`` placeholders."""
    text = json.dumps(doc)
    for key, value in mapping.items():
        text = text.replace("{{%s}}" % key, value)
        text = text.replace("{{CONNECTION:%s}}" % key, value)
    return json.loads(text)


def convert_factory(factory: Factory, out_dir: str | Path, pipelines=None,
                    mapping: dict[str, str] | None = None) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name in pipelines or sorted(factory.pipelines):
        if name not in factory.pipelines:
            raise KeyError(f"Pipeline '{name}' not found in factory")
        doc = convert_pipeline(factory, name)
        if mapping:
            doc = apply_connection_map(doc, mapping)
        path = out / f"{name}.json"
        path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        written.append(path)
    return written
