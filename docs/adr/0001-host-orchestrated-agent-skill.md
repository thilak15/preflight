# ADR-0001: Host-Orchestrated Agent Skill Over Standalone LLM CLI

- **Status:** Accepted
- **Date:** 2026-10-27
- **Dimension:** `scope`

## Context

PreFlight's original concept proposed a standalone Python CLI application powered by the Google GenAI SDK (`gemini-2.5-flash`) and `Rich` terminal UI. However, developers running PreFlight inside modern AI coding environments (Antigravity, Claude Code, Cursor, Codex) are already interacting with a frontier LLM that holds full workspace context, file-editing tools, and subagent capabilities.

Building a separate LLM loop inside a Python CLI creates three structural problems:
1. **Duplicate API Keys & Billing:** Users must provision and manage a separate `GEMINI_API_KEY` even though their host coding agent is already authenticated.
2. **Split Conversation Context:** Architectural decisions discussed inside the CLI loop are invisible to the host coding agent unless manually exported and re-imported.
3. **Nondeterministic Side Effects:** Relying on a raw LLM prompt to write HTML dashboards or manage GitHub API caching leads to broken Mermaid syntax and redundant network calls.

## Decision

We package PreFlight as a **host-orchestrated Agent Skill** (`skills/preflight/SKILL.md`) paired with three **deterministic, stdlib-only Python helper scripts** (`state.py`, `scout.py`, `render_blueprint.py`):

- The **host agent** conducts the Socratic interview rounds and synthesizes architectural trade-offs.
- **`scout.py`** deterministically executes GitHub REST/Search API queries, inspects rate-limit headers, caches responses in SQLite, and extracts high-reaction issues and top comments.
- **`state.py`** deterministically enforces evidence requirements on the 5-dimension rubric (rejecting shallow summaries, missing edge cases, or uncited prior art) and writes `docs/adr/NNNN-*.md`.
- **`render_blueprint.py`** deterministically compiles `.preflight/*.json` into `blueprint_report.html` and `.preflight/SPEC.md`.

## Considered & Rejected Alternatives

- **Standalone `gemini-2.5-flash` Python CLI:** Rejected due to duplicate key management, split context, and unnecessary third-party Python dependencies (`google-genai`, `rich`).
- **Pure Markdown Prompt Skill (No Helper Scripts):** Rejected because pure prompt instructions cannot enforce programmatic evidence gates, cache GitHub API responses in SQLite, or guarantee valid HTML/Mermaid rendering.

## Consequences

- **Positive:** Zero `pip install` dependencies (runs on any system with Python 3.10+); works across any model or host agent; programmatic validation prevents the agent from awarding itself `100%` without evidence.
- **Negative / Trade-off:** Requires an AI coding agent environment rather than running as an autonomous chatbot in a bare terminal without an agent host.
