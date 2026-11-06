"""Dependency-aware migration waves.

A parent pipeline that calls children through *Execute Pipeline* can only be cut
over once those children exist in Fabric, so children always land in an earlier
wave than their parents.
"""
from __future__ import annotations

from .loader import Factory

CONTAINER_KEYS = (
    "activities",
    "ifTrueActivities",
    "ifFalseActivities",
    "defaultActivities",
)


def walk_activities(activities, container: str | None = None):
    """Yield ``(activity, container_name)`` for every activity, including nested ones."""
    for act in activities or []:
        yield act, container
        tp = act.get("typeProperties", {})
        for key in CONTAINER_KEYS:
            if key in tp:
                yield from walk_activities(tp[key], act.get("name"))
        for case in tp.get("cases", []):
            yield from walk_activities(case.get("activities"), act.get("name"))


def pipeline_dependencies(factory: Factory) -> dict[str, set[str]]:
    """Map each pipeline to the set of child pipelines it executes."""
    deps: dict[str, set[str]] = {}
    for name, props in factory.pipelines.items():
        children = set()
        for act, _ in walk_activities(props.get("activities")):
            if act.get("type") == "ExecutePipeline":
                ref = act.get("typeProperties", {}).get("pipeline", {}).get("referenceName")
                if ref:
                    children.add(ref)
        deps[name] = children
    return deps


def plan_waves(deps: dict[str, set[str]]):
    """Return ``(waves, cycles, missing)``.

    ``waves``   - list of pipeline-name lists; wave 1 has no dependencies.
    ``cycles``  - pipelines that call each other in a loop (cannot be ordered).
    ``missing`` - ``(parent, child)`` pairs where the child is not in the factory.
    """
    known = set(deps)
    missing = sorted((p, c) for p, kids in deps.items() for c in kids if c not in known)
    pending = {p: {c for c in kids if c in known} for p, kids in deps.items()}
    done: set[str] = set()
    waves: list[list[str]] = []
    while pending:
        ready = sorted(p for p, kids in pending.items() if kids <= done)
        if not ready:
            break
        waves.append(ready)
        done.update(ready)
        for p in ready:
            del pending[p]
    cycles = sorted(pending)
    return waves, cycles, missing
