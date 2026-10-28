#!/usr/bin/env python3
"""
PreFlight Aesthetic Blueprint Generator (`scripts/render_blueprint.py`).

Reads:
- `.preflight/state.json` (Working State, 5-dimension Readiness Scorecard, Red-Team Critiques, System Design)
- `.preflight/decisions.json` (Decision Ledger / ADRs)
- `.preflight/prior-art.json` (Active Incumbents, Graveyard Repos, Mined Pain Points)

Enforces the Readiness Gate (>=80% and no 0% dimensions, unless `--force` or `forced_unlock=True`)
and renders a standalone, dark-mode `blueprint_report.html` dashboard with interactive Mermaid.js diagrams.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any

from state import DIMENSIONS, DIMENSION_LABELS, compute_readiness, load_decisions, load_state


def esc(val: Any) -> str:
    return html.escape(str(val or ""))


def load_prior_art(workspace: Path) -> dict[str, Any]:
    path = workspace / ".preflight" / "prior-art.json"
    if not path.exists():
        return {"active_incumbents": [], "graveyard_repos": [], "pain_points": [], "queries": []}
    return json.loads(path.read_text(encoding="utf-8"))


def default_topology_mermaid(project_name: str) -> str:
    return f"""flowchart TD
    User(["Developer / User"]) --> Entry["{project_name} Interface"]
    Entry --> Core["Core Orchestration Engine"]
    Core --> State[("Working State & Decision Ledger")]
    Core --> Scout["Prior-Art & Pain-Point Scout"]
    Scout --> Cache[("SQLite Repo Cache")]
    Core --> Blueprint["Blueprint Renderer"]
"""


def default_sequence_mermaid(project_name: str) -> str:
    return f"""sequenceDiagram
    actor Dev as Developer
    participant PF as {project_name}
    participant Scout as GitHub Deep-Scout
    participant Ledger as Decision Ledger
    Dev->>PF: Pitch initial idea
    PF->>Dev: Round 1 Socratic Grilling
    Dev->>PF: Round 1 Answers
    par Async Prior-Art Scouting
        PF->>Scout: Execute targeted repo & issue queries
        Scout-->>PF: Active Incumbents, Graveyard Repos, Pain Points
    and Round 2+ Grilling
        PF->>Dev: Challenge with Mined Pain Points & Edge Cases
        Dev->>Ledger: Lock ADRs & Rejected Options
    end
    Ledger->>PF: Readiness Gate >= 80% Unlocked
    PF-->>Dev: Render standalone blueprint_report.html
