---
name: preflight
description: >-
  Adversarial pre-implementation architecture validator and GitHub prior-art scout.
  Use when the user wants to validate a new project idea before writing code, run `/preflight`,
  stress-test an architecture across Problem/Scope/Memory/Bottlenecks/Differentiation,
  scout GitHub for Graveyard Repos and Mined Pain Points from open issues, or generate a
  visual `blueprint_report.html` system design blueprint.
---

# PreFlight: Adversarial Architecture & Prior-Art Swarm

PreFlight runs **before** code is written. Instead of acting as a "yes-man", you interrogate the user across five architectural dimensions, scout GitHub for **Active Incumbents**, **Graveyard Repos**, and **Pain-Point Mining** from open issues, record locked choices in a **Decision Ledger**, and render a standalone dark-mode `blueprint_report.html` **Blueprint**.

Also activate the `grilling` and `domain-modeling` disciplines during every PreFlight session:
- Format every interview round using numbered frontier questions (`❓ **Q1** ... ➡️ <recommended answer>`), worded so `"yes"` accepts the recommendation.
- Maintain `GLOSSARY.md` at the workspace root inline as domain terms crystallise.

---

## The 5 Grilling Dimensions & Readiness Gate

Every project is scored across five dimensions (`20%` each, `0%–100%` total):

| Key | Dimension | `0` (Untouched) | `10` (Surface) | `20` (Stress-Tested) |
| :--- | :--- | :--- | :--- | :--- |
| `problem` | **Problem & User Pain** | Unstated | General pitch stated | Concrete failure mode of status quo + target user workflow locked |
| `scope` | **Scope & Non-Goals** | Unbounded | High-level features listed | Explicit V1 non-goals + hard boundary seams locked |
| `memory` | **State & Persistence (Memory)** | Unknown | Storage engine named | Schema/lifecycle, caching, and (for AI apps) context/episodic memory locked |
| `bottlenecks` | **Bottlenecks & Failure Modes** | Ignored | Happy-path assumed | Rate limits, latency, single points of failure, and mitigations stress-tested |
| `differentiation` | **Prior-Art Differentiation** | Unchecked | Self-claimed uniqueness | Directly contrasted against scouted **Active Incumbents**, **Graveyard Repos**, and mined GitHub issue pain points |

**Readiness Gate Rule**: Blueprint generation is **LOCKED** until total readiness is **$\ge 80\%$** with **no dimension at `0`**, unless the user explicitly says `"force blueprint"`.

---

## Execution Process

### Step 1: Initialize Working State & Launch Round 1 Grilling

When the user pitches an idea or invokes `/preflight`:

1. Initialize `.preflight/state.json` via [state.py](./scripts/state.py):
   ```bash
   python3 ~/.gemini/config/skills/preflight/scripts/state.py --workspace . init \
     --name "<Project Name>" \
     --summary "<1-2 sentence summary>" \
     --runtime "<Target Runtime>" \
     --stack "<Comma-separated stack>"
   ```
2. Seed `GLOSSARY.md` at the workspace root if it does not exist yet.
3. Ask **Round 1** of the **Grilling Session** (3–5 frontier questions covering `problem`, `scope`, and initial `memory`/`bottlenecks` assumptions), always providing a sharp `➡️` recommended answer for each.

**Completion Criterion**: `.preflight/state.json` exists and Round 1 frontier questions are presented to the user.

---

### Step 2: Run the Asynchronous GitHub Prior-Art Scout

As soon as the core problem is clear (right after Round 1, or immediately if the user gave a detailed spec upfront):

