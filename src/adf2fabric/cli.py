"""Command-line interface: ``adf2fabric assess | convert | run``."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, report
from .assess import assess
from .convert import convert_factory
from .loader import load_factory


def _write_reports(assessment, out: Path, formats: list[str], repo_url: str | None) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    written = []
    if "json" in formats:
        p = out / "assessment.json"
        p.write_text(report.to_json(assessment), encoding="utf-8")
        written.append(p)
    if "md" in formats:
        p = out / "assessment.md"
        p.write_text(report.to_markdown(assessment), encoding="utf-8")
        written.append(p)
    if "html" in formats:
        p = out / "index.html"
        p.write_text(report.to_html(assessment, repo_url), encoding="utf-8")
        written.append(p)
    return written


def _summary_line(a) -> str:
    c = a.activity_status_counts
    return (
        f"{a.factory_name}: {a.counts['pipelines']} pipelines, {sum(c.values())} activities | "
        f"{a.readiness_pct}% ready | {c['blocker']} blockers | "
        f"{len(a.waves)} waves | ~{a.total_effort_hours:g} h"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="adf2fabric",
        description="Assess and convert Azure Data Factory pipelines for Microsoft Fabric.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("source", help="ARM template JSON or Git-integrated factory folder")
        p.add_argument("-o", "--out", default="adf2fabric-output", help="output folder")

    pa = sub.add_parser("assess", help="score every object for Fabric compatibility")
    common(pa)
    pa.add_argument("--format", default="html,md,json", help="comma list of html, md, json")
    pa.add_argument("--repo-url", help="link shown in the HTML footer")
    pa.add_argument("--fail-on-blockers", action="store_true",
                    help="exit with code 2 when blockers are found (for CI gates)")

    pc = sub.add_parser("convert", help="generate draft Fabric pipeline JSON")
    common(pc)
    pc.add_argument("--pipeline", action="append", help="only convert this pipeline (repeatable)")
    pc.add_argument("--connections", help="JSON map of linked service / placeholder -> Fabric ID")

    pr = sub.add_parser("run", help="assess and convert in one go")
    common(pr)
    pr.add_argument("--repo-url", help="link shown in the HTML footer")
    pr.add_argument("--connections", help="JSON map of linked service / placeholder -> Fabric ID")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        factory = load_factory(args.source)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    out = Path(args.out)
    mapping = None
    if getattr(args, "connections", None):
        mapping = json.loads(Path(args.connections).read_text(encoding="utf-8"))

    if args.command in ("assess", "run"):
        a = assess(factory)
        formats = ["html", "md", "json"] if args.command == "run" else [
            f.strip() for f in args.format.split(",") if f.strip()]
        for path in _write_reports(a, out, formats, args.repo_url):
            print(f"wrote {path}")
        print(_summary_line(a))
        if args.command == "assess" and args.fail_on_blockers and a.blockers:
            return 2

    if args.command in ("convert", "run"):
        try:
            files = convert_factory(factory, out / "fabric_pipelines",
                                    getattr(args, "pipeline", None), mapping)
        except KeyError as exc:
            print(f"error: {exc.args[0]}", file=sys.stderr)
            return 1
        print(f"wrote {len(files)} draft Fabric pipeline(s) to {out / 'fabric_pipelines'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