"""


def build_html(
    state: dict[str, Any],
    decisions: list[dict[str, Any]],
    prior_art: dict[str, Any],
) -> str:
    project_name = esc(state.get("project_name") or "Untitled Project")
    project_summary = esc(state.get("project_summary") or "No project summary provided.")
    runtime = esc(state.get("target_runtime") or "Unspecified Runtime")
    stack_items = state.get("tech_stack") or []
    readiness_score, unlocked = compute_readiness(state)

    gate_badge_color = "#10b981" if unlocked else "#f59e0b"
    gate_badge_text = "READINESS GATE PASSED" if unlocked else "FORCED OVERRIDE / DRAFT"

    # 1. Dimension Cards
    dim_cards_html = []
    for dim in DIMENSIONS:
        d = state.get("dimensions", {}).get(dim, {})
        label = esc(d.get("label") or DIMENSION_LABELS[dim])
        score = int(d.get("score", 0))
        pct = score * 5  # out of 100% for bar width
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
        critiques_html = '<div class="card"><p class="muted">No red-team critiques recorded yet.</p></div>'

    # 3. Prior-Art Matrix & Pain-Point Mine
    incumbents = prior_art.get("active_incumbents") or []
    graveyard = prior_art.get("graveyard_repos") or []
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
                <td><span class="badge badge-red">Graveyard ({esc(r.get('graveyard_reason') or '>365d inactive')})</span></td>
                <td>{esc(r.get('description'))}</td>
            </tr>
            """
        )
    prior_art_table_body = "".join(inc_rows) or '<tr><td colspan="6" class="muted">No repositories scouted yet.</td></tr>'

    pp_cards = []
    for p in pain_points[:12]:
        pp_cards.append(
            f"""
            <div class="card pp-card">
                <div class="pp-header">
                    <a href="{esc(p.get('issue_url'))}" target="_blank" rel="noopener" class="pp-link">
                        {esc(p.get('repo_full_name'))}#{int(p.get('issue_number', 0))}
                    </a>
                    <span class="pp-Metric">👍 {int(p.get('reactions_plus_one', 0))} &nbsp;|&nbsp; 💬 {int(p.get('comments_count', 0))}</span>
                </div>
                <h4>{esc(p.get('title'))}</h4>
                <p class="muted">{esc(p.get('body_excerpt') or 'No body excerpt.')}</p>
            </div>
            """
        )
    pain_points_html = "".join(pp_cards) or '<div class="card"><p class="muted">No open issue pain points mined yet.</p></div>'

    # 4. System Design & Mermaid
    sys_design = state.get("system_design") or {}
    topology_mermaid = (sys_design.get("topology_mermaid") or "").strip() or default_topology_mermaid(
        state.get("project_name") or "PreFlight"
    )
    sequence_mermaid = (sys_design.get("sequence_mermaid") or "").strip() or default_sequence_mermaid(
        state.get("project_name") or "PreFlight"
    )
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
        steps_html = """
        <ol class="step-list">
            <li>Run <code>/to-spec</code> to publish the finalized specification from this Blueprint.</li>
            <li>Run <code>/to-tickets</code> to slice the spec into vertical tracer-bullet tickets with blocking edges.</li>
            <li>Execute each vertical slice with <code>/implement</code> and <code>/tdd</code> (red-green-refactor).</li>
        </ol>
        """

    stack_badges = "".join(f'<span class="stack-pill">{esc(s)}</span>' for s in stack_items) or '<span class="stack-pill">TBD</span>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>PreFlight Blueprint — {project_name}</title>
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
    min-width: 220px;
  }}
  .score-number {{ font-size: 2.5rem; font-weight: 800; color: {gate_badge_color}; line-height: 1.1; }}
  .score-label {{ font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); }}
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
  .mermaid-box {{
    background: #0f172a;
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1.5rem;
    overflow-x: auto;
    margin-top: 0.75rem;
  }}
  .step-list {{ padding-left: 1.4rem; }}
  .step-list li {{ margin-bottom: 0.6rem; }}
  h2.section-title {{ font-size: 1.35rem; margin: 1.25rem 0 0.75rem; color: #e2e8f0; }}
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="title-group">
      <div class="score-label">PREFLIGHT ARCHITECTURE &amp; PRIOR-ART BLUEPRINT</div>
      <h1>{project_name}</h1>
      <p>{project_summary}</p>
      <div class="meta-row">
        <span class="stack-pill">Runtime: {runtime}</span>
        {stack_badges}
      </div>
    </div>
    <div class="score-box">
      <div class="score-label">{gate_badge_text}</div>
      <div class="score-number">{readiness_score}%</div>
      <div class="muted">5-Dimension Rubric</div>
    </div>
  </header>

  <div class="tabs">
    <button class="tab-btn active" onclick="showTab('tab-scorecard', this)">1. Readiness &amp; Red-Team</button>
    <button class="tab-btn" onclick="showTab('tab-prior-art', this)">2. Prior-Art &amp; Pain Points ({len(incumbents) + len(graveyard)})</button>
    <button class="tab-btn" onclick="showTab('tab-design', this)">3. System Topology &amp; Sequence</button>
    <button class="tab-btn" onclick="showTab('tab-ledger', this)">4. Decision Ledger ({len(decisions)}) &amp; Next Steps</button>
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
    <h2 class="section-title">GitHub Prior-Art Matrix (Active Incumbents vs. Graveyard Repos)</h2>
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

    <h2 class="section-title">Pain-Point Mine (Top-Voted Open Issues from Incumbents)</h2>
    <div class="grid-2">
      {pain_points_html}
    </div>
  </section>

  <!-- TAB 3: SYSTEM DESIGN & MERMAID -->
  <section id="tab-design" class="tab-panel">
    <h2 class="section-title">System Topology Diagram</h2>
    <div class="mermaid-box">
      <pre class="mermaid">{esc(topology_mermaid)}</pre>
    </div>

    <h2 class="section-title">Core Request Lifecycle (Sequence Diagram)</h2>
    <div class="mermaid-box">
      <pre class="mermaid">{esc(sequence_mermaid)}</pre>
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

  <!-- TAB 4: DECISION LEDGER & IMPLEMENTATION PLAN -->
  <section id="tab-ledger" class="tab-panel">
    <h2 class="section-title">Decision Ledger (Locked ADRs &amp; Rejected Paths)</h2>
    {decisions_html}

    <h2 class="section-title">Tracer-Bullet Implementation Plan &amp; Handoff</h2>
    <div class="card">
      {steps_html}
    </div>
  </section>
</div>

<script>
  mermaid.initialize({{ startOnLoad: true, theme: 'dark', securityLevel: 'loose' }});
  function showTab(tabId, btn) {{
    document.querySelectorAll('.tab-panel').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    document.getElementById(tabId).classList.add('active');
    btn.classList.add('active');
  }}
</script>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render PreFlight HTML Blueprint")
    parser.add_argument("--workspace", default=".", help="Workspace root directory")
    parser.add_argument("--output", default="blueprint_report.html", help="Output HTML filename")
    parser.add_argument("--force", action="store_true", help="Bypass Readiness Gate check")

    args = parser.parse_args(argv)
    workspace = Path(args.workspace).resolve()
    state = load_state(workspace)
    score, unlocked = compute_readiness(state)

    if not unlocked and not args.force:
        zero_dims = [
            d for d in DIMENSIONS if int(state.get("dimensions", {}).get(d, {}).get("score", 0)) == 0
        ]
        print(
            f"ERROR: Readiness Gate is LOCKED ({score}% / 80% required; untouched dimensions: {zero_dims}).\n"
            "Complete the Grilling Session across all 5 dimensions or pass `--force` if the user explicitly requested an early override.",
            file=sys.stderr,
        )
        return 2

    decisions = load_decisions(workspace)
    prior_art = load_prior_art(workspace)
    html_content = build_html(state, decisions, prior_art)

    out_path = workspace / args.output
    out_path.write_text(html_content, encoding="utf-8")
    print(f"Blueprint rendered successfully: {out_path} (Readiness: {score}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
