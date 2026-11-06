"""Render an assessment as JSON, Markdown or a self-contained HTML page."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from html import escape

from . import __version__, rules
from .assess import Assessment

_LABEL = {rules.SUPPORTED: "Supported", rules.REWORK: "Rework", rules.BLOCKER: "Blocker"}
_KIND_TITLE = {
    "activity": "Activities",
    "linked_service": "Linked services → Fabric connections",
    "trigger": "Triggers",
    "integration_runtime": "Integration runtimes",
}


def to_json(a: Assessment) -> str:
    return json.dumps(a.to_dict(), indent=2)


def to_markdown(a: Assessment) -> str:
    c = a.activity_status_counts
    lines = [
        f"# Fabric migration assessment: {a.factory_name}",
        "",
        f"- **Readiness:** {a.readiness_pct}% of {sum(c.values())} activities migrate without redesign",
        f"- **Activities:** {c['supported']} supported, {c['rework']} rework, {c['blocker']} blocker",
        f"- **Blockers:** {len(a.blockers)}",
        f"- **Estimated effort:** {a.total_effort_hours} hours",
        "",
        "## Migration waves",
        "",
    ]
    for i, wave in enumerate(a.waves, 1):
        lines.append(f"{i}. {', '.join(wave)}")
    if a.cycles:
        lines.append(f"\n**Circular calls (order manually):** {', '.join(a.cycles)}")
    lines += [
        "",
        "## Pipelines",
        "",
        "| Wave | Pipeline | Status | Activities | Blockers | Effort (h) | Triggers |",
        "|---|---|---|---|---|---|---|",
    ]
    for p in a.pipelines:
        lines.append(
            f"| {p.wave or '-'} | {p.name} | {_LABEL[p.status]} | {p.activities} | "
            f"{p.blockers} | {p.effort_hours} | {', '.join(p.triggers) or '-'} |"
        )
    if a.blockers:
        lines += ["", "## Blockers", ""]
        for f in a.blockers:
            where = f" in `{f.pipeline}`" if f.pipeline else ""
            lines.append(f"- **{f.name}** ({f.adf_type}){where}: {f.note}")
    for kind, title in _KIND_TITLE.items():
        items = a.of_kind(kind)
        if not items:
            continue
        lines += ["", f"## {title}", "", "| Name | ADF type | Status | Fabric equivalent | Note |", "|---|---|---|---|---|"]
        for f in items:
            name = f"{f.pipeline} / {f.name}" if f.pipeline else f.name
            lines.append(f"| {name} | {f.adf_type} | {_LABEL[f.status]} | {f.fabric_equivalent} | {f.note} |")
    return "\n".join(lines) + "\n"


_CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#17202a;--muted:#5d6b7a;--line:#e3e7ec;
--ok:#1f8a4c;--rw:#c27c0e;--bl:#c0392b;--accent:#0f6cbd}
@media (prefers-color-scheme:dark){:root{--bg:#0f1419;--card:#18202a;--ink:#e6edf3;
--muted:#9aa7b4;--line:#2a3542;--ok:#3fb56f;--rw:#e0a23a;--bl:#e5604f;--accent:#4aa3ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:1100px;margin:0 auto;padding:32px 16px 64px}
h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:36px 0 12px}
.sub{color:var(--muted);margin:0 0 24px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.card b{display:block;font-size:26px}.card span{color:var(--muted);font-size:13px}
.bar{display:flex;height:14px;border-radius:7px;overflow:hidden;margin:18px 0 6px;background:var(--line)}
.bar i{display:block}.ok{background:var(--ok)}.rw{background:var(--rw)}.bl{background:var(--bl)}
.legend{display:flex;gap:16px;flex-wrap:wrap;color:var(--muted);font-size:13px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px}
.waves{display:flex;gap:10px;flex-wrap:wrap}
.wave{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;flex:1;min-width:200px}
.wave h3{margin:0 0 6px;font-size:13px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.wave div{font-family:ui-monospace,Consolas,monospace;font-size:13px}
.tbl{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:10px}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{text-align:left;padding:8px 12px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.03em}
tr:last-child td{border-bottom:0}code{font-size:13px}
.pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:600;color:#fff}
footer{margin-top:40px;color:var(--muted);font-size:13px}a{color:var(--accent)}
"""

_PILL = {rules.SUPPORTED: "ok", rules.REWORK: "rw", rules.BLOCKER: "bl"}


def _pill(status: str) -> str:
    return f'<span class="pill {_PILL[status]}">{_LABEL[status]}</span>'


