#!/usr/bin/env python3
"""
PreFlight State, Tooling Matrix, Memory Advisor & Decision Ledger CLI (`scripts/state.py`).

Manages:
- .preflight/state.json (Working State + Evidence-Gated 5-dimension Readiness Rubric + Tooling & Memory Architecture)
- .preflight/decisions.json + docs/adr/NNNN-<slug>.md (Decision Ledger)
- .preflight/STACK.md (Tooling, OSS Building Blocks & Project Maintenance Stack document)

Programmatic Evidence Rules (anti-theater enforcement):
1. `score == 20` ("stress-tested") requires:
   - A substantive summary (>= 40 characters)
   - At least 2 concrete edge cases (`--edge-case`)
2. `dimension == "differentiation"` with `score > 0` requires:
   - `.preflight/prior-art.json` must exist and contain at least 1 scouted repository
   - For `score == 20`, the summary or edge cases must explicitly cite at least one discovered
     repository (`owner/repo` or repo name) from `prior-art.json`.
3. `readiness_unlocked` requires:
   - Total score >= 80%
   - Zero dimensions at 0%
   - `.preflight/prior-art.json` present
   - At least 1 recorded ADR in `.preflight/decisions.json`
   - At least 1 recorded Red-Team Critique in `red_team_critiques`
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
    "memory": "State, Memory & Agent Communication",
    "bottlenecks": "Bottlenecks & Failure Modes",
    "differentiation": "Prior-Art Differentiation",
}

TOOL_CATEGORIES = (
    "core-oss",
    "dependency-lock",
    "container-runtime",
    "orchestration-deploy",
    "ci-cd-quality",
    "storage-memory",
    "observability",
)

MEMORY_STRATEGIES = (
    "stateless",
    "transactional-db",
    "lexical-fts",
    "rag-vector-db",
    "hybrid-search",
    "episodic-agent-state",
)

MIN_SUMMARY_LEN_FOR_20 = 40
MIN_EDGE_CASES_FOR_20 = 2


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
        "tooling_recommendations": [],
        "memory_architecture": {
            "strategy": "",
            "agent_communication_pattern": "",
            "workflow_memory_flow": "",
            "rationale": "",
            "alternatives_considered": "",
            "failure_modes": [],
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
        "missing_gate_requirements": [],
    }


def reset_workspace_state(
    workspace: Path,
    purge_cache: bool = False,
    clear_adrs: bool = True,
) -> list[str]:
    """
    Delete all pre-performed scores, states, decisions, prior-art snapshots, and generated specs
    so the user can run a new idea or re-run the same idea cleanly from zero.
    """
    removed: list[str] = []
    preflight_dir = workspace / ".preflight"
    targets = [
        preflight_dir / "state.json",
        preflight_dir / "decisions.json",
        preflight_dir / "prior-art.json",
        preflight_dir / "SPEC.md",
        preflight_dir / "STACK.md",
        workspace / "blueprint_report.html",
    ]
    if purge_cache:
        targets.append(preflight_dir / "cache.db")

    for t in targets:
        if t.exists():
            t.unlink()
            removed.append(str(t.relative_to(workspace)))

    if clear_adrs:
        adr_dir = workspace / "docs" / "adr"
        if adr_dir.exists():
            for adr_file in sorted(adr_dir.glob("[0-9][0-9][0-9][0-9]-*.md")):
                adr_file.unlink()
                removed.append(str(adr_file.relative_to(workspace)))

    return removed


def load_prior_art(workspace: Path) -> dict[str, Any] | None:
    path = workspace / ".preflight" / "prior-art.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_decisions(workspace: Path) -> list[dict[str, Any]]:
    path = get_preflight_dir(workspace) / "decisions.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_decisions(workspace: Path, decisions: list[dict[str, Any]]) -> Path:
    path = get_preflight_dir(workspace) / "decisions.json"
    path.write_text(json.dumps(decisions, indent=2) + "\n", encoding="utf-8")
    return path


def evaluate_gate(state: dict[str, Any], workspace: Path | None = None) -> tuple[int, bool, list[str]]:
    dims = state.get("dimensions", {})
    scores = [int(dims.get(d, {}).get("score", 0)) for d in DIMENSIONS]
    total = max(0, min(100, sum(scores)))
    missing: list[str] = []

    if total < 80:
        missing.append(f"Total score is {total}% (requires >= 80%)")

    zero_dims = [d for d in DIMENSIONS if int(dims.get(d, {}).get("score", 0)) == 0]
    if zero_dims:
        missing.append(f"Untouched (0%) dimensions: {', '.join(zero_dims)}")

    if not (state.get("red_team_critiques") or []):
        missing.append("At least 1 Red-Team Critique (`add-critique`) is required")

    if workspace is not None:
        prior_art = load_prior_art(workspace)
        has_repos = bool(
            prior_art
            and ((prior_art.get("active_incumbents") or []) or (prior_art.get("graveyard_repos") or []))
        )
        if not has_repos:
            missing.append("Prior-Art Scout (`scout.py`) has not been run (.preflight/prior-art.json missing or empty)")

        decisions = load_decisions(workspace)
        if not decisions:
            missing.append("At least 1 Architecture Decision Record (`add-decision`) is required")

    unlocked = len(missing) == 0
    state["readiness_score"] = total
    state["readiness_unlocked"] = unlocked
    state["missing_gate_requirements"] = missing
    return total, unlocked, missing


def compute_readiness(state: dict[str, Any], workspace: Path | None = None) -> tuple[int, bool]:
    total, unlocked, _ = evaluate_gate(state, workspace)
    return total, unlocked


def load_state(workspace: Path) -> dict[str, Any]:
    path = get_preflight_dir(workspace) / "state.json"
    if not path.exists():
        state = default_state()
        evaluate_gate(state, workspace)
        return state
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("tooling_recommendations", [])
    data.setdefault(
        "memory_architecture",
        {
            "strategy": "",
            "agent_communication_pattern": "",
            "workflow_memory_flow": "",
            "rationale": "",
            "alternatives_considered": "",
            "failure_modes": [],
        },
    )
    evaluate_gate(data, workspace)
    return data


def build_stack_markdown(state: dict[str, Any]) -> str:
    project_name = state.get("project_name") or "Untitled Project"
    tools = state.get("tooling_recommendations") or []
    mem = state.get("memory_architecture") or {}

    lines = [
        f"# Tooling, OSS Stack & Memory Architecture: {project_name}",
        "",
        "## 1. Recommended Tooling, OSS Building Blocks & Project Maintenance",
        "",
    ]
    if not tools:
        lines.append("_No tooling recommendations recorded yet._")
        lines.append("")
    else:
        lines.append("| Category | Purpose | Recommended Tool | Why Chosen | Alternatives Considered |")
        lines.append("| :--- | :--- | :--- | :--- | :--- |")
        for t in tools:
            lines.append(
                f"| `{t.get('category', 'general')}` | {t.get('purpose', '—')} | **{t.get('recommended', '—')}** | "
                f"{t.get('why', '—')} | {t.get('alternatives', '—')} |"
            )
        lines.append("")

    lines.extend(
        [
            "## 2. Memory, State & Agent Communication Architecture",
            "",
            f"- **Selected Memory Strategy:** `{mem.get('strategy') or 'Unspecified'}`",
            f"- **Agent / Component Communication Pattern:** {mem.get('agent_communication_pattern') or '—'}",
            f"- **Workflow Memory Flow:** {mem.get('workflow_memory_flow') or '—'}",
            f"- **Why This Strategy (vs. RAG / Vector DB / Alternatives):** {mem.get('rationale') or '—'}",
            f"- **Alternatives Considered:** {mem.get('alternatives_considered') or '—'}",
            "",
        ]
    )
    fms = mem.get("failure_modes") or []
    if fms:
        lines.append("### Anticipated Memory Failure Modes & Mitigations")
        lines.append("")
        for fm in fms:
            lines.append(f"- ⚠️ {fm}")
        lines.append("")

    return "\n".join(lines)


def save_state(workspace: Path, state: dict[str, Any]) -> Path:
    state["updated_at"] = now_iso()
    status_clean(state, workspace)
    preflight_dir = get_preflight_dir(workspace)
    path = preflight_dir / "state.json"
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    # Keep .preflight/STACK.md synchronized whenever tooling or memory architecture exists
    if state.get("tooling_recommendations") or (state.get("memory_architecture") or {}).get("strategy"):
        stack_md_path = preflight_dir / "STACK.md"
        stack_md_path.write_text(build_stack_markdown(state) + "\n", encoding="utf-8")

    return path


def status_clean(state: dict[str, Any], workspace: Path | None = None) -> dict[str, Any]:
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
        d["label"] = DIMENSION_LABELS[dim]
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
    evaluate_gate(state, workspace)
    return state


def validate_dimension_evidence(
    workspace: Path,
    dimension: str,
    score: int,
    summary: str,
    edge_cases: list[str],
) -> str | None:
    """Return an error string if the requested score violates evidence rules, or None if valid."""
    clean_summary = summary.strip()
    if score > 0 and len(clean_summary) < 15:
        return f"Rejected: summary for '{dimension}' is too short ({len(clean_summary)} chars). Provide a real architectural explanation."

    if score == 20:
        if len(clean_summary) < MIN_SUMMARY_LEN_FOR_20:
            return (
                f"Rejected: score 20/20 on '{dimension}' requires a substantive summary "
                f"(>= {MIN_SUMMARY_LEN_FOR_20} chars; got {len(clean_summary)})."
            )
        if len(edge_cases) < MIN_EDGE_CASES_FOR_20:
            return (
                f"Rejected: score 20/20 on '{dimension}' requires at least {MIN_EDGE_CASES_FOR_20} "
                f"stress-tested edge cases (`--edge-case`); got {len(edge_cases)}."
            )

    if dimension == "differentiation" and score > 0:
        prior_art = load_prior_art(workspace)
        if not prior_art:
            return (
                "Rejected: cannot score 'differentiation' > 0 before running `scout.py` "
                "(.preflight/prior-art.json does not exist)."
            )
        repos = (prior_art.get("active_incumbents") or []) + (prior_art.get("graveyard_repos") or [])
        if not repos:
            return (
                "Rejected: `.preflight/prior-art.json` contains 0 discovered repositories. "
                "Run `scout.py` with valid search queries first."
            )
        if score == 20:
            combined_text = (clean_summary + " " + " ".join(edge_cases)).lower()
            repo_tokens: list[str] = []
            for r in repos:
                fn = (r.get("full_name") or "").lower()
                if fn:
                    repo_tokens.append(fn)
                    if "/" in fn:
                        repo_tokens.append(fn.split("/", 1)[1])
            if not any(tok and tok in combined_text for tok in repo_tokens):
                sample_names = ", ".join(r.get("full_name", "") for r in repos[:4])
                return (
                    "Rejected: score 20/20 on 'differentiation' must explicitly cite at least one "
                    f"discovered repository from `.preflight/prior-art.json` (e.g., {sample_names})."
                )
    return None


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
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if write_markdown:
        adr_dir.mkdir(parents=True, exist_ok=True)
        lines = [
            f"# ADR-{adr_num:04d}: {title}",
            "",
            "- **Status:** Accepted",
            f"- **Date:** {date_str}",
        ]
        if dimension:
            lines.append(f"- **Dimension:** `{dimension}`")
        lines.extend(
            [
                "",
                "## Decision",
                "",
                decision.strip(),
            ]
        )
        if rationale.strip():
            lines.extend(["", "## Context & Rationale", "", rationale.strip()])
        if rejected.strip():
            lines.extend(["", "## Considered & Rejected Alternatives", "", rejected.strip()])
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


def format_scorecard(state: dict[str, Any], workspace: Path | None = None) -> str:
    total, unlocked, missing = evaluate_gate(state, workspace)
    gate_str = "UNLOCKED (Ready for Blueprint)" if unlocked else "LOCKED"
    tools_count = len(state.get("tooling_recommendations") or [])
    mem_strat = (state.get("memory_architecture") or {}).get("strategy") or "unset"
    lines = [
        f"# PreFlight Readiness Scorecard: {state.get('project_name', 'Untitled')}",
        f"**Overall Readiness:** {total}% — **{gate_str}** | **Tooling Entries:** {tools_count} | **Memory Strategy:** `{mem_strat}`",
        "",
        "| Dimension | Score | Status | Edge Cases | Summary |",
        "| :--- | :---: | :---: | :---: | :--- |",
    ]
    for dim in DIMENSIONS:
        d = state["dimensions"][dim]
        summary = (d.get("summary") or "—").replace("\n", " ")
        ec_count = len(d.get("edge_cases") or [])
        lines.append(
            f"| **{d['label']}** (`{dim}`) | {d['score']}/20 | `{d['status']}` | {ec_count} | {summary} |"
        )
    if missing:
        lines.append("")
        lines.append("## Remaining Gate Requirements")
        for m in missing:
            lines.append(f"- 🔒 {m}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PreFlight state, tooling, memory & decision ledger manager")
    parser.add_argument("--workspace", default=".", help="Workspace root directory")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="Initialize or update project metadata (use --reset for a clean slate)")
    p_init.add_argument("--name", required=True, help="Project name")
    p_init.add_argument("--summary", default="", help="Project summary")
    p_init.add_argument("--runtime", default="", help="Target runtime")
    p_init.add_argument("--stack", default="", help="Comma-separated tech stack items")
    p_init.add_argument(
        "--reset",
        action="store_true",
        help="Wipe existing scores, state, decisions, prior-art, and blueprints before initializing",
    )
    p_init.add_argument(
        "--purge-cache",
        action="store_true",
        help="When used with --reset, also delete .preflight/cache.db",
    )

    p_reset = sub.add_parser(
        "reset",
        help="Clear all pre-performed scores, states, decisions, and prior-art so you can run a fresh idea",
    )
    p_reset.add_argument(
        "--purge-cache",
        action="store_true",
        help="Also delete the SQLite GitHub cache (.preflight/cache.db)",
    )
    p_reset.add_argument(
        "--keep-adrs",
        action="store_true",
        help="Keep existing docs/adr/NNNN-*.md files on disk",
    )

    p_score = sub.add_parser("update-dimension", help="Update a dimension score & notes (enforces evidence rules)")
    p_score.add_argument("--dimension", choices=DIMENSIONS, required=True)
    p_score.add_argument("--score", type=int, choices=[0, 10, 20], required=True)
    p_score.add_argument("--summary", required=True, help="Substantive summary of locked understanding")
    p_score.add_argument("--edge-case", action="append", default=[], help="Stress-tested edge case (>=2 required for score 20)")

    p_tool = sub.add_parser(
        "add-tool",
        help="Record a recommended OSS building block or project maintenance tool (Docker, Kubernetes, poetry/uv lock, etc.) with alternatives",
    )
    p_tool.add_argument(
        "--category",
        choices=TOOL_CATEGORIES,
        default="core-oss",
        help="Tool category (e.g. dependency-lock, container-runtime, orchestration-deploy, ci-cd-quality, core-oss)",
    )
    p_tool.add_argument("--purpose", required=True, help="What capability or maintenance job this tool fulfills")
    p_tool.add_argument("--recommended", required=True, help="Recommended tool, library, or lock/container mechanism")
    p_tool.add_argument("--why", required=True, help="Why this tool is recommended for this specific project")
    p_tool.add_argument("--alternatives", required=True, help="Viable alternatives and when/why to use or reject them")

    p_mem = sub.add_parser(
        "set-memory-arch",
        help="Configure agent communication pattern, memory strategy (stateless, SQLite, FTS, RAG, Vector DB), and memory failure modes",
    )
    p_mem.add_argument(
        "--strategy",
        choices=MEMORY_STRATEGIES,
        required=True,
        help="Primary memory architecture (stateless, transactional-db, lexical-fts, rag-vector-db, hybrid-search, episodic-agent-state)",
    )
    p_mem.add_argument(
        "--communication",
        required=True,
        help="How agents or components communicate & pass context/state across workflow steps",
    )
    p_mem.add_argument(
        "--workflow",
        default="",
        help="How memory is read/written/invalidated during the execution workflow",
    )
    p_mem.add_argument(
        "--rationale",
        required=True,
        help="Why this memory model fits better than alternatives (e.g., why SQLite FTS over Vector DB, or why RAG is needed)",
    )
    p_mem.add_argument(
        "--alternatives",
        default="",
        help="Other memory architectures considered (e.g., RAG, Vector DB, Redis, plain files) and why rejected",
    )
    p_mem.add_argument(
        "--failure-mode",
        action="append",
        default=[],
        help="Specific memory failure mode we might face and its mitigation (can be passed multiple times)",
    )

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

    p_design = sub.add_parser("set-design", help="Set Mermaid diagrams, trade-off options, and implementation steps")
    p_design.add_argument("--topology", default="", help="Mermaid flowchart string for system topology")
    p_design.add_argument("--topology-file", default="", help="Path to file containing Mermaid topology diagram")
    p_design.add_argument("--sequence", default="", help="Mermaid sequenceDiagram string")
    p_design.add_argument("--sequence-file", default="", help="Path to file containing Mermaid sequence diagram")
    p_design.add_argument(
        "--option",
        action="append",
        default=[],
        help="Trade-off option formatted as 'Option Name|Pros|Cons|Verdict'",
    )
    p_design.add_argument(
        "--step",
        action="append",
        default=[],
        help="Ordered implementation step (can be passed multiple times)",
    )

    p_status = sub.add_parser("status", help="Print current Readiness Scorecard")
    p_status.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    workspace = Path(args.workspace).resolve()

    if args.cmd == "reset":
        removed = reset_workspace_state(
            workspace=workspace,
            purge_cache=args.purge_cache,
            clear_adrs=not args.keep_adrs,
        )
        if removed:
            print(f"Reset complete. Removed {len(removed)} file(s): {', '.join(removed)}")
        else:
            print("Reset complete. Workspace was already clean.")
        return 0

    if args.cmd == "init":
        if args.reset:
            reset_workspace_state(
                workspace=workspace,
                purge_cache=args.purge_cache,
                clear_adrs=True,
            )
            state = default_state(name=args.name, summary=args.summary)
        else:
            existing_path = get_preflight_dir(workspace) / "state.json"
            if existing_path.exists():
                existing = load_state(workspace)
                old_name = (existing.get("project_name") or "").strip()
                # If switching to a different project name without --reset, warn clearly
                if old_name and old_name != "Untitled Project" and old_name.lower() != args.name.strip().lower():
                    print(
                        f"NOTE: Existing state found for '{old_name}'. Use `init --reset` or `state.py reset` "
                        "to wipe previous scores and decisions when starting a new idea.",
                        file=sys.stderr,
                    )
                state = existing
            else:
                state = default_state(name=args.name, summary=args.summary)

        state["project_name"] = args.name
        if args.summary:
            state["project_summary"] = args.summary
        if args.runtime:
            state["target_runtime"] = args.runtime
        if args.stack:
            state["tech_stack"] = [s.strip() for s in args.stack.split(",") if s.strip()]
        save_state(workspace, state)
        print(format_scorecard(state, workspace))
        return 0

    if args.cmd == "update-dimension":
        state = load_state(workspace)
        d = state["dimensions"][args.dimension]
        existing_ecs = list(d.get("edge_cases") or [])
        for ec in args.edge_case:
            if ec.strip() and ec.strip() not in existing_ecs:
                existing_ecs.append(ec.strip())

        err = validate_dimension_evidence(
            workspace=workspace,
            dimension=args.dimension,
            score=args.score,
            summary=args.summary,
            edge_cases=existing_ecs,
        )
        if err:
            print(f"ERROR: {err}", file=sys.stderr)
            return 2

        d["score"] = args.score
        d["summary"] = args.summary.strip()
        d["edge_cases"] = existing_ecs
        save_state(workspace, state)
        print(format_scorecard(state, workspace))
        return 0

    if args.cmd == "add-tool":
        state = load_state(workspace)
        tools = state.setdefault("tooling_recommendations", [])
        entry = {
            "category": args.category,
            "purpose": args.purpose.strip(),
            "recommended": args.recommended.strip(),
            "why": args.why.strip(),
            "alternatives": args.alternatives.strip(),
        }
        # Replace if same category + purpose already exists, otherwise append
        replaced = False
        for idx, existing in enumerate(tools):
            if (
                existing.get("category") == entry["category"]
                and existing.get("purpose", "").lower() == entry["purpose"].lower()
            ):
                tools[idx] = entry
                replaced = True
                break
        if not replaced:
            tools.append(entry)
        save_state(workspace, state)
        print(f"Recorded tool [{entry['category']}]: {entry['recommended']} ({entry['purpose']})")
        return 0

    if args.cmd == "set-memory-arch":
        state = load_state(workspace)
        mem = state.setdefault("memory_architecture", {})
        existing_fms = list(mem.get("failure_modes") or [])
        for fm in args.failure_mode:
            if fm.strip() and fm.strip() not in existing_fms:
                existing_fms.append(fm.strip())
        mem["strategy"] = args.strategy
        mem["agent_communication_pattern"] = args.communication.strip()
        if args.workflow:
            mem["workflow_memory_flow"] = args.workflow.strip()
        mem["rationale"] = args.rationale.strip()
        if args.alternatives:
            mem["alternatives_considered"] = args.alternatives.strip()
        mem["failure_modes"] = existing_fms
        save_state(workspace, state)
        print(f"Updated memory_architecture: strategy={args.strategy} ({len(existing_fms)} failure modes tracked)")
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
        state = load_state(workspace)
        save_state(workspace, state)
        print(json.dumps(entry, indent=2))
        return 0

    if args.cmd == "set-design":
        state = load_state(workspace)
        sys_design = state.setdefault(
            "system_design",
            {
                "topology_mermaid": "",
                "sequence_mermaid": "",
                "options_matrix": [],
                "implementation_steps": [],
            },
        )
        if args.topology_file:
            sys_design["topology_mermaid"] = Path(args.topology_file).read_text(encoding="utf-8").strip()
        elif args.topology:
            sys_design["topology_mermaid"] = args.topology.strip()

        if args.sequence_file:
            sys_design["sequence_mermaid"] = Path(args.sequence_file).read_text(encoding="utf-8").strip()
        elif args.sequence:
            sys_design["sequence_mermaid"] = args.sequence.strip()

        if args.option:
            parsed_options = []
            for raw_opt in args.option:
                parts = [p.strip() for p in raw_opt.split("|")]
                if len(parts) != 4:
                    print(
                        f"ERROR: --option must have 4 pipe-separated fields 'Option|Pros|Cons|Verdict'; got: {raw_opt}",
                        file=sys.stderr,
                    )
                    return 2
                parsed_options.append(
                    {
                        "option": parts[0],
                        "pros": parts[1],
                        "cons": parts[2],
                        "verdict": parts[3],
                    }
                )
            sys_design["options_matrix"] = parsed_options

        if args.step:
            sys_design["implementation_steps"] = [s.strip() for s in args.step if s.strip()]

        save_state(workspace, state)
        print("Updated system_design in .preflight/state.json")
        return 0

    if args.cmd == "status":
        state = load_state(workspace)
        if args.json:
            print(json.dumps(state, indent=2))
        else:
            print(format_scorecard(state, workspace))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
