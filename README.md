<div align="center">

# ✈️ PreFlight

**Validate your architecture, scout GitHub prior art, lock your stack, and generate ready-to-code tickets — before writing a single line of code.**

[![CI](https://github.com/thilak15/preflight/actions/workflows/ci.yml/badge.svg)](https://github.com/thilak15/preflight/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Dependencies](https://img.shields.io/badge/Dependencies-Zero%20(Stdlib%20Only)-10b981)](#1-install)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)

[**What It Does**](#-what-preflight-does) · [**Quick Start**](#-quick-start) · [**5-Dimension Gate**](#-the-5-dimension-readiness-gate) · [**Generated Artifacts**](#-what-gets-generated) · [**Case Study**](./examples/edge-cron-scheduler/CASE_STUDY.md) · [**CLI Reference**](#-cli-reference) · [**Changelog**](./CHANGELOG.md)

</div>

---

## Why PreFlight?

Most AI coding assistants act like eager "yes-men": pitch an idea and they immediately scaffold code on shaky assumptions, pick a Vector DB when SQLite FTS5 would do, or reinvent a library that already has thousands of stars on GitHub.

**PreFlight** runs *before* implementation. It combines a structured Socratic interview with a live GitHub prior-art & config-file scout to stress-test your design, lock architectural decisions, and output a complete blueprint and ordered issue queue.

---

## ✨ What PreFlight Does

| Stage | Capability | How It Works |
| :--- | :--- | :--- |
| **1. Interrogate** | **Socratic Frontier Grilling** | Challenges your idea across 5 dimensions (`Problem`, `Scope`, `Memory`, `Bottlenecks`, `Differentiation`) with concrete `➡️` recommended answers. |
| **2. Scout** | **GitHub Prior-Art & Pain-Point Miner** | Queries GitHub (`-q`, `--topic`, `-t`) for **Active Incumbents**, **Dormant/Graveyard Repos** ($>365\text{d}$ inactivity heuristic), **OSS Building Blocks**, and top-voted open issues + developer comments. |
| **3. Inspect** | **"Stack Explained" (`Now` vs. `Later`)** | Inspects real repo config files (`pyproject.toml`, `Dockerfile`, `.github/workflows`, `.pre-commit-config.yaml`, `go.sum`, `Cargo.lock`) and separates **`✅ Verified`** proofs from **`⚠️ Claimed / Unverified`** recommendations. |
| **4. Advise** | **Memory & Agent Communication** | Supports primary + secondary strategies (`stateless`, `transactional-db`, `lexical-fts`, `rag-vector-db`, `hybrid-search`, `episodic-agent-state`), handoff schemas, and memory failure modes. |
| **5. Compile** | **Blueprint, Spec & Ordered Tickets** | Enforces an **80% Evidence Gate**, then compiles `blueprint_report.html`, `.preflight/SPEC.md`, `.preflight/STACK.md`, and ordered vertical-slice tickets in `.preflight/issues/01-*.md`. |

---

## 🚀 Quick Start

### 1. Install

Clone the repository and copy the self-contained skill into your agent's skills directory (zero external dependencies — Python 3.10+ standard library only):

```bash
git clone https://github.com/thilak15/preflight.git
cd preflight

# For Gemini / Antigravity:
cp -R skills/preflight ~/.gemini/config/skills/preflight

# Or for Claude Code:
cp -R skills/preflight ~/.claude/skills/preflight
```

> **Tip:** Authenticate [GitHub CLI](https://cli.github.com/) (`gh auth login`) or set `GITHUB_TOKEN` for the `30 req/min` GitHub Search API quota (automatically falls back to `10 req/min` unauthenticated).

### 2. Run Inside Your Agent

```text
/preflight I want to build <your project idea>
```

Want to run a **brand-new idea** in the same folder or **re-run from a clean slate**?
```bash
python3 skills/preflight/scripts/state.py --workspace . reset
```
*(By default, `reset` and `init --reset` only remove ADR files recorded in `.preflight/decisions.json` and preserve any pre-existing `docs/adr/*.md` files. Pass `--keep-adrs` to also keep ADRs from the previous PreFlight session.)*

---

## 🧭 Workflow Overview

```mermaid
flowchart LR
    A(["💡 Idea Pitch"]) --> B["1. Socratic Grilling\n(state.py)"]
    B --> C["2. GitHub & Config Scout\n(scout.py + cache.db)"]
    C --> D["3. Stack Explained &\nMemory Advisor"]
    D --> E{"🔒 80% Evidence\nGate Unlocked?"}
    E -->|"No"| B
    E -->|"Yes"| F["4. Blueprint + SPEC.md +\nOrdered Tickets (.preflight/issues/)"]
```

---

## 🛡️ The 5-Dimension Readiness Gate

Unlike prompt-only skills where an LLM can grade itself `100%` with one-line summaries, `state.py` enforces **programmatic anti-theater checks** before unlocking Blueprint generation:

| Dimension | Weight | Required to Score `20/20` (Programmatically Enforced in `state.py`) |
| :--- | :---: | :--- |
| **1. Problem & User Pain** (`problem`) | `20%` | Substantive summary ($\ge 40$ chars) + $\ge 2$ stress-tested `--edge-case` scenarios |
| **2. Scope & Non-Goals** (`scope`) | `20%` | Explicit V1 non-goals ($\ge 40$ chars) + $\ge 2$ hard boundary `--edge-case` items |
| **3. State, Memory & Agent Comm** (`memory`) | `20%` | Requires `set-memory-arch` (primary strategy, communication pattern, $\ge 1$ failure mode) + summary ($\ge 40$ chars) + $\ge 2$ `--edge-case` items |
| **4. Bottlenecks & Failure Modes** (`bottlenecks`) | `20%` | Rate limits, latency, SPOFs ($\ge 40$ chars), and $\ge 2$ stress-tested mitigations |
| **5. Prior-Art Differentiation** (`differentiation`) | `20%` | Requires `.preflight/prior-art.json` from `scout.py`, $\ge 2$ edge cases, and must explicitly cite $\ge 1$ discovered `owner/repo` |

**Gate Unlock Rule (`evaluate_gate`):**
- Total score $\ge 80\%$ with **zero** dimensions at `0%`
- `.preflight/prior-art.json` present with scouted repositories
- `set-memory-arch` configured (strategy + communication pattern + $\ge 1$ failure mode)
- At least **1 Stack Explained tool entry** (`add-tool`)
- At least **1 ADR** (`add-decision`) and **1 Red-Team Critique** (`add-critique`)
- Both Mermaid diagrams (`topology` + `sequence`) populated via `set-design`

> **Draft Override (`--force`):** Passing `--force` to `render_blueprint.py` or `state.py export-tickets` allows exporting early previews while the gate is locked, but stamps **`[DRAFT]`** across `blueprint_report.html`, `SPEC.md`, `STACK.md`, and marks all exported tickets `**Status:** draft` instead of `ready-for-agent`.

---

## 📦 What Gets Generated

When the Readiness Gate unlocks and `render_blueprint.py` runs, PreFlight produces a complete engineering package:

| Artifact | Purpose |
| :--- | :--- |
| **`blueprint_report.html`** | Interactive 5-tab dark-mode HTML dashboard (Scorecard, Prior-Art & Pain Points, Stack Explained & Memory, Mermaid Diagrams, ADR Ledger). *Note: Rendered diagrams load Mermaid.js from `cdn.jsdelivr.net` (internet required); expandable raw Mermaid source blocks are included on every diagram.* |
| **`.preflight/SPEC.md`** | Clean, git-ready system design specification. |
| **`.preflight/STACK.md`** | **"Stack Explained"** table (`Now` vs. `Later`, **`✅ Verified`** vs. **`⚠️ Claimed / Unverified`** config proof, alternatives) + Primary & Secondary Memory architecture. |
| **`.preflight/issues/01-*.md`** | Individual, ordered vertical-slice tickets (`01`, `02`, `03`...) with ticket-specific acceptance criteria derived from each step, relevant ADRs, and critiques. |
| **`docs/adr/NNNN-*.md`** | Permanent Architecture Decision Records with rejected alternatives. |
| **`GLOSSARY.md`** | Ubiquitous domain language maintained throughout the interview. |

---

## 📖 Case Study (`examples/edge-cron-scheduler/`)

See an illustrative walkthrough backed by a **real committed `scout.py` dataset** ([`examples/edge-cron-scheduler/.preflight/prior-art.json`](./examples/edge-cron-scheduler/.preflight/prior-art.json)), showing how PreFlight pivoted an embedded-Raft cron pitch into an autonomous **SQLite WAL + Linux `cgroups v2`** architecture after mining real issues like `dkron-io/dkron#1001`, `dkron-io/dkron#966`, and `dagucloud/dagu#1260`:

- 📄 **[Read the Case Study Walkthrough](./examples/edge-cron-scheduler/CASE_STUDY.md)**
- 🔍 **[Inspect Committed `prior-art.json`](./examples/edge-cron-scheduler/.preflight/prior-art.json)** & **[`state.json`](./examples/edge-cron-scheduler/.preflight/state.json)**
- 📋 **[View the Exported `SPEC.md`](./examples/edge-cron-scheduler/SPEC.md)** & **[`STACK.md`](./examples/edge-cron-scheduler/STACK.md)**
- 🎟️ **[Browse the Ordered Tickets (`issues/INDEX.md`)](./examples/edge-cron-scheduler/issues/INDEX.md)**
- 🖥️ **[Open `blueprint_report.html`](./examples/edge-cron-scheduler/blueprint_report.html)**

---

## 🛠️ CLI Reference

<details>
<summary><strong>Click to expand full CLI commands (<code>state.py</code>, <code>scout.py</code>, <code>render_blueprint.py</code>)</strong></summary>

<br/>

```bash
# 1. Initialize (or pass --reset [--keep-adrs] to wipe any previous run cleanly)
python3 skills/preflight/scripts/state.py --workspace . init --reset \
  --name "EdgeCron" \
  --summary "Autonomous Linux edge DAG scheduler with cgroup v2 step isolation" \
  --runtime "Go 1.23 (Linux)" \
  --stack "Go,SQLite3 WAL,Linux cgroups v2"

# 2. Scout GitHub Competitors (-q / --topic), OSS Building Blocks (-t / --tool-topic), and Repo Config Files
python3 skills/preflight/scripts/scout.py --workspace . \
  -q "dagu language:go" \
  -q "dkron language:go" \
  --topic "cron-scheduler" \
  -t "modernc.org/sqlite"

# 3. Add "Stack Explained" entries (Verified against scout.py observed_stack_configs or workspace files)
python3 skills/preflight/scripts/state.py --workspace . add-tool \
  --category container-runtime \
  --recommended "Docker (Dockerfile)" \
  --stage now \
  --config-proof "Dockerfile" \
  --purpose "Multi-stage static binary build & cgroups v2 integration test container" \
  --why "Proven across dkron-io/dkron and dagucloud/dagu; tests cgroup.kill behavior reproducibly" \
  --alternatives "Host-only go test (cannot safely simulate OOM kills on dev laptops)"

# 4. Configure Primary + Secondary Memory & Agent/Component Communication Architecture
python3 skills/preflight/scripts/state.py --workspace . set-memory-arch \
  --strategy transactional-db \
  --secondary-strategy lexical-fts \
  --communication "Single-writer Go channel batching step heartbeats into SQLite WAL every 100ms" \
  --workflow "Append-only run state transitions + SQLite FTS5 over step logs (50MB ring buffer)" \
  --rationale "Deterministic crash recovery and exact log search without Raft quorum loss (dkron-io/dkron#1001)" \
  --alternatives "Embedded Raft (dkron-io/dkron#1001); shared NFS files (dagucloud/dagu#1260)" \
  --failure-mode "SQLITE_BUSY under 50+ concurrent step heartbeats -> Mitigated by single writer goroutine"

# 5. Score Dimensions, Record ADRs & Red-Team Critiques
python3 skills/preflight/scripts/state.py --workspace . update-dimension \
  --dimension differentiation --score 20 \
  --summary "Addresses dkron-io/dkron#1001 (Raft quorum loss) and dagucloud/dagu#1260 (shared filesystem coupling) via autonomous SQLite WAL and Linux cgroups v2." \
  --edge-case "Avoids dkron-io/dkron#1001 by eliminating Raft in favor of per-node SQLite WAL" \
  --edge-case "Solves dagucloud/dagu#1260 and dkron-io/dkron#966 via mTLS sync_outbox and max_parallel_jobs"

python3 skills/preflight/scripts/state.py --workspace . add-decision \
  --title "Linux cgroups v2 Per-Step Isolation" \
  --decision "Spawn each DAG step inside a dedicated cgroup v2 scope with cgroup.kill teardown." \
  --rejected "Standard Go os/exec Process.Kill()" \
  --rationale "Prevents orphaned grandchild processes and enforces per-step memory caps." \
  --dimension bottlenecks

python3 skills/preflight/scripts/state.py --workspace . add-critique \
  --title "Post-Outage Cron Stampede on Reboot" \
  --severity critical \
  --attack "Firing 240 missed 1-minute jobs simultaneously after a 4-hour outage exhausts 1GB RAM." \
  --mitigation "Enforce per-DAG catchup_policy (skip | latest_only | backfill_serial)."

# 6. Set Diagrams & Render Blueprint + SPEC.md + STACK.md + Ordered Tickets (.preflight/issues/)
python3 skills/preflight/scripts/state.py --workspace . set-design \
  --topology "flowchart LR\n    CLI --> Daemon --> SQLite[(SQLite WAL)]" \
  --sequence "sequenceDiagram\n    CLI->>Daemon: Trigger DAG\n    Daemon->>SQLite: Commit state" \
  --option "SQLite WAL + cgroups v2|100% offline availability, zero orphans|Linux-only|Selected (ADR-0001)" \
  --step "Bootstrap Go 1.23 module and SQLite WAL single-writer batch loop (ADR-0001)" \
  --step "Implement Linux cgroup v2 scope runner with cgroup.kill teardown (ADR-0002)"

python3 skills/preflight/scripts/render_blueprint.py --workspace .
```

</details>

---

## 📂 Repository Layout

```text
preflight/
├── skills/preflight/
│   ├── SKILL.md                     # Self-contained Agent Skill instructions
│   └── scripts/
│       ├── state.py                 # Readiness Gate, Stack Explained, Memory Advisor & Ticket Exporter
│       ├── scout.py                 # GitHub Deep-Scout, Config Inspector & Issue/Comment Miner
│       └── render_blueprint.py      # 5-tab HTML Blueprint, SPEC.md, STACK.md & Ticket compiler
├── examples/edge-cron-scheduler/    # Case study with committed prior-art.json, state.json, SPEC, STACK & tickets
├── docs/adr/                        # Architecture Decision Records (0001–0003)
├── tests/test_preflight.py          # Zero-dependency unit & integration test suite
├── CHANGELOG.md                     # Release history
└── GLOSSARY.md                      # Domain vocabulary
```

## 🧪 Testing

```bash
python3 -m unittest discover -s tests -v
```

## 📄 License

Released under the [MIT License](./LICENSE).
