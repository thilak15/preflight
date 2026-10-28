# ADR-0002: Hybrid Repo-Native Markdown/JSON State and SQLite Repo Cache

- **Status:** Accepted
- **Date:** 2026-10-27
- **Dimension:** `memory`

## Context

During a PreFlight session, three distinct classes of data are produced:
1. **Working State:** Current rubric scores, edge cases, red-team critiques, and Mermaid system diagrams.
2. **Decision Ledger & Domain Vocabulary:** Locked Architecture Decision Records (ADRs) and canonical project terms (`GLOSSARY.md`).
3. **GitHub API Cache:** Raw HTTP responses from `/search/repositories`, `/search/issues`, and `/repos/:owner/:repo/issues/:number/comments`.

Storing all three in a single binary SQLite file makes architectural decisions opaque to `git diff`, code reviewers, and subsequent coding sessions. Conversely, storing raw GitHub API responses as flat JSON files clutters the workspace and complicates TTL expiration.

## Decision

We split persistence by access pattern:
- **Repo-Native Markdown (`GLOSSARY.md`, `docs/adr/NNNN-*.md`, `.preflight/SPEC.md`):** Human-readable, git-diffable artifacts meant to be committed or handed directly to implementation workflows.
- **Structured Session State (`.preflight/state.json`, `.preflight/decisions.json`, `.preflight/prior-art.json`):** Machine-readable JSON files consumed by `state.py` and `render_blueprint.py`.
- **SQLite API Cache (`.preflight/cache.db`):** Ephemeral local cache with a 7-day TTL for GitHub Search and Issue Comment API responses, excluded from version control via `.gitignore`.

## Considered & Rejected Alternatives

- **Single SQLite Database for All State:** Rejected because binary `.db` files cannot be reviewed in pull requests or read natively by coding agents without SQL queries.
- **In-Memory Only (No Disk Persistence):** Rejected because multi-round Socratic interviews and iterative GitHub scouting runs must survive across turns and terminal invocations without re-hitting GitHub rate limits.

## Consequences

- **Positive:** ADRs and `GLOSSARY.md` remain first-class repository documentation; repeated `scout.py` runs hit local SQLite cache in `<10ms` without consuming GitHub Search API quota (`30 req/min` authenticated, `10 req/min` unauthenticated).
- **Negative / Trade-off:** `state.py` must keep `.preflight/decisions.json` and `docs/adr/NNNN-*.md` synchronized when `add-decision` is invoked.
