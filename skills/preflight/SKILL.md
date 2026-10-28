---
name: preflight
description: >-
  Pre-implementation architecture validator and GitHub prior-art scout.
  Use when the user wants to validate a new project idea before writing code, run `/preflight`,
  stress-test an architecture across Problem/Scope/Memory/Bottlenecks/Differentiation,
  scout GitHub for Graveyard/Dormant Repos and verified Pain Points from open issues and comments,
  or generate a visual `blueprint_report.html` and `.preflight/SPEC.md` system design specification.
---

# PreFlight: Pre-Implementation Architecture & Prior-Art Validator

PreFlight runs **before** code is written. Instead of acting as a "yes-man", you interrogate the user across five architectural dimensions, scout GitHub for **Active Incumbents**, **Graveyard / Dormant Repos**, and **Pain-Point Mining** from open issues and top-voted comments, record locked choices in a **Decision Ledger**, and compile a dark-mode `blueprint_report.html` **Blueprint** alongside a clean `.preflight/SPEC.md` specification.

## Interview & Domain Discipline (Self-Contained)

1. **Frontier Interview Rounds**:
   - Map the architecture as a **design tree** where each settled decision unblocks downstream questions.
   - Ask all currently unblocked questions in a single numbered round (`❓ **Q1** - **<Title>**: <Body> \n\n ➡️ <Recommended answer>`), worded so `"yes"` accepts your recommendation.
2. **Inline Domain Glossary (`GLOSSARY.md`)**:
   - Maintain `GLOSSARY.md` at the workspace root as domain terms crystallize (`**<Term>**: <1-2 sentence definition>\n_Avoid_: <synonyms>`).

---

## Script Path Resolution

Resolve `PREFLIGHT_SCRIPTS` to the `scripts/` folder adjacent to this `SKILL.md` file (for example `.agents/skills/preflight/scripts`, `skills/preflight/scripts`, or `~/.gemini/config/skills/preflight/scripts`):

```bash
for d in "./skills/preflight/scripts" "./.agents/skills/preflight/scripts" "$HOME/.gemini/config/skills/preflight/scripts" "$HOME/.claude/skills/preflight/scripts"; do
  [ -d "$d" ] && PREFLIGHT_SCRIPTS="$d" && break
done
```

---

## The 5 Grilling Dimensions & Evidence-Based Readiness Gate

Every project is scored across five dimensions (`20%` each, `0%–100%` total). `state.py` enforces **strict programmatic evidence rules** — self-certifying `20/20` with a one-liner or scoring `differentiation` before running `scout.py` will fail with exit code `2`:

| Key | Dimension | `0` (Untouched) | `10` (Surface) | `20` (Stress-Tested — Programmatically Enforced) |
| :--- | :--- | :--- | :--- | :--- |
| `problem` | **Problem & User Pain** | Unstated | General pitch stated | Summary $\ge 40$ chars + $\ge 2$ `--edge-case` scenarios locked |
| `scope` | **Scope & Non-Goals** | Unbounded | High-level features listed | Summary $\ge 40$ chars + $\ge 2$ explicit boundary `--edge-case` items |
| `memory` | **State & Persistence (Memory)** | Unknown | Storage engine named | Summary $\ge 40$ chars + $\ge 2$ state/cache/lifecycle `--edge-case` items |
| `bottlenecks` | **Bottlenecks & Failure Modes** | Ignored | Happy-path assumed | Summary $\ge 40$ chars + $\ge 2$ rate-limit/latency/SPOF `--edge-case` items |
| `differentiation` | **Prior-Art Differentiation** | Unchecked | Contrasted against scouted repos | Requires `.preflight/prior-art.json` from `scout.py`, $\ge 2$ edge cases, and must explicitly cite at least one discovered `owner/repo` |

**Readiness Gate Requirements (`evaluate_gate`)**:
`render_blueprint.py` refuses to render a passed Blueprint until **all** of the following hold:
1. Total score $\ge 80\%$ with **zero** dimensions at `0%`.
2. `.preflight/prior-art.json` exists and contains scouted repositories from `scout.py`.
3. At least **1 Architecture Decision Record** (`add-decision`) is recorded in `.preflight/decisions.json` and `docs/adr/`.
4. At least **1 Adversarial Red-Team Critique** (`add-critique`) is recorded.
5. Both `topology_mermaid` and `sequence_mermaid` are populated via `state.py set-design`.

---

## Execution Process

### Step 1: Initialize Working State & Launch Round 1 Grilling

When the user pitches an idea or invokes `/preflight`:

1. Initialize `.preflight/state.json`:
   ```bash
   python3 "$PREFLIGHT_SCRIPTS/state.py" --workspace . init \
     --name "<Project Name>" \
     --summary "<1-2 sentence summary>" \
     --runtime "<Target Runtime>" \
     --stack "<Comma-separated stack>"
   ```
