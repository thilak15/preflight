---
name: preflight
description: >-
  Pre-implementation architecture validator, GitHub prior-art & OSS building-block scout,
  project maintenance tooling advisor, and memory/agent-communication architect.
  Use when the user wants to validate a new project idea before writing code, run `/preflight`,
  reset/rerun an idea from a clean state, stress-test an architecture across Problem/Scope/Memory/Bottlenecks/Differentiation,
  scout GitHub for Graveyard/Dormant Repos, OSS Building Blocks, and verified Pain Points from open issues,
  recommend project maintenance tooling (Docker, Kubernetes, lockfiles, CI) with alternatives,
  design agent communication and memory workflows (Stateless vs. SQLite/Postgres vs. FTS vs. RAG vs. Vector DB),
  or generate `blueprint_report.html`, `.preflight/SPEC.md`, and `.preflight/STACK.md`.
---

# PreFlight: Pre-Implementation Architecture, Tooling & Prior-Art Validator

PreFlight runs **before** code is written. Instead of acting as a "yes-man", you interrogate the user across five architectural dimensions, scout GitHub for **Active Incumbents**, **Graveyard / Dormant Repos**, **OSS Building Blocks**, and **Pain-Point Mining** from open issues and top-voted comments, recommend **Project Maintenance & Infrastructure Tooling** (with alternatives), prescribe the right **Memory & Agent Communication Workflow** (Stateless vs. Transactional DB vs. Lexical FTS vs. RAG / Vector DB), record locked choices in a **Decision Ledger**, and compile `blueprint_report.html`, `.preflight/SPEC.md`, and `.preflight/STACK.md`.

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

## Fresh Reset / Running a New Idea or Re-Running Cleanly (`reset` / `--reset`)

Whenever the user wants to **run a different idea in the same folder** or **re-run the same idea from a fresh slate**:
- Run `state.py reset` (or pass `--reset` to `state.py init`):
  ```bash
  python3 "$PREFLIGHT_SCRIPTS/state.py" --workspace . reset
  ```
- This deletes all pre-performed dimension scores, `.preflight/state.json`, `.preflight/decisions.json`, `.preflight/prior-art.json`, `.preflight/SPEC.md`, `.preflight/STACK.md`, `blueprint_report.html`, and generated `docs/adr/NNNN-*.md` files while keeping `.preflight/cache.db` so GitHub API rate limits aren't wasted (pass `--purge-cache` to also wipe `cache.db`).

---

## The 5 Grilling Dimensions & Evidence-Based Readiness Gate

Every project is scored across five dimensions (`20%` each, `0%–100%` total). `state.py` enforces **strict programmatic evidence rules** — self-certifying `20/20` with a one-liner or scoring `differentiation` before running `scout.py` will fail with exit code `2`:

| Key | Dimension | `0` (Untouched) | `10` (Surface) | `20` (Stress-Tested — Programmatically Enforced) |
| :--- | :--- | :--- | :--- | :--- |
| `problem` | **Problem & User Pain** | Unstated | General pitch stated | Summary $\ge 40$ chars + $\ge 2$ `--edge-case` scenarios locked |
| `scope` | **Scope & Non-Goals** | Unbounded | High-level features listed | Summary $\ge 40$ chars + $\ge 2$ explicit boundary `--edge-case` items |
| `memory` | **State, Memory & Agent Communication** | Unknown | Storage engine named | Summary $\ge 40$ chars + $\ge 2$ state/cache/context `--edge-case` items |
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

### Step 1: Initialize Working State (or Reset) & Launch Round 1 Grilling

When the user pitches an idea or invokes `/preflight`:

1. Initialize `.preflight/state.json` (pass `--reset` if starting a new idea or re-running from scratch):
   ```bash
   python3 "$PREFLIGHT_SCRIPTS/state.py" --workspace . init --reset \
     --name "<Project Name>" \
     --summary "<1-2 sentence summary>" \
     --runtime "<Target Runtime>" \
     --stack "<Comma-separated stack>"
   ```