def to_html(a: Assessment, repo_url: str | None = None) -> str:
    c = a.activity_status_counts
    total = sum(c.values()) or 1
    e = escape
    seg = "".join(
        f'<i class="{_PILL[s]}" style="width:{100 * c[s] / total:.2f}%" title="{_LABEL[s]}: {c[s]}"></i>'
        for s in (rules.SUPPORTED, rules.REWORK, rules.BLOCKER)
        if c[s]
    )
    cards = [
        (f"{a.readiness_pct}%", "activities migrate without redesign"),
        (str(a.counts["pipelines"]), "pipelines"),
        (str(sum(c.values())), "activities"),
        (str(len(a.blockers)), "blockers"),
        (f"{a.total_effort_hours:g} h", "estimated effort"),
        (str(len(a.waves)), "migration waves"),
    ]
    waves = "".join(
        f'<div class="wave"><h3>Wave {i}</h3>' + "".join(f"<div>{e(p)}</div>" for p in wave) + "</div>"
        for i, wave in enumerate(a.waves, 1)
    )
    if a.cycles:
        waves += '<div class="wave"><h3>Circular - order manually</h3>' + "".join(
            f"<div>{e(p)}</div>" for p in a.cycles) + "</div>"

    prow = "".join(
        f"<tr><td>{p.wave or '-'}</td><td><code>{e(p.name)}</code></td><td>{_pill(p.status)}</td>"
        f"<td>{p.activities}</td><td>{p.blockers}</td><td>{p.effort_hours:g}</td>"
        f"<td>{e(', '.join(p.children)) or '-'}</td><td>{e(', '.join(p.triggers)) or '-'}</td></tr>"
        for p in a.pipelines
    )

    sections = []
    for kind, title in _KIND_TITLE.items():
        items = a.of_kind(kind)
        if not items:
            continue
        rows = "".join(
            f"<tr><td><code>{e(f.pipeline + ' / ' if f.pipeline else '')}{e(f.name)}</code></td>"
            f"<td>{e(f.adf_type)}</td><td>{_pill(f.status)}</td><td>{e(f.fabric_equivalent)}</td>"
            f"<td>{e(f.note)}</td></tr>"
            for f in items
        )
        sections.append(
            f"<h2>{e(title)}</h2><div class='tbl'><table><thead><tr><th>Name</th><th>ADF type</th>"
            f"<th>Status</th><th>Fabric equivalent</th><th>Note</th></tr></thead><tbody>{rows}</tbody></table></div>"
        )

    blockers = ""
    if a.blockers:
        blockers = "<h2>Blockers to resolve before cut-over</h2><div class='tbl'><table><thead><tr>" \
            "<th>Object</th><th>Type</th><th>Recommended replacement</th><th>Why</th></tr></thead><tbody>" + "".join(
            f"<tr><td><code>{e((f.pipeline + ' / ') if f.pipeline else '')}{e(f.name)}</code></td><td>{e(f.adf_type)}</td>"
            f"<td>{e(f.fabric_equivalent)}</td><td>{e(f.note)}</td></tr>" for f in a.blockers
        ) + "</tbody></table></div>"

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    repo = f' · <a href="{e(repo_url)}">Source on GitHub</a>' if repo_url else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ADF → Fabric assessment: {e(a.factory_name)}</title><style>{_CSS}</style></head>
<body><main>
<h1>ADF → Microsoft Fabric migration assessment</h1>
<p class="sub">Factory <code>{e(a.factory_name)}</code> · {a.counts['pipelines']} pipelines,
{a.counts['datasets']} datasets, {a.counts['linked_services']} linked services,
{a.counts['triggers']} triggers, {a.counts['integration_runtimes']} integration runtimes</p>
<div class="cards">{''.join(f'<div class="card"><b>{v}</b><span>{l}</span></div>' for v, l in cards)}</div>
<div class="bar">{seg}</div>
<div class="legend"><span><i class="ok"></i>Supported {c['supported']}</span>
<span><i class="rw"></i>Rework {c['rework']}</span><span><i class="bl"></i>Blocker {c['blocker']}</span></div>
<h2>Migration waves</h2>
<p class="sub">Child pipelines always land before the parents that call them.</p>
<div class="waves">{waves}</div>
<h2>Pipelines</h2>
<div class="tbl"><table><thead><tr><th>Wave</th><th>Pipeline</th><th>Status</th><th>Activities</th>
<th>Blockers</th><th>Effort (h)</th><th>Calls</th><th>Triggers</th></tr></thead><tbody>{prow}</tbody></table></div>
{blockers}
{''.join(sections)}
<footer>Generated by adf2fabric {__version__} on {stamp}{repo}</footer>
</main></body></html>
"""
