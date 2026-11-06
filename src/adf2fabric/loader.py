"""Load an Azure Data Factory definition.

Two input shapes are supported:

* an ARM template export (``ARMTemplateForFactory.json`` from "Export ARM template"
  or the ``adf_publish`` branch), and
* a Git-integrated factory folder (``pipeline/``, ``dataset/``, ``linkedService/``,
  ``trigger/``, ``integrationRuntime/``, ``dataflow/``).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

_ARM_TYPES = {
    "Microsoft.DataFactory/factories/pipelines": "pipelines",
    "Microsoft.DataFactory/factories/datasets": "datasets",
    "Microsoft.DataFactory/factories/linkedServices": "linked_services",
    "Microsoft.DataFactory/factories/triggers": "triggers",
    "Microsoft.DataFactory/factories/integrationRuntimes": "integration_runtimes",
    "Microsoft.DataFactory/factories/dataflows": "dataflows",
}

_GIT_FOLDERS = {
    "pipeline": "pipelines",
    "dataset": "datasets",
    "linkedService": "linked_services",
    "trigger": "triggers",
    "integrationRuntime": "integration_runtimes",
    "dataflow": "dataflows",
}

# "[concat(parameters('factoryName'), '/pl_load_sales')]"  ->  pl_load_sales
_ARM_NAME = re.compile(r"'/([^']+)'\s*\)\s*\]$")


@dataclass
class Factory:
    """In-memory view of a factory: every object's ``properties`` keyed by name."""

    name: str
    pipelines: dict[str, dict] = field(default_factory=dict)
    datasets: dict[str, dict] = field(default_factory=dict)
    linked_services: dict[str, dict] = field(default_factory=dict)
    triggers: dict[str, dict] = field(default_factory=dict)
    integration_runtimes: dict[str, dict] = field(default_factory=dict)
    dataflows: dict[str, dict] = field(default_factory=dict)

    def counts(self) -> dict[str, int]:
        return {
            "pipelines": len(self.pipelines),
            "datasets": len(self.datasets),
            "linked_services": len(self.linked_services),
            "triggers": len(self.triggers),
            "integration_runtimes": len(self.integration_runtimes),
            "dataflows": len(self.dataflows),
        }


def resource_name(raw: str) -> str:
    """Turn an ARM resource name expression into the plain object name."""
    match = _ARM_NAME.search(raw)
    if match:
        return match.group(1)
    return raw.rsplit("/", 1)[-1]


def load_factory(path: str | Path) -> Factory:
    """Load a factory from an ARM template file or a Git-integrated folder."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"No such file or folder: {p}")
    if p.is_dir():
        if any((p / folder).is_dir() for folder in _GIT_FOLDERS):
            return _load_git(p)
        for candidate in ("ARMTemplateForFactory.json", "arm_template.json"):
            if (p / candidate).is_file():
                return _load_arm(p / candidate)
        raise ValueError(
            f"{p} is neither a Git-integrated factory folder nor contains an ARM template"
        )
    return _load_arm(p)


def _load_arm(path: Path) -> Factory:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if "resources" not in doc:
        raise ValueError(f"{path} is not an ARM template (no 'resources' array)")
    default_name = (
        doc.get("parameters", {}).get("factoryName", {}).get("defaultValue") or path.stem
    )
    factory = Factory(name=default_name)
    for res in doc["resources"]:
        bucket = _ARM_TYPES.get(res.get("type", ""))
        if bucket:
            getattr(factory, bucket)[resource_name(res["name"])] = res.get("properties", {})
    return factory


def _load_git(folder: Path) -> Factory:
    factory = Factory(name=folder.name)
    for sub, bucket in _GIT_FOLDERS.items():
        directory = folder / sub
        if not directory.is_dir():
            continue
        for file in sorted(directory.glob("*.json")):
            obj = json.loads(file.read_text(encoding="utf-8"))
            getattr(factory, bucket)[obj.get("name", file.stem)] = obj.get("properties", {})
    return factory