2. Seed `GLOSSARY.md` at the workspace root if it does not exist yet.
3. Ask **Round 1** of the **Grilling Session** (3–4 frontier questions covering `problem`, `scope`, initial `memory` & agent communication needs, and `bottlenecks`), each with a concrete `➡️` recommended answer.

**Completion Criterion**: `.preflight/state.json` exists and Round 1 frontier questions are presented to the user.

---

### Step 2: Run the GitHub Prior-Art, Pain-Point & OSS Building-Block Scout

As soon as the core problem is clear (after Round 1, or immediately if the user provided a detailed spec):

1. Craft 3–4 competitor queries (`-q`) **and** 2–3 open-source library/tooling queries (`-t` / `--tool-query`) for the libraries/SDKs needed to build the project.
2. Run `scout.py`:
   ```bash
   python3 "$PREFLIGHT_SCRIPTS/scout.py" --workspace . \
     -q "<competitor query 1>" \
     -q "<competitor query 2>" \
     -t "<oss building block query 1>" \
     -t "<oss building block query 2>"
   ```
   `scout.py` authenticates via `gh auth token` $\to$ `GITHUB_TOKEN` $\to$ unauthenticated fallback, caches responses in `.preflight/cache.db` (SQLite3, 7-day TTL), writes `.preflight/prior-art.json`, and outputs:
   - **Active Incumbents** (pushed within 365 days, with monthly star velocity)
   - **Graveyard / Dormant Repos** (archived or $>365\text{d}$ without pushes)
   - **Scouted OSS Building Blocks** (actively maintained open-source libraries/tools with license & star velocity)
   - **Verified Pain Points** (Pass A: top `+1` open issues; Pass B: `label:bug` open issues; includes `top_comments` from issue threads)

**Completion Criterion**: `.preflight/prior-art.json` is populated with both competitors and OSS building blocks.

---

### Step 3: "Stack Explained" (Config-Verified Tooling, Now vs. Later) & Memory Architecture

For every idea, you must produce a **"Stack Explained"** breakdown grounded in the config files `scout.py` discovered across incumbent repos (`pyproject.toml` for Poetry/uv, `Dockerfile` for Docker, `.github/workflows` for GitHub Actions, `.pre-commit-config.yaml` for pre-commit, etc.) **and** prescribe the Memory & Agent Communication workflow:

#### A. "Stack Explained" (`state.py add-tool`)
Produce one concise entry per tool answering four exact questions:
1. **What job it does** (`--purpose`)
2. **Why this project needs it now** (`--why`)
3. **What the alternative was** (`--alternatives`)
4. **Whether it is `now` or `later`** (`--stage now|later`) + the config file that proves it (`--config-proof`)

```bash
python3 "$PREFLIGHT_SCRIPTS/state.py" --workspace . add-tool \
  --category <dependency-lock|container-runtime|orchestration-deploy|ci-cd-quality|core-oss|storage-memory|observability> \
  --recommended "<Tool name, e.g. uv (uv.lock), Docker, GitHub Actions, pre-commit, Kubernetes>" \
  --stage <now|later> \
  --purpose "<What job it does>" \
  --why "<Why this project needs it now (or why deferred until later)>" \
  --alternatives "<What the alternative was and why it wasn't chosen>" \
  --config-proof "<Config file proving usage, e.g. pyproject.toml ([tool.uv]), Dockerfile, .github/workflows, .pre-commit-config.yaml>"
```
Always include entries for:
- **Dependency Locking** (`pyproject.toml` / `uv.lock` / `poetry.lock` / `Cargo.lock`) — usually `now`.
- **Code Quality & CI** (`.pre-commit-config.yaml`, `.github/workflows`) — usually `now`.
- **Containerization** (`Dockerfile` / `docker-compose.yml`) — `now` or `later` depending on runtime.
- **Orchestration at Scale** (`Kubernetes` / `Chart.yaml` / `k8s/`) — explicitly mark `later` when a single binary or Docker Compose suffices for V1!

