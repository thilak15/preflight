#!/usr/bin/env python3
"""
PreFlight State & Decision Ledger CLI helper.

Manages:
- .preflight/state.json (Working State + 5-dimension Readiness Gate rubric)
- .preflight/decisions.json + docs/adr/NNNN-<slug>.md (Decision Ledger)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DIMENSIONS = (
    "problem",
    "scope",
    "memory",
    "bottlenecks",
    "differentiation",
)

DIMENSION_LABELS = {
    "problem": "Problem & User Pain",
    "scope": "Scope & Non-Goals",
    "memory": "State & Persistence (Memory)",
    "bottlenecks": "Bottlenecks & Failure Modes",
    "differentiation": "Prior-Art Differentiation",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or "decision"


def get_preflight_dir(workspace: Path) -> Path:
    d = workspace / ".preflight"
    d.mkdir(parents=True, exist_ok=True)
    return d


def default_state(name: str = "", summary: str = "") -> dict[str, Any]:
    return {
        "project_name": name or "Untitled Project",
        "project_summary": summary,
        "target_runtime": "",
        "tech_stack": [],
        "bottlenecks": [],
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "dimensions": {
            dim: {
                "label": DIMENSION_LABELS[dim],
                "score": 0,  # 0, 10, or 20
                "status": "untouched",  # untouched | surface | stress-tested
                "summary": "",
                "edge_cases": [],
            }
            for dim in DIMENSIONS
        },
        "red_team_critiques": [],
        "system_design": {
            "topology_mermaid": "",
            "sequence_mermaid": "",
            "options_matrix": [],
            "implementation_steps": [],
        },
        "readiness_score": 0,
        "readiness_unlocked": False,
        "forced_unlock": False,
    }


def compute_readiness(state: dict[str, Any]) -> tuple[int, bool]:
    dims = state.get("dimensions", {})
    scores = [int(dims.get(d, {}).get("score", 0)) for d in DIMENSIONS]
    total = max(0, min(100, sum(scores)))
    no_zero = all(s > 0 for s in scores)
    unlocked = bool(state.get("forced_unlock")) or (total >= 80 and no_zero)
    state["readiness_score"] = total
    state["readiness_unlocked"] = unlocked
    return total, unlocked


def load_state(workspace: Path) -> dict[str, Any]:
    path = get_preflight_dir(workspace) / "state.json"
    if not path.exists():
        state = default_state()
        compute_readiness(state)
        return state
    data = json.loads(path.read_text(encoding="utf-8"))
    compute_readiness(data)
    return data


def save_state(workspace: Path, state: dict[str, Any]) -> Path:
    state["updated_at"] = now_iso()
    compute_readiness(state)
    path = get_preflight_dir(workspace) / "state.json"
    path.write_text(json.dumps(status_clean(state), indent=2) + "\n", encoding="utf-8")
    return path


def status_clean(state: dict[str, Any]) -> dict[str, Any]:
    for dim in DIMENSIONS:
        d = state.setdefault("dimensions", {}).setdefault(
            dim,
            {
                "label": DIMENSION_LABELS[dim],
                "score": 0,
                "status": "untouched",
                "summary": "",
                "edge_cases": [],
            },
        )
        score = int(d.get("score", 0))
        if score >= 20:
            d["score"] = 20
            d["status"] = "stress-tested"
        elif score >= 10:
            d["score"] = 10
            d["status"] = "surface"
        else:
            d["score"] = 0
            d["status"] = "untouched"
    compute_readiness(state)
    return state


def load_decisions(workspace: Path) -> list[dict[str, Any]]:
    path = get_preflight_dir(workspace) / "decisions.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_decisions(workspace: Path, decisions: list[dict[str, Any]]) -> Path:
    path = get_preflight_dir(workspace) / "decisions.json"
    path.write_text(json.dumps(decisions, indent=2) + "\n", encoding="utf-8")
    return path


def next_adr_number(adr_dir: Path) -> int:
    if not adr_dir.exists():
        return 1
    highest = 0
    for f in adr_dir.glob("*.md"):
        m = re.match(r"^(\d{4})-", f.name)
        if m:
            highest = max(highest, int(m.group(1)))
    return highest + 1


def record_adr(
    workspace: Path,
    title: str,
    decision: str,
    rejected: str = "",
    rationale: str = "",
    dimension: str = "",
    write_markdown: bool = True,
) -> dict[str, Any]:
    decisions = load_decisions(workspace)
    adr_dir = workspace / "docs" / "adr"
    adr_num = max(next_adr_number(adr_dir), len(decisions) + 1)
    slug = slugify(title)
    adr_filename = f"{adr_num:04d}-{slug}.md"
    adr_rel_path = f"docs/adr/{adr_filename}"

    if write_markdown:
        adr_dir.mkdir(parents=True, exist_ok=True)
        lines = [f"# {title}", "", decision.strip()]
        if rationale.strip():
            lines.extend(["", f"**Rationale:** {rationale.strip()}"])
        if rejected.strip():
            lines.extend(["", "## Considered & Rejected", "", rejected.strip()])
        (adr_dir / adr_filename).write_text("\n".join(lines) + "\n", encoding="utf-8")

    entry = {
        "id": f"ADR-{adr_num:04d}",
        "number": adr_num,
        "title": title,
        "decision": decision,
        "rejected": rejected,
        "rationale": rationale,
        "dimension": dimension,
        "file": adr_rel_path if write_markdown else "",
        "created_at": now_iso(),
    }
    decisions.append(entry)
    save_decisions(workspace, decisions)
    return entry


def format_scorecard(state: dict[str, Any]) -> str:
    total, unlocked = compute_readiness(state)
    gate_str = "UNLOCKED (Ready for Blueprint)" if unlocked else "LOCKED (Requires >=80% and no 0% dimensions)"
    lines = [
        f"# PreFlight Readiness Scorecard: {state.get('project_name', 'Untitled')}",
        f"**Overall Readiness:** {total}% — **{gate_str}**",
        "",
        "| Dimension | Score | Status | Summary |",
        "| :--- | :---: | :---: | :--- |",
    ]
    for dim in DIMENSIONS:
        d = state["dimensions"][dim]
        summary = (d.get("summary") or "—").replace("\n", " ")
        lines.append(
            f"| **{d['label']}** (`{dim}`) | {d['score']}/20 | `{d['status']}` | {summary} |"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PreFlight state & decision ledger manager")
    parser.add_argument("--workspace", default=".", help="Workspace root directory")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="Initialize or update project metadata")
    p_init.add_argument("--name", required=True, help="Project name")
    p_init.add_argument("--summary", default="", help="Project summary")
    p_init.add_argument("--runtime", default="", help="Target runtime")
    p_init.add_argument("--stack", default="", help="Comma-separated tech stack items")

    p_score = sub.add_parser("update-dimension", help="Update a dimension score & notes")
    p_score.add_argument("--dimension", choices=DIMENSIONS, required=True)
    p_score.add_argument("--score", type=int, choices=[0, 10, 20], required=True)
    p_score.add_argument("--summary", required=True, help="Summary of locked understanding")
    p_score.add_argument("--edge-case", action="append", default=[], help="Stress-tested edge case")

    p_crit = sub.add_parser("add-critique", help="Add an adversarial red-team critique finding")
    p_crit.add_argument("--title", required=True)
    p_crit.add_argument("--severity", choices=["critical", "high", "medium"], default="high")
    p_crit.add_argument("--attack", required=True, help="How this architectural assumption fails under stress")
    p_crit.add_argument("--mitigation", required=True, help="How the design resolves or mitigates it")

    p_adr = sub.add_parser("add-decision", help="Append an architectural decision (and write docs/adr/NNNN.md)")
    p_adr.add_argument("--title", required=True)
    p_adr.add_argument("--decision", required=True)
    p_adr.add_argument("--rejected", default="")
    p_adr.add_argument("--rationale", default="")
    p_adr.add_argument("--dimension", choices=list(DIMENSIONS) + [""], default="")
    p_adr.add_argument("--no-markdown", action="store_true", help="Skip writing docs/adr/NNNN.md")

    p_status = sub.add_parser("status", help="Print current Readiness Scorecard")
    p_status.add_argument("--json", action="store_true")

    p_force = sub.add_parser("force-unlock", help="Override the Readiness Gate via explicit user request")

    args = parser.parse_args(argv)
    workspace = Path(args.workspace).resolve()

    if args.cmd == "init":
        state = load_state(workspace)
        state["project_name"] = args.name
        if args.summary:
            state["project_summary"] = args.summary
        if args.runtime:
            state["target_runtime"] = args.runtime
        if args.stack:
            state["tech_stack"] = [s.strip() for s in args.stack.split(",") if s.strip()]
        save_state(workspace, state)
        print(format_scorecard(state))
        return 0

    if args.cmd == "update-dimension":
        state = load_state(workspace)
        d = state["dimensions"][args.dimension]
        d["score"] = args.score
        d["summary"] = args.summary
        if args.edge_case:
            existing = d.get("edge_cases", [])
            for ec in args.edge_case:
                if ec not in existing:
                    existing.append(ec)
            d["edge_cases"] = existing
        save_state(workspace, state)
        print(format_scorecard(state))
        return 0

    if args.cmd == "add-critique":
        state = load_state(workspace)
        state.setdefault("red_team_critiques", []).append(
            {
                "title": args.title,
                "severity": args.severity,
                "attack": args.attack,
                "mitigation": args.mitigation,
            }
        )
        save_state(workspace, state)
        print(f"Added critique: {args.title} ({args.severity})")
        return 0

    if args.cmd == "add-decision":
        entry = record_adr(
            workspace=workspace,
            title=args.title,
            decision=args.decision,
            rejected=args.rejected,
            rationale=args.rationale,
            dimension=args.dimension,
            write_markdown=not args.no_markdown,
        )
        print(json.dumps(entry, indent=2))
        return 0

    if args.cmd == "force-unlock":
        state = load_state(workspace)
        state["forced_unlock"] = True
        save_state(workspace, state)
        print(format_scorecard(state))
        return 0

    if args.cmd == "status":
        state = load_state(workspace)
        if args.json:
            print(json.dumps(state, indent=2))
        else:
            print(format_scorecard(state))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