1. Craft 3–5 targeted GitHub search queries covering the problem domain and technical mechanism.
2. Run [scout.py](./scripts/scout.py) (use `run_command` or delegate to a background `research` subagent so you don't block):
   ```bash
   python3 ~/.gemini/config/skills/preflight/scripts/scout.py --workspace . \
     -q "<query 1>" \
     -q "<query 2>" \
     -q "<query 3>"
   ```
   `scout.py` authenticates via `gh auth token` $\to$ `GITHUB_TOKEN` $\to$ unauthenticated fallback, caches responses in `.preflight/cache.db` (SQLite3, 7-day TTL), writes `.preflight/prior-art.json`, and prints a Markdown digest of:
   - **Active Incumbents** (pushed within 365 days, with star velocity/month)
   - **Graveyard Repos** (inactive $>365$ days or archived)
   - **Pain-Point Mining** (top-voted `+1` open issues across incumbents)

**Completion Criterion**: `.preflight/prior-art.json` and `.preflight/cache.db` are populated, and you have reviewed the digest.

---

### Step 3: Challenge with Prior-Art Evidence & Update the Decision Ledger

In Round 2 and subsequent rounds:

1. **Use Scout Findings as Live Ammunition**:
   - Cite specific **Graveyard Repos** and ask how the user's design avoids stalling for the same reason.
   - Cite top-voted open issues from **Active Incumbents** (**Pain-Point Mining**) and ask how the user's architecture solves those exact user complaints.
2. **Update Rubric & Decision Ledger after each round**:
   - Update dimension scores (`0`, `10`, `20`) and edge cases:
     ```bash
     python3 ~/.gemini/config/skills/preflight/scripts/state.py --workspace . update-dimension \
       --dimension <problem|scope|memory|bottlenecks|differentiation> \
       --score <0|10|20> \
       --summary "<Locked understanding>" \
       --edge-case "<Stress-tested scenario>"
     ```
   - Record adversarial critiques uncovered during grilling:
     ```bash
     python3 ~/.gemini/config/skills/preflight/scripts/state.py --workspace . add-critique \
       --title "<Risk title>" \
       --severity <critical|high|medium> \
       --attack "<How it fails under stress>" \
       --mitigation "<Architectural mitigation>"
     ```
   - Record locked architectural decisions (writes both `.preflight/decisions.json` and `docs/adr/NNNN-<slug>.md`):
     ```bash
     python3 ~/.gemini/config/skills/preflight/scripts/state.py --workspace . add-decision \
       --title "<Short Decision Title>" \
       --decision "<What we decided>" \
       --rejected "<What alternatives were rejected>" \
       --rationale "<Why we chose this path>" \
       --dimension <dimension>
     ```
3. Display the current Readiness Scorecard (`state.py status`) at the start of each round so the user sees progress toward the `80%` gate.

**Completion Criterion**: Readiness Gate reaches $\ge 80\%$ with zero untouched (`0`) dimensions (or user explicitly requests `force-unlock`).

---

### Step 4: Populate System Design Diagrams & Render `blueprint_report.html`

Once the **Readiness Gate** is unlocked:

1. Update `.preflight/state.json`'s `system_design` block with project-specific:
   - `topology_mermaid`: `flowchart TD` or `flowchart LR` showing component boundaries and data stores.
   - `sequence_mermaid`: `sequenceDiagram` showing the primary request/execution lifecycle.
   - `options_matrix`: list of `{ "option": "...", "pros": "...", "cons": "...", "verdict": "..." }`.
   - `implementation_steps`: ordered tracer-bullet build steps.
2. Run [render_blueprint.py](./scripts/render_blueprint.py):
   ```bash
   python3 ~/.gemini/config/skills/preflight/scripts/render_blueprint.py --workspace . --output blueprint_report.html
   ```
3. Present a link to `[blueprint_report.html](file:///.../blueprint_report.html)`, `[GLOSSARY.md](file:///.../GLOSSARY.md)`, and `[docs/adr/](file:///.../docs/adr/)`.
4. **Downstream Handoff**: Offer to immediately run `/to-spec` and `/to-tickets` (followed by `/implement` + `/tdd`) to turn the Blueprint into vertical tracer-bullet tickets.
