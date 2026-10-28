#!/usr/bin/env python3
"""
PreFlight Blueprint & Specification Generator (`scripts/render_blueprint.py`).

Reads:
- `.preflight/state.json` (Working State, 5-dimension Readiness Scorecard, Tooling & Maintenance Matrix,
  Memory & Agent Communication Architecture, Red-Team Critiques, System Design)
- `.preflight/decisions.json` (Decision Ledger / ADRs)
- `.preflight/prior-art.json` (Active Incumbents, Graveyard/Dormant Repos, OSS Building Blocks, Verified Pain Points)

Enforces:
1. Evidence-based Readiness Gate (`evaluate_gate`: score >= 80%, no 0% dimensions, `prior-art.json` present,
   >= 1 ADR, >= 1 Red-Team Critique).
2. Explicit `topology_mermaid` and `sequence_mermaid` in `system_design` (rejects missing diagrams so
   placeholder diagrams are never shipped behind a "PASSED" badge).

Outputs:
- `blueprint_report.html`: Dark-mode interactive HTML dashboard with Mermaid.js diagrams, Tooling & Stack
  recommendations, Memory & Agent Communication breakdown, offline raw source fallback, and 1-click "Copy Spec Markdown".
- `.preflight/SPEC.md` (or `--spec-output`): Clean Markdown specification document ready for implementation.
- `.preflight/STACK.md`: Dedicated Tooling, OSS Building Blocks, Project Maintenance & Memory Architecture doc.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any

from state import (
    DIMENSIONS,
    DIMENSION_LABELS,
    build_stack_markdown,
    evaluate_gate,
    export_tickets_to_dir,
    format_memory_strategy_display,
    format_stack_explained_table,
    load_decisions,
    load_prior_art as load_prior_art_optional,
    load_state,
    strip_step_prefix,
)


def esc(val: Any) -> str:
    return html.escape(str(val or ""))


def load_prior_art(workspace: Path) -> dict[str, Any]:
    data = load_prior_art_optional(workspace)
    if not data:
        return {
            "active_incumbents": [],
            "graveyard_repos": [],
            "oss_building_blocks": [],
            "observed_stack_configs": [],
            "pain_points": [],
            "queries": [],
        }
    return data


def build_spec_markdown(
    state: dict[str, Any],
    decisions: list[dict[str, Any]],
    prior_art: dict[str, Any],
    is_draft: bool | None = None,
) -> str:
    project_name = state.get("project_name") or "Untitled Project"
    project_summary = state.get("project_summary") or "No project summary provided."
    runtime = state.get("target_runtime") or "Unspecified Runtime"
    stack = ", ".join(state.get("tech_stack") or []) or "Unspecified"
    readiness_score = int(state.get("readiness_score", 0))
    unlocked = bool(state.get("readiness_unlocked", False))
    draft = (not unlocked) if is_draft is None else is_draft
    title_prefix = "[DRAFT] " if draft else ""
    readiness_badge = "DRAFT — Readiness Gate Bypassed via `--force`" if draft else "Evidence-Verified"

    lines = [
        f"# {title_prefix}System Design Specification: {project_name}",
        "",
    ]
    if draft:
        lines.extend(
            [
                "> ⚠️ **DRAFT SPECIFICATION — READINESS GATE LOCKED:** This document was generated using `--force` before all PreFlight Readiness Gate checks passed. Do not treat as an approved production spec.",
                "",
            ]
        )
    lines.extend(
        [
            f"- **Readiness Score:** {readiness_score}% ({readiness_badge})",
            f"- **Target Runtime:** {runtime}",
            f"- **Tech Stack:** {stack}",
            "",
            "## 1. Executive Summary",
            "",
            project_summary,
            "",
            "## 2. Architectural Dimensions & Stress-Tested Edge Cases",
            "",
        ]
    )

    for dim in DIMENSIONS:
        d = state.get("dimensions", {}).get(dim, {})
        label = d.get("label") or DIMENSION_LABELS[dim]
        score = int(d.get("score", 0))
        summary = d.get("summary") or "—"
        lines.append(f"### {label} (`{dim}` — {score}/20)")
        lines.append(summary)
        edge_cases = d.get("edge_cases") or []
        if edge_cases:
            lines.append("")
            lines.append("**Stress-Tested Edge Cases:**")
            for ec in edge_cases:
                lines.append(f"- {ec}")
        lines.append("")

    # Memory & Agent Communication Section
    mem = state.get("memory_architecture") or {}
    if mem.get("strategy") or mem.get("agent_communication_pattern") or mem.get("failure_modes"):
        secondaries = [s for s in (mem.get("secondary_strategies") or []) if s]
        lines.extend(
            [
                "### Memory, State & Agent Communication Workflow",
                "",
                f"- **Primary Memory Strategy:** `{mem.get('strategy') or 'Unspecified'}`",
                f"- **Secondary / Combined Strategies:** {', '.join(f'`{s}`' for s in secondaries) if secondaries else 'None (single-strategy)'}",
                f"- **Combined Memory Profile:** `{format_memory_strategy_display(mem)}`",
                f"- **Agent / Component Communication Pattern:** {mem.get('agent_communication_pattern') or '—'}",
                f"- **Workflow Memory Lifecycle:** {mem.get('workflow_memory_flow') or '—'}",
                f"- **Why Chosen (vs. RAG / Vector DB / Alternatives):** {mem.get('rationale') or '—'}",
                f"- **Alternatives Considered:** {mem.get('alternatives_considered') or '—'}",
                "",
            ]
        )
        for fm in mem.get("failure_modes") or []:
            lines.append(f"- ⚠️ **Memory Failure Mode & Mitigation:** {fm}")
        lines.append("")

    # Tooling, OSS Building Blocks & Project Maintenance Section ("Stack Explained")
    sec_num = 3
    tools = state.get("tooling_recommendations") or []
    oss_blocks = prior_art.get("oss_building_blocks") or []
    observed_configs = prior_art.get("observed_stack_configs") or []
    if tools or oss_blocks or observed_configs:
        lines.append(f"## {sec_num}. Stack Explained (Tooling, Alternatives, Now vs. Later & Proof Status)")
        sec_num += 1
        lines.append("")
        if tools:
            lines.extend(format_stack_explained_table(tools))
            lines.append("")
        if observed_configs:
            lines.append("### Config Files Verified in Scouted Incumbent Repos")
            lines.append("")
            lines.append("| Category | Tool Proven | Config File Inspected | Observed In Repos |")
            lines.append("| :--- | :--- | :--- | :--- |")
            for oc in observed_configs:
                repos_list = ", ".join(f"`{r}`" for r in oc.get("repos") or [])
                lines.append(
                    f"| `{oc.get('category', '—')}` | **{oc.get('tool', '—')}** | `{oc.get('config_file', '—')}` | {repos_list} |"
                )
            lines.append("")
        if oss_blocks:
            lines.append("### Scouted Open-Source Building Blocks (GitHub)")
            lines.append("")
            lines.append("| Repository | Stars | License | Language | Last Push | Description |")
            lines.append("| :--- | :---: | :---: | :---: | :---: | :--- |")
            for b in oss_blocks[:8]:
                desc = (b.get("description") or "—").replace("|", "\\|")
                lines.append(
                    f"| [{b['full_name']}]({b['html_url']}) | ⭐ {b['stars']} | `{b.get('license', 'Unspecified')}` | "
                    f"{b.get('language', '—')} | {b['inactive_days']}d ago | {desc} |"
                )
            lines.append("")

    lines.append(f"## {sec_num}. Adversarial Red-Team Critiques & Mitigations")
    sec_num += 1
    lines.append("")
    critiques = state.get("red_team_critiques") or []
    for c in critiques:
        lines.append(f"### [{(c.get('severity') or 'high').upper()}] {c.get('title')}")
        lines.append(f"- **Failure Mode / Attack Vector:** {c.get('attack')}")
        lines.append(f"- **Architectural Mitigation:** {c.get('mitigation')}")
        lines.append("")

    lines.append(f"## {sec_num}. GitHub Prior-Art & Mined Pain Points")
    sec_num += 1
    lines.append("")
    incumbents = prior_art.get("active_incumbents") or []
    graveyard = prior_art.get("graveyard_repos") or []
    if incumbents or graveyard:
        lines.append("| Repository | Stars | Velocity | Last Push | Status | Summary |")
        lines.append("| :--- | :---: | :---: | :---: | :--- | :--- |")
        for r in incumbents[:8]:
            desc = (r.get("description") or "—").replace("|", "\\|")
            lines.append(
                f"| [{r['full_name']}]({r['html_url']}) | ⭐ {r['stars']} | {r['star_velocity_per_month']}/mo | {r['inactive_days']}d ago | Active Incumbent | {desc} |"
            )
        for r in graveyard[:6]:
            desc = (r.get("description") or "—").replace("|", "\\|")
            lines.append(
                f"| [{r['full_name']}]({r['html_url']}) | ⭐ {r['stars']} | {r['star_velocity_per_month']}/mo | {r['inactive_days']}d ago | {r.get('graveyard_reason') or 'Dormant'} | {desc} |"
            )
        lines.append("")

    pain_points = prior_art.get("pain_points") or []
    if pain_points:
        lines.append("### Verified User Pain Points from Open Issues")
        lines.append("")
        for p in pain_points[:10]:
            cat = "BUG/FAILURE" if p.get("category") == "bug_or_failure" else "TOP-VOTED"
            lines.append(
                f"- **[{cat}] [{p['repo_full_name']}#{p['issue_number']}]({p['issue_url']}) — {p['title']}** "
                f"(👍 {p['reactions_plus_one']} | 💬 {p['comments_count']})"
            )
            if p.get("body_excerpt"):
                lines.append(f"  > {p['body_excerpt']}")
            for tc in p.get("top_comments") or []:
                lines.append(f"  > 💬 **@{tc['author']}** (👍 {tc['reactions']}): {tc['excerpt']}")
        lines.append("")

    sys_design = state.get("system_design") or {}
    topology_mermaid = (sys_design.get("topology_mermaid") or "").strip()
    sequence_mermaid = (sys_design.get("sequence_mermaid") or "").strip()

    lines.extend(
        [
            f"## {sec_num}. System Architecture Diagrams",
            "",
            "### System Topology",
            "",
            "```mermaid",
            topology_mermaid,
            "```",
            "",
            "### Request / Execution Lifecycle",
            "",
            "```mermaid",
            sequence_mermaid,
            "```",
            "",
        ]
    )
    sec_num += 1

    options_matrix = sys_design.get("options_matrix") or []
    if options_matrix:
        lines.extend(
            [
                "### Architecture Trade-Off Matrix",
                "",
                "| Option | Pros | Cons | Verdict |",
                "| :--- | :--- | :--- | :--- |",
            ]
        )
        for o in options_matrix:
            lines.append(
                f"| **{o.get('option')}** | {o.get('pros')} | {o.get('cons')} | {o.get('verdict')} |"
            )
        lines.append("")

    lines.append(f"## {sec_num}. Decision Ledger (ADRs)")
    sec_num += 1
    lines.append("")
    for adr in decisions:
        lines.append(f"### {adr.get('id')}: {adr.get('title')}")
        lines.append(f"- **Decision:** {adr.get('decision')}")
        if adr.get("rationale"):
            lines.append(f"- **Rationale:** {adr.get('rationale')}")
        if adr.get("rejected"):
            lines.append(f"- **Rejected Alternatives:** {adr.get('rejected')}")
        lines.append("")

    impl_steps = sys_design.get("implementation_steps") or []
    if impl_steps:
        lines.append(f"## {sec_num}. Implementation Plan")
        lines.append("")
        for idx, step in enumerate(impl_steps, start=1):
            clean_step = strip_step_prefix(step)
            lines.append(f"{idx}. {clean_step}")
        lines.append("")

    return "\n".join(lines)


def build_html(
    state: dict[str, Any],
    decisions: list[dict[str, Any]],
    prior_art: dict[str, Any],
    spec_markdown: str,
) -> str:
    project_name = esc(state.get("project_name") or "Untitled Project")
    project_summary = esc(state.get("project_summary") or "No project summary provided.")
    runtime = esc(state.get("target_runtime") or "Unspecified Runtime")
    stack_items = state.get("tech_stack") or []
    readiness_score = int(state.get("readiness_score", 0))
    unlocked = bool(state.get("readiness_unlocked", False))

    gate_badge_color = "#10b981" if unlocked else "#f59e0b"
    gate_badge_text = "READINESS GATE PASSED" if unlocked else "DRAFT / OVERRIDE"

    # 1. Dimension Cards
    dim_cards_html = []
    for dim in DIMENSIONS:
        d = state.get("dimensions", {}).get(dim, {})
        label = esc(d.get("label") or DIMENSION_LABELS[dim])
        score = int(d.get("score", 0))
        pct = score * 5
        status = esc(d.get("status", "untouched"))
        summary = esc(d.get("summary") or "Not yet evaluated.")
        edge_cases = d.get("edge_cases") or []
        ec_html = ""
        if edge_cases:
            items = "".join(f"<li>{esc(ec)}</li>" for ec in edge_cases)
            ec_html = f'<ul class="edge-list">{items}</ul>'
        bar_color = "#10b981" if score == 20 else ("#f59e0b" if score == 10 else "#ef4444")
        dim_cards_html.append(
            f"""
            <div class="card dim-card">
                <div class="dim-header">
                    <span class="dim-title">{label}</span>
                    <span class="dim-score" style="color:{bar_color}">{score}/20 ({status})</span>
                </div>
                <div class="progress-track">
                    <div class="progress-fill" style="width:{pct}%; background:{bar_color}"></div>
                </div>
                <p class="dim-summary">{summary}</p>
                {ec_html}
            </div>
            """
        )

    # 2. Red-Team Critiques
    critiques = state.get("red_team_critiques") or []
    if critiques:
        crit_rows = []
        for c in critiques:
            sev = (c.get("severity") or "high").lower()
            sev_color = "#ef4444" if sev == "critical" else ("#f97316" if sev == "high" else "#eab308")
            crit_rows.append(
                f"""
                <div class="card critique-card" style="border-left: 4px solid {sev_color}">
                    <div class="crit-header">
                        <h4>{esc(c.get("title"))}</h4>
                        <span class="badge" style="background:{sev_color}22; color:{sev_color}; border:1px solid {sev_color}55">{esc(sev.upper())}</span>
                    </div>
                    <p><strong>Failure Mode / Attack Vector:</strong> {esc(c.get("attack"))}</p>
                    <p><strong>Architectural Mitigation:</strong> {esc(c.get("mitigation"))}</p>
                </div>
                """
            )
        critiques_html = "".join(crit_rows)
    else:
        critiques_html = '<div class="card"><p class="muted">No red-team critiques recorded.</p></div>'

    # 3. Prior-Art Matrix & Pain-Point Mine
    incumbents = prior_art.get("active_incumbents") or []
    graveyard = prior_art.get("graveyard_repos") or []
    oss_blocks = prior_art.get("oss_building_blocks") or []
    pain_points = prior_art.get("pain_points") or []

    inc_rows = []
    for r in incumbents:
        inc_rows.append(
            f"""
            <tr>
                <td><a href="{esc(r.get('html_url'))}" target="_blank" rel="noopener">{esc(r.get('full_name'))}</a></td>
                <td>⭐ {int(r.get('stars', 0)):,}</td>
                <td>{esc(r.get('star_velocity_per_month'))}/mo</td>
                <td>{int(r.get('inactive_days', 0))}d ago</td>
                <td><span class="badge badge-green">Active Incumbent</span></td>
                <td>{esc(r.get('description'))}</td>
            </tr>
            """
        )
    for r in graveyard:
        inc_rows.append(
            f"""
            <tr class="graveyard-row">
                <td><a href="{esc(r.get('html_url'))}" target="_blank" rel="noopener">{esc(r.get('full_name'))}</a></td>
                <td>⭐ {int(r.get('stars', 0)):,}</td>
                <td>{esc(r.get('star_velocity_per_month'))}/mo</td>
                <td>{int(r.get('inactive_days', 0))}d ago</td>
                <td><span class="badge badge-red">{esc(r.get('graveyard_reason') or 'Dormant >365d')}</span></td>
                <td>{esc(r.get('description'))}</td>
            </tr>
            """
        )
    prior_art_table_body = "".join(inc_rows) or '<tr><td colspan="6" class="muted">No repositories scouted.</td></tr>'

    pp_cards = []
    for p in pain_points[:12]:
        cat = p.get("category") or "top_voted"
        cat_badge = (
            '<span class="badge badge-red">BUG / FAILURE</span>'
            if cat == "bug_or_failure"
            else '<span class="badge badge-blue">TOP-VOTED</span>'
        )
        top_comments = p.get("top_comments") or []
        comments_html = ""
        if top_comments:
            c_items = "".join(
                f'<div class="comment-quote"><strong>@{esc(tc.get("author"))}</strong> (👍 {int(tc.get("reactions", 0))}): {esc(tc.get("excerpt"))}</div>'
                for tc in top_comments
            )
            comments_html = f'<div class="comments-box">{c_items}</div>'

        pp_cards.append(
            f"""
            <div class="card pp-card">
                <div class="pp-header">
                    <div>
                        {cat_badge}
                        <a href="{esc(p.get('issue_url'))}" target="_blank" rel="noopener" class="pp-link">
                            {esc(p.get('repo_full_name'))}#{int(p.get('issue_number', 0))}
                        </a>
                    </div>
                    <span class="pp-metric">👍 {int(p.get('reactions_plus_one', 0))} &nbsp;|&nbsp; 💬 {int(p.get('comments_count', 0))}</span>
                </div>
                <h4>{esc(p.get('title'))}</h4>
                <p class="muted">{esc(p.get('body_excerpt') or 'No body excerpt.')}</p>
                {comments_html}
            </div>
            """
        )
    pain_points_html = "".join(pp_cards) or '<div class="card"><p class="muted">No verified open issue pain points mined.</p></div>'

    # 3b. "Stack Explained" (Tooling, Now vs. Later, Verified vs Claimed) & Memory Architecture HTML
    tools = state.get("tooling_recommendations") or []
    observed_configs = prior_art.get("observed_stack_configs") or []
    if tools:
        tool_rows = []
        for t in tools:
            stage = (t.get("stage") or "now").lower()
            stage_badge = (
                '<span class="badge badge-green">NOW (Day 1)</span>'
                if stage == "now"
                else '<span class="badge badge-blue">LATER (Defer)</span>'
            )
            proof = esc(t.get("config_proof") or "—")
            p_status = t.get("proof_status") or "claimed-unverified"
            p_source = esc(t.get("proof_source") or "")
            if p_status == "verified":
                proof_badge = f'<span class="badge badge-green">Verified ({p_source})</span>'
            else:
                proof_badge = '<span class="badge badge-red">Claimed / Unverified</span>'
            tool_rows.append(
                f"""
                <tr>
                    <td>
                        <span class="badge badge-green">{esc(t.get('recommended'))}</span>
                        <div class="muted" style="font-size:0.78rem; margin-top:0.2rem">{esc(t.get('category', 'core-oss'))}</div>
                    </td>
                    <td>{stage_badge}</td>
                    <td><strong>{esc(t.get('purpose'))}</strong></td>
                    <td>{esc(t.get('why'))}</td>
                    <td class="muted">{esc(t.get('alternatives'))}</td>
                    <td>{proof_badge}<div style="margin-top:0.2rem"><code>{proof}</code></div></td>
                </tr>
                """
            )
        tool_rows_html = "".join(tool_rows)
    else:
        tool_rows_html = '<tr><td colspan="6" class="muted">No explicit Stack Explained entries added via `state.py add-tool` yet.</td></tr>'

    if observed_configs:
        cfg_rows = "".join(
            f"""
            <tr>
                <td><span class="badge badge-blue">{esc(oc.get('category'))}</span></td>
                <td><strong>{esc(oc.get('tool'))}</strong></td>
                <td><code>{esc(oc.get('config_file'))}</code></td>
                <td>{esc(', '.join(oc.get('repos') or []))}</td>
            </tr>
            """
            for oc in observed_configs
        )
    else:
        cfg_rows = '<tr><td colspan="4" class="muted">No config-file stack signals recorded in `.preflight/prior-art.json` yet.</td></tr>'

    if oss_blocks:
        oss_rows = "".join(
            f"""
            <tr>
                <td><a href="{esc(b.get('html_url'))}" target="_blank" rel="noopener">{esc(b.get('full_name'))}</a></td>
                <td>⭐ {int(b.get('stars', 0)):,}</td>
                <td><code>{esc(b.get('license', 'Unspecified'))}</code></td>
                <td>{esc(b.get('language'))}</td>
                <td>{int(b.get('inactive_days', 0))}d ago</td>
                <td>{esc(b.get('description'))}</td>
            </tr>
            """
            for b in oss_blocks
        )
    else:
        oss_rows = '<tr><td colspan="6" class="muted">No open-source building blocks scouted via `scout.py -t` yet.</td></tr>'

    mem = state.get("memory_architecture") or {}
    mem_strategy = esc(format_memory_strategy_display(mem) if mem.get("strategy") else "Not explicitly set (see Memory dimension)")
    mem_comm = esc(mem.get("agent_communication_pattern") or "—")
    mem_flow = esc(mem.get("workflow_memory_flow") or "—")
    mem_rationale = esc(mem.get("rationale") or "—")
    mem_alts = esc(mem.get("alternatives_considered") or "—")
    mem_fms = mem.get("failure_modes") or []
    mem_fm_html = (
        "<ul class='edge-list'>" + "".join(f"<li>⚠️ {esc(fm)}</li>" for fm in mem_fms) + "</ul>"
        if mem_fms
        else '<p class="muted">See Memory dimension edge cases.</p>'
    )

    # 4. System Design & Mermaid
    sys_design = state.get("system_design") or {}
    topology_mermaid = (sys_design.get("topology_mermaid") or "").strip()
    sequence_mermaid = (sys_design.get("sequence_mermaid") or "").strip()
    options_matrix = sys_design.get("options_matrix") or []
    if options_matrix:
        opt_rows = "".join(
            f"""
            <tr>
                <td><strong>{esc(o.get('option'))}</strong></td>
                <td>{esc(o.get('pros'))}</td>
                <td>{esc(o.get('cons'))}</td>
                <td>{esc(o.get('verdict'))}</td>
            </tr>
            """
            for o in options_matrix
        )
    else:
        opt_rows = '<tr><td colspan="4" class="muted">See Decision Ledger (ADRs) for evaluated trade-offs.</td></tr>'

    # 5. Decision Ledger & Implementation Steps
    if decisions:
        adr_cards = []
        for adr in decisions:
            adr_cards.append(
                f"""
                <div class="card adr-card">
                    <div class="adr-header">
                        <span class="badge badge-blue">{esc(adr.get('id'))}</span>
                        <h4>{esc(adr.get('title'))}</h4>
                        <span class="muted">{esc(adr.get('file'))}</span>
                    </div>
                    <p><strong>Locked Decision:</strong> {esc(adr.get('decision'))}</p>
                    {f"<p><strong>Rationale:</strong> {esc(adr.get('rationale'))}</p>" if adr.get('rationale') else ""}
                    {f"<p class='rejected'><strong>Rejected Alternatives:</strong> {esc(adr.get('rejected'))}</p>" if adr.get('rejected') else ""}
                </div>
                """
            )
        decisions_html = "".join(adr_cards)
    else:
        decisions_html = '<div class="card"><p class="muted">No ADRs recorded in Decision Ledger.</p></div>'

    impl_steps = sys_design.get("implementation_steps") or []
    if impl_steps:
        steps_html = "<ol class='step-list'>" + "".join(f"<li>{esc(s)}</li>" for s in impl_steps) + "</ol>"
    else:
        steps_html = '<p class="muted">No implementation steps recorded.</p>'

    stack_badges = "".join(f'<span class="stack-pill">{esc(s)}</span>' for s in stack_items) or '<span class="stack-pill">TBD</span>'
    spec_json_escaped = json.dumps(spec_markdown)
    title_prefix = "[DRAFT] " if not unlocked else ""
    rubric_subtitle = "Evidence-Verified Rubric" if unlocked else "DRAFT (Gate Bypassed via --force)"
    draft_banner_html = (
        """
        <div style="background:#ef444422; border:2px solid #ef4444; color:#fca5a5; padding:1rem 1.25rem; border-radius:10px; margin-bottom:1.5rem; font-weight:600;">
          ⚠️ <strong>DRAFT BLUEPRINT (READINESS GATE LOCKED):</strong> This report was rendered with <code>--force</code> before meeting PreFlight's 80% evidence gate. All specifications and tickets are marked <code>DRAFT</code>.
        </div>
        """
        if not unlocked
        else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{title_prefix}PreFlight Blueprint — {project_name}</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<style>
  :root {{
    --bg: #0b0f19;
    --panel: #111827;
    --panel-alt: #1f2937;
    --border: #374151;
    --text: #f3f4f6;
    --muted: #9ca3af;
    --accent: #38bdf8;
    --green: #10b981;
    --amber: #f59e0b;
    --red: #ef4444;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, sans-serif;
    line-height: 1.6;
    padding: 2rem;
  }}
  .container {{ max-width: 1280px; margin: 0 auto; }}
  header {{
    background: linear-gradient(135deg, #111827 0%, #1e293b 100%);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 2rem;
    margin-bottom: 1.5rem;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 1.5rem;
    flex-wrap: wrap;
  }}
  .title-group h1 {{ font-size: 2rem; letter-spacing: -0.02em; margin-bottom: 0.4rem; }}
  .title-group p {{ color: var(--muted); max-width: 760px; }}
  .meta-row {{ margin-top: 1rem; display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; }}
  .stack-pill {{
    background: #1e293b;
    border: 1px solid #334155;
    color: var(--accent);
    padding: 0.2rem 0.65rem;
    border-radius: 999px;
    font-size: 0.8rem;
    font-weight: 600;
  }}
  .score-box {{
    background: #0f172a;
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.25rem 1.5rem;
    text-align: right;
    min-width: 240px;
  }}
  .score-number {{ font-size: 2.5rem; font-weight: 800; color: {gate_badge_color}; line-height: 1.1; }}
  .score-label {{ font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); }}
  .copy-btn {{
    margin-top: 0.75rem;
    background: #1e293b;
    color: var(--accent);
    border: 1px solid var(--accent);
    padding: 0.4rem 0.85rem;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.8rem;
    font-weight: 600;
  }}
  .copy-btn:hover {{ background: var(--accent); color: #0f172a; }}
  .tabs {{
    display: flex;
    gap: 0.5rem;
    margin-bottom: 1.5rem;
    border-bottom: 1px solid var(--border);
    padding-bottom: 0.75rem;
    flex-wrap: wrap;
  }}
  .tab-btn {{
    background: var(--panel);
    color: var(--muted);
    border: 1px solid var(--border);
    padding: 0.55rem 1.1rem;
    border-radius: 8px;
    cursor: pointer;
    font-weight: 600;
    font-size: 0.9rem;
    transition: all 0.15s ease;
  }}
  .tab-btn.active, .tab-btn:hover {{
    color: var(--text);
    border-color: var(--accent);
    background: #1e293b;
  }}
  .tab-panel {{ display: none; }}
  .tab-panel.active {{ display: block; }}
  .grid-2 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 1rem; }}
  .card {{
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1.25rem;
    margin-bottom: 1rem;
  }}
  .dim-header, .crit-header, .pp-header, .adr-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.5rem;
    gap: 0.5rem;
  }}
  .dim-title {{ font-weight: 700; font-size: 1.05rem; }}
  .dim-score {{ font-weight: 700; font-size: 0.9rem; }}
  .progress-track {{
    width: 100%;
    height: 8px;
    background: #1f2937;
    border-radius: 999px;
    overflow: hidden;
    margin-bottom: 0.75rem;
  }}
  .progress-fill {{ height: 100%; border-radius: 999px; }}
  .edge-list {{ margin-top: 0.6rem; padding-left: 1.2rem; color: var(--muted); font-size: 0.9rem; }}
  .badge {{
    padding: 0.15rem 0.55rem;
    border-radius: 6px;
    font-size: 0.75rem;
    font-weight: 700;
    margin-right: 0.4rem;
  }}
  .badge-green {{ background: #10b98122; color: #34d399; border: 1px solid #10b98155; }}
  .badge-red {{ background: #ef444422; color: #f87171; border: 1px solid #ef444455; }}
  .badge-blue {{ background: #38bdf822; color: #38bdf8; border: 1px solid #38bdf855; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 0.5rem; font-size: 0.92rem; }}
  th, td {{ padding: 0.75rem; text-align: left; border-bottom: 1px solid var(--border); }}
  th {{ color: var(--muted); font-weight: 600; text-transform: uppercase; font-size: 0.75rem; }}
  tr.graveyard-row {{ background: #ef44440a; }}
  a {{ color: var(--accent); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .muted {{ color: var(--muted); font-size: 0.9rem; }}
  .rejected {{ color: #fca5a5; margin-top: 0.35rem; }}
  .comments-box {{
    margin-top: 0.65rem;
    padding-top: 0.55rem;
    border-top: 1px dashed var(--border);
  }}
  .comment-quote {{
    font-size: 0.85rem;
    color: #cbd5e1;
    background: #0f172a;
    padding: 0.45rem 0.65rem;
    border-radius: 6px;
    margin-top: 0.35rem;
    border-left: 3px solid var(--accent);
  }}
  .mermaid-box {{
    background: #0f172a;
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1.5rem;
    overflow-x: auto;
    margin-top: 0.75rem;
  }}
  details.raw-mermaid {{ margin-top: 0.5rem; font-size: 0.82rem; color: var(--muted); }}
  details.raw-mermaid pre {{
    background: #0b0f19;
    padding: 0.75rem;
    border-radius: 6px;
    border: 1px solid var(--border);
    margin-top: 0.35rem;
    color: #e2e8f0;
    overflow-x: auto;
  }}
  .step-list {{ padding-left: 1.4rem; }}
  .step-list li {{ margin-bottom: 0.6rem; }}
  h2.section-title {{ font-size: 1.35rem; margin: 1.25rem 0 0.75rem; color: #e2e8f0; }}
</style>
</head>
<body>
<div class="container">
  {draft_banner_html}
  <header>
    <div class="title-group">
      <div class="score-label">PREFLIGHT ARCHITECTURE &amp; PRIOR-ART BLUEPRINT</div>
      <h1>{title_prefix}{project_name}</h1>
      <p>{project_summary}</p>
      <div class="meta-row">
        <span class="stack-pill">Runtime: {runtime}</span>
        {stack_badges}
      </div>
    </div>
    <div class="score-box">
      <div class="score-label">{gate_badge_text}</div>
      <div class="score-number">{readiness_score}%</div>
      <div class="muted">{rubric_subtitle}</div>
      <button class="copy-btn" onclick="copySpecMarkdown(this)">Copy Spec Markdown (.preflight/SPEC.md)</button>
    </div>
  </header>

  <div class="tabs">
    <button class="tab-btn active" onclick="showTab('tab-scorecard', this)">1. Readiness &amp; Red-Team</button>
    <button class="tab-btn" onclick="showTab('tab-prior-art', this)">2. Prior-Art &amp; Pain Points ({len(incumbents) + len(graveyard)})</button>
    <button class="tab-btn" onclick="showTab('tab-tooling-memory', this)">3. Stack Explained &amp; Memory ({len(tools) + len(observed_configs)})</button>
    <button class="tab-btn" onclick="showTab('tab-design', this)">4. System Topology &amp; Sequence</button>
    <button class="tab-btn" onclick="showTab('tab-ledger', this)">5. Decision Ledger ({len(decisions)}) &amp; Plan</button>
  </div>

  <!-- TAB 1: SCORECARD & RED TEAM -->
  <section id="tab-scorecard" class="tab-panel active">
    <h2 class="section-title">5-Dimension Grilling Scorecard</h2>
    <div class="grid-2">
      {''.join(dim_cards_html)}
    </div>
    <h2 class="section-title">Adversarial Red-Team Critique</h2>
    {critiques_html}
  </section>

  <!-- TAB 2: PRIOR ART & PAIN POINTS -->
  <section id="tab-prior-art" class="tab-panel">
    <h2 class="section-title">GitHub Prior-Art Matrix (Active Incumbents vs. Graveyard / Dormant Repos)</h2>
    <div class="card" style="overflow-x:auto">
      <table>
        <thead>
          <tr>
            <th>Repository</th>
            <th>Stars</th>
            <th>Velocity</th>
            <th>Last Push</th>
            <th>Classification</th>
            <th>Summary</th>
          </tr>
        </thead>
        <tbody>
          {prior_art_table_body}
        </tbody>
      </table>
    </div>

    <h2 class="section-title">Pain-Point Mine (Verified Bugs &amp; Top-Voted Open Issues + Top Comments)</h2>
    <div class="grid-2">
      {pain_points_html}
    </div>
  </section>

  <!-- TAB 3: STACK EXPLAINED, PROJECT MAINTENANCE & MEMORY ARCHITECTURE -->
  <section id="tab-tooling-memory" class="tab-panel">
    <h2 class="section-title">Stack Explained (What Job It Does, Why Needed, Alternative &amp; Now vs. Later)</h2>
    <div class="card" style="overflow-x:auto">
      <table>
        <thead>
          <tr>
            <th>Tool</th>
            <th>Now / Later</th>
            <th>What Job It Does</th>
            <th>Why This Project Needs It</th>
            <th>What the Alternative Was</th>
            <th>Config Proof</th>
          </tr>
        </thead>
        <tbody>
          {tool_rows_html}
        </tbody>
      </table>
    </div>

    <h2 class="section-title">Config Files Proven in Scouted Repos (pyproject.toml, Dockerfile, .github/workflows, .pre-commit-config.yaml)</h2>
    <div class="card" style="overflow-x:auto">
      <table>
        <thead>
          <tr>
            <th>Category</th>
            <th>Tool Proven</th>
            <th>Config File Evidence</th>
            <th>Observed In Scouted Repos</th>
          </tr>
        </thead>
        <tbody>
          {cfg_rows}
        </tbody>
      </table>
    </div>

    <h2 class="section-title">Memory, State &amp; Agent Communication Advisor</h2>
    <div class="card">
      <div class="dim-header">
        <span class="dim-title">Selected Memory Strategy</span>
        <span class="badge badge-green">{mem_strategy}</span>
      </div>
      <p><strong>Agent / Component Communication Pattern:</strong> {mem_comm}</p>
      <p><strong>Workflow Memory Lifecycle:</strong> {mem_flow}</p>
      <p><strong>Why This Memory Architecture (vs. RAG / Vector DB / Alternatives):</strong> {mem_rationale}</p>
      <p class="rejected"><strong>Alternatives Considered:</strong> {mem_alts}</p>
      <h4 style="margin-top:0.85rem">Anticipated Memory Failure Modes &amp; Mitigations</h4>
      {mem_fm_html}
    </div>

    <h2 class="section-title">Scouted Open-Source Building Blocks (GitHub Libraries &amp; SDKs)</h2>
    <div class="card" style="overflow-x:auto">
      <table>
        <thead>
          <tr>
            <th>Repository</th>
            <th>Stars</th>
            <th>License</th>
            <th>Language</th>
            <th>Last Push</th>
            <th>Summary</th>
          </tr>
        </thead>
        <tbody>
          {oss_rows}
        </tbody>
      </table>
    </div>
  </section>

  <!-- TAB 4: SYSTEM DESIGN & MERMAID -->
  <section id="tab-design" class="tab-panel">
    <h2 class="section-title">System Topology Diagram</h2>
    <div class="mermaid-box">
      <pre class="mermaid">{esc(topology_mermaid)}</pre>
      <details class="raw-mermaid">
        <summary>View raw Mermaid source (Note: visual diagram rendering requires internet access for Mermaid CDN)</summary>
        <pre>{esc(topology_mermaid)}</pre>
      </details>
    </div>

    <h2 class="section-title">Core Request Lifecycle (Sequence Diagram)</h2>
    <div class="mermaid-box">
      <pre class="mermaid">{esc(sequence_mermaid)}</pre>
      <details class="raw-mermaid">
        <summary>View raw Mermaid source (Note: visual diagram rendering requires internet access for Mermaid CDN)</summary>
        <pre>{esc(sequence_mermaid)}</pre>
      </details>
    </div>

    <h2 class="section-title">Architecture Trade-Off Matrix</h2>
    <div class="card" style="overflow-x:auto">
      <table>
        <thead>
          <tr>
            <th>Option</th>
            <th>Pros</th>
            <th>Cons</th>
            <th>Verdict</th>
          </tr>
        </thead>
        <tbody>
          {opt_rows}
        </tbody>
      </table>
    </div>
  </section>

  <!-- TAB 5: DECISION LEDGER & IMPLEMENTATION PLAN -->
  <section id="tab-ledger" class="tab-panel">
    <h2 class="section-title">Decision Ledger (Locked ADRs &amp; Rejected Paths)</h2>
    {decisions_html}

    <h2 class="section-title">Implementation Plan</h2>
    <div class="card">
      {steps_html}
    </div>
  </section>
</div>

<script>
  const SPEC_MARKDOWN = {spec_json_escaped};
  if (typeof mermaid !== 'undefined') {{
    mermaid.initialize({{ startOnLoad: true, theme: 'dark', securityLevel: 'loose' }});
  }}
  function showTab(tabId, btn) {{
    document.querySelectorAll('.tab-panel').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    document.getElementById(tabId).classList.add('active');
    btn.classList.add('active');
  }}
  function copySpecMarkdown(btn) {{
    navigator.clipboard.writeText(SPEC_MARKDOWN).then(() => {{
      const orig = btn.textContent;
      btn.textContent = "Copied SPEC.md to Clipboard!";
      setTimeout(() => {{ btn.textContent = orig; }}, 2000);
    }});
  }}
</script>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render PreFlight HTML Blueprint, SPEC.md, and STACK.md")
    parser.add_argument("--workspace", default=".", help="Workspace root directory")
    parser.add_argument("--output", default="blueprint_report.html", help="Output HTML filename")
    parser.add_argument(
        "--spec-output",
        default=".preflight/SPEC.md",
        help="Output Markdown specification path (relative to workspace)",
    )
    parser.add_argument("--force", action="store_true", help="Bypass Readiness Gate check (marks output as DRAFT)")

    args = parser.parse_args(argv)
    workspace = Path(args.workspace).resolve()
    state = load_state(workspace)
    score, unlocked, missing = evaluate_gate(state, workspace)

    if not unlocked and not args.force:
        print(
            f"ERROR: Readiness Gate is LOCKED ({score}% / 80% required).\n"
            "Missing gate requirements:\n"
            + "\n".join(f"  - {m}" for m in missing),
            file=sys.stderr,
        )
        return 2

    sys_design = state.get("system_design") or {}
    topology_mermaid = (sys_design.get("topology_mermaid") or "").strip()
    sequence_mermaid = (sys_design.get("sequence_mermaid") or "").strip()
    if (not topology_mermaid or not sequence_mermaid) and not args.force:
        print(
            "ERROR: `system_design.topology_mermaid` and `system_design.sequence_mermaid` must be populated "
            "via `state.py set-design` before rendering the Blueprint (refusing to render generic placeholder diagrams).",
            file=sys.stderr,
        )
        return 2

    if not topology_mermaid:
        topology_mermaid = "flowchart LR\n    Draft[\"Draft Topology (Pending set-design)\"]"
        sys_design["topology_mermaid"] = topology_mermaid
    if not sequence_mermaid:
        sequence_mermaid = "sequenceDiagram\n    Note over User: Draft Sequence (Pending set-design)"
        sys_design["sequence_mermaid"] = sequence_mermaid

    is_draft = not unlocked
    decisions = load_decisions(workspace)
    prior_art = load_prior_art(workspace)
    spec_md = build_spec_markdown(state, decisions, prior_art, is_draft=is_draft)
    html_content = build_html(state, decisions, prior_art, spec_md)

    out_path = workspace / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_content, encoding="utf-8")

    spec_path = workspace / args.spec_output
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(spec_md + "\n", encoding="utf-8")

    stack_path = workspace / ".preflight" / "STACK.md"
    stack_path.parent.mkdir(parents=True, exist_ok=True)
    stack_path.write_text(build_stack_markdown(state, is_draft=is_draft) + "\n", encoding="utf-8")

    ticket_files = export_tickets_to_dir(workspace, state, decisions, is_draft=is_draft)

    draft_tag = " [DRAFT]" if is_draft else ""
    print(
        f"Blueprint rendered{draft_tag}: {out_path} | Spec exported: {spec_path} | Stack exported: {stack_path} | "
        f"Tickets exported: {len(ticket_files)} in .preflight/issues/ (Readiness: {score}%)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
