"""Score every factory object for Microsoft Fabric compatibility."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from . import rules
from .loader import Factory
from .waves import pipeline_dependencies, plan_waves, walk_activities


@dataclass
class Finding:
    kind: str            # activity | linked_service | trigger | integration_runtime
    name: str
    adf_type: str
    status: str
    fabric_equivalent: str
    note: str
    effort_hours: float
    pipeline: str | None = None
    container: str | None = None


@dataclass
class PipelineSummary:
    name: str
    status: str
    activities: int
    blockers: int
    effort_hours: float
    wave: int | None
    children: list[str]
    triggers: list[str]


@dataclass
class Assessment:
    factory_name: str
    counts: dict
    findings: list[Finding] = field(default_factory=list)
    pipelines: list[PipelineSummary] = field(default_factory=list)
    waves: list[list[str]] = field(default_factory=list)
    cycles: list[str] = field(default_factory=list)
    missing_references: list[tuple[str, str]] = field(default_factory=list)

    def of_kind(self, kind: str) -> list[Finding]:
        return [f for f in self.findings if f.kind == kind]

    @property
    def activity_status_counts(self) -> dict[str, int]:
        out = {rules.SUPPORTED: 0, rules.REWORK: 0, rules.BLOCKER: 0}
        for f in self.of_kind("activity"):
            out[f.status] += 1
        return out

    @property
    def readiness_pct(self) -> float:
        """Share of activities that migrate without redesign (supported + rework)."""
        c = self.activity_status_counts
        total = sum(c.values())
        return round(100 * (total - c[rules.BLOCKER]) / total, 1) if total else 100.0

    @property
    def blockers(self) -> list[Finding]:
        return [f for f in self.findings if f.status == rules.BLOCKER]

    @property
    def total_effort_hours(self) -> float:
        return round(
            sum(f.effort_hours for f in self.findings)
            + rules.EFFORT_HOURS["pipeline_base"] * len(self.pipelines),
            2,
        )

    def to_dict(self) -> dict:
        return {
            "factory": self.factory_name,
            "counts": self.counts,
            "summary": {
                "activity_status": self.activity_status_counts,
                "readiness_pct": self.readiness_pct,
                "blockers": len(self.blockers),
                "total_effort_hours": self.total_effort_hours,
            },
            "waves": self.waves,
            "cycles": self.cycles,
            "missing_references": [list(m) for m in self.missing_references],
            "pipelines": [asdict(p) for p in self.pipelines],
            "findings": [asdict(f) for f in self.findings],
        }


def _finding(kind: str, name: str, adf_type: str, **extra) -> Finding:
    status, equivalent, note = rules.rule_for(kind, adf_type)
    return Finding(
        kind=kind,
        name=name,
        adf_type=adf_type,
        status=status,
        fabric_equivalent=equivalent,
        note=note,
        effort_hours=rules.EFFORT_HOURS[kind][status],
        **extra,
    )


def trigger_targets(props: dict) -> list[str]:
    """Pipelines a trigger starts.

    Schedule/event triggers use a ``pipelines`` list; tumbling-window triggers use
    a singular ``pipeline`` object.
    """
    tp_names = [
        p.get("pipelineReference", {}).get("referenceName")
        for p in props.get("pipelines", [])
    ]
    single = props.get("pipeline", {}).get("pipelineReference", {}).get("referenceName")
    if single:
        tp_names.append(single)
    return [n for n in tp_names if n]


def assess(factory: Factory) -> Assessment:
    result = Assessment(factory_name=factory.name, counts=factory.counts())

    deps = pipeline_dependencies(factory)
    waves, cycles, missing = plan_waves(deps)
    result.waves, result.cycles, result.missing_references = waves, cycles, missing
    wave_of = {p: i + 1 for i, wave in enumerate(waves) for p in wave}

    triggers_by_pipeline: dict[str, list[str]] = {}
    for tname, tprops in factory.triggers.items():
        result.findings.append(_finding("trigger", tname, tprops.get("type", "Unknown")))
        for target in trigger_targets(tprops):
            triggers_by_pipeline.setdefault(target, []).append(tname)

    for pname, pprops in factory.pipelines.items():
        acts = [
            _finding("activity", act.get("name", "?"), act.get("type", "Unknown"),
                     pipeline=pname, container=container)
            for act, container in walk_activities(pprops.get("activities"))
        ]
        result.findings.extend(acts)
        result.pipelines.append(
            PipelineSummary(
                name=pname,
                status=rules.worst(a.status for a in acts),
                activities=len(acts),
                blockers=sum(a.status == rules.BLOCKER for a in acts),
                effort_hours=round(
                    rules.EFFORT_HOURS["pipeline_base"] + sum(a.effort_hours for a in acts), 2
                ),
                wave=wave_of.get(pname),
                children=sorted(deps.get(pname, ())),
                triggers=sorted(triggers_by_pipeline.get(pname, [])),
            )
        )
    result.pipelines.sort(key=lambda p: (p.wave or 99, p.name))

    for lname, lprops in factory.linked_services.items():
        result.findings.append(_finding("linked_service", lname, lprops.get("type", "Unknown")))
    for rname, rprops in factory.integration_runtimes.items():
        result.findings.append(
            _finding("integration_runtime", rname, rules.runtime_type(rprops))
        )
    return result