#### B. Memory, State & Agent Communication Advisor (`state.py set-memory-arch`)
Evaluate how agents or components should communicate and what memory architecture fits best—do **not** default to a Vector DB or RAG unless unstructured semantic retrieval actually requires it:
- `stateless`: Pure CLI/utility or deterministic transform (avoid unnecessary DB overhead).
- `transactional-db`: Structured relational/embedded state (`SQLite WAL` / `PostgreSQL`) with typed schemas.
- `lexical-fts`: Exact-match/identifier/code/log search (`SQLite FTS5`, `BM25`, `Postgres tsvector`).
- `rag-vector-db`: Unstructured semantic retrieval (`pgvector`, `Qdrant`, `LanceDB`) when semantic similarity over large corpora is mandatory.
- `hybrid-search`: Combined lexical (`BM25`/`FTS5`) + vector embeddings with Reciprocal Rank Fusion.
- `episodic-agent-state`: Multi-step agent workflow using structured handoff checkpoints + compacted episodic state to prevent context rot.

Record the memory architecture and its specific failure modes:
```bash
python3 "$PREFLIGHT_SCRIPTS/state.py" --workspace . set-memory-arch \
  --strategy <stateless|transactional-db|lexical-fts|rag-vector-db|hybrid-search|episodic-agent-state> \
  --communication "<How agents/components communicate and pass state (e.g., typed JSON handoff schemas, MCP, event queue)>" \
  --workflow "<How memory is read, written, compacted, and invalidated across the workflow>" \
  --rationale "<Why this memory strategy beats RAG/Vector DB or other alternatives for this idea>" \
  --alternatives "<Rejected memory options (e.g. pure Vector DB, uncompacted chat history) and why>" \
  --failure-mode "<Memory Failure Mode 1 (e.g. context window bloat, chunk boundary loss, stale cache) + mitigation>" \
  --failure-mode "<Memory Failure Mode 2 + mitigation>"
```
This automatically generates `.preflight/STACK.md` and populates Tab 3 of `blueprint_report.html`.

---

### Step 4: Challenge with Prior-Art Evidence & Update the Decision Ledger

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

### Step 5: Set System Design, Render Blueprint & Export Ordered Tickets (`.preflight/issues/`)

Once the **Readiness Gate** is unlocked:

1. Populate the Mermaid diagrams, trade-off matrix, and ordered vertical-slice implementation steps via `state.py set-design`:
   ```bash
   python3 "$PREFLIGHT_SCRIPTS/state.py" --workspace . set-design \
     --topology "flowchart TD ..." \
     --sequence "sequenceDiagram ..." \
     --option "Option A|Pros|Cons|Selected (ADR-0001)" \
     --option "Option B|Pros|Cons|Rejected" \
     --step "Step 1: ..." \
     --step "Step 2: ..."
   ```
2. Render the Blueprint, Specification, Stack Document, and **individual dependency-ordered issue files** (`.preflight/issues/01-<slug>.md`, `02-<slug>.md`, ..., plus `.preflight/issues/INDEX.md`):
   ```bash
   python3 "$PREFLIGHT_SCRIPTS/render_blueprint.py" --workspace . \
     --output blueprint_report.html \
     --spec-output .preflight/SPEC.md
   ```
   *(You can also run `python3 "$PREFLIGHT_SCRIPTS/state.py" --workspace . export-tickets` standalone at any time to regenerate `.preflight/issues/NN-<slug>.md`.)*
3. Present links to:
   - `blueprint_report.html`
   - `.preflight/SPEC.md` and `.preflight/STACK.md`
   - `.preflight/issues/INDEX.md` (and the individual `01-...md`, `02-...md` tickets)
   - `GLOSSARY.md` and `docs/adr/`
4. **Code One-by-One in Exact Dependency Order (Handoff to Implementation)**:
   Offer the user two ways to code the generated tickets in order:
   - **Option A — One Ticket at a Time**: Work through `.preflight/issues/01-<slug>.md`, `02-<slug>.md`, ... sequentially (one vertical slice per context window), writing tests first and verifying each ticket's acceptance criteria before moving to the next.
   - **Option B — Parallel Task-Graph Build**: Use background implementer subagents to execute unblocked tickets in `.preflight/issues/INDEX.md` in dependency order and merge them onto an integration branch.