2. Seed `GLOSSARY.md` at the workspace root if it does not exist yet.
3. Ask **Round 1** of the **Grilling Session** (3–4 frontier questions covering `problem`, `scope`, and initial `memory`/`bottlenecks` assumptions), each with a concrete `➡️` recommended answer.

**Completion Criterion**: `.preflight/state.json` exists and Round 1 frontier questions are presented to the user.

---

### Step 2: Run the GitHub Prior-Art & Pain-Point Scout

As soon as the core problem is clear (after Round 1, or immediately if the user provided a detailed spec):

1. Craft 3–5 targeted GitHub search queries covering the problem domain, alternative names, and technical mechanism.
2. Run `scout.py`:
   ```bash
   python3 "$PREFLIGHT_SCRIPTS/scout.py" --workspace . \
     -q "<query 1>" \
     -q "<query 2>" \
     -q "<query 3>"
   ```
   `scout.py` authenticates via `gh auth token` $\to$ `GITHUB_TOKEN` $\to$ unauthenticated fallback, inspects GitHub Search API rate-limit headers (`30 req/min` authenticated, `10 req/min` unauthenticated), caches responses in `.preflight/cache.db` (SQLite3, 7-day TTL), writes `.preflight/prior-art.json`, and outputs:
   - **Active Incumbents** (pushed within 365 days, with monthly star velocity)
   - **Graveyard / Dormant Repos** (archived or $>365\text{d}$ without pushes)
   - **Verified Pain Points** (Pass A: top `+1` open issues; Pass B: `label:bug` open issues; minimum engagement filter enforced; includes `top_comments` from issue threads)

**Completion Criterion**: `.preflight/prior-art.json` is populated and you have reviewed the discovered incumbents, graveyard repos, and issue comments.

---

### Step 3: Challenge with Prior-Art Evidence & Update the Decision Ledger

In Round 2 and subsequent rounds:

1. **Challenge with Mined Evidence**:
   - Cite specific **Active Incumbents** and **Graveyard Repos** by `owner/repo`.
   - Quote specific `🐛 BUG/FAILURE` or `🔥 TOP-VOTED` issues and `@author` comments from `scout.py`, and ask how the user's architecture avoids or solves those exact failure modes.
2. **Update Rubric, Critiques, and ADRs after each round**:
   - Update dimension scores (`0`, `10`, `20`) with substantive summaries and $\ge 2$ `--edge-case` flags:
     ```bash
     python3 "$PREFLIGHT_SCRIPTS/state.py" --workspace . update-dimension \
       --dimension <problem|scope|memory|bottlenecks|differentiation> \
       --score <0|10|20> \
       --summary "<Detailed architectural explanation (>=40 chars)>" \
       --edge-case "<Concrete edge case 1>" \
       --edge-case "<Concrete edge case 2>"
     ```
   - Record adversarial critiques uncovered during grilling:
     ```bash
     python3 "$PREFLIGHT_SCRIPTS/state.py" --workspace . add-critique \
       --title "<Risk title>" \
       --severity <critical|high|medium> \
       --attack "<How it fails under stress>" \
       --mitigation "<Architectural mitigation>"
     ```
   - Record locked architectural decisions (writes both `.preflight/decisions.json` and `docs/adr/NNNN-<slug>.md`):
     ```bash
     python3 "$PREFLIGHT_SCRIPTS/state.py" --workspace . add-decision \
       --title "<Short Decision Title>" \
       --decision "<What we decided>" \
       --rejected "<What alternatives were rejected>" \
       --rationale "<Why we chose this path>" \
       --dimension <dimension>
     ```
3. Display the Readiness Scorecard (`state.py status`) at each round.

**Completion Criterion**: All gate requirements in `state.py status` are satisfied (`UNLOCKED`).

---

### Step 4: Set System Design & Render `blueprint_report.html` + `.preflight/SPEC.md`

Once the **Readiness Gate** is unlocked:

1. Populate the Mermaid diagrams, trade-off matrix, and implementation steps via `state.py set-design`:
   ```bash
   python3 "$PREFLIGHT_SCRIPTS/state.py" --workspace . set-design \
     --topology "flowchart TD ..." \
     --sequence "sequenceDiagram ..." \
     --option "Option A|Pros|Cons|Selected (ADR-0001)" \
     --option "Option B|Pros|Cons|Rejected" \
     --step "Step 1: ..." \
     --step "Step 2: ..."
   ```
2. Render the Blueprint and Markdown specification:
   ```bash
   python3 "$PREFLIGHT_SCRIPTS/render_blueprint.py" --workspace . \
     --output blueprint_report.html \
     --spec-output .preflight/SPEC.md
   ```
3. Present links to `blueprint_report.html`, `.preflight/SPEC.md`, `GLOSSARY.md`, and `docs/adr/`.
