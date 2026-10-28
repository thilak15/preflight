# Changelog

All notable changes to **PreFlight** are documented in this file.

## [Unreleased]

### Added
- **Live-Link Skill Installer (`scripts/link-skills.sh`)**: Dev-only script to link `skills/preflight` directly into `~/.claude/skills`, `~/.agents/skills`, and `~/.gemini/config/skills` so that `git pull` automatically updates installed agent skills without re-copying. Includes safety guards against silent overwrite of real folders (`--force` required) and against symlinks pointing into the repository.

### Fixed
- **Readiness Gate includes diagrams (`state.py evaluate_gate`)**: Missing `topology_mermaid` / `sequence_mermaid` now keeps the gate locked, so `state.py status`, `export-tickets`, and `render_blueprint.py` agree, and `render_blueprint.py --force` always watermarks placeholder diagrams as `DRAFT`.
- **Differentiation citations (`state.py cites_repo`)**: A `20/20` differentiation score now requires a whole-token `owner/repo` citation; bare repo names like `cron` no longer pass by matching ordinary words.
- **Config proof verification (`state.py verify_config_proof`)**: An explicit `--config-proof` filename that was never observed stays `claimed-unverified`, even if the tool name matches a scouted config.

### Changed
- Shared `format_memory_architecture_lines()` renders the Memory Architecture in both `STACK.md` and `SPEC.md`.
- Removed duplicate `examples/edge-cron-scheduler/.preflight/STACK.md` and `.preflight/issues/` (the published copies live at the example root).
- Updated module docstrings, `GLOSSARY.md` (**Proof Status**, secondary strategies, ADR-preserving reset), and ADR-0003.

## [0.2.0] - 2026-10-28

### Added
- **Config-File Stack Inspector (`scout.py`)**: Inspects root repository files (`pyproject.toml`, `uv.lock`, `poetry.lock`, `Dockerfile`, `docker-compose.yml`, `.github/workflows`, `.pre-commit-config.yaml`, `go.sum`, `Cargo.lock`, `Makefile`) across top incumbents and records `observed_stack_configs` + `search_limits` metadata in `.preflight/prior-art.json`.
- **GitHub Topic & OSS Building-Block Search (`scout.py`)**: Added `--topic`, `--tool-query` (`-t`), and `--tool-topic` flags to discover both competitor repositories and open-source building blocks/SDKs.
- **"Stack Explained" Advisor (`state.py add-tool` & `.preflight/STACK.md`)**: Records per-tool purpose, why needed, alternatives considered, `now` vs. `later` stage, and verifies `--config-proof` against `scout.py` output or workspace files (`✅ Verified` vs. `⚠️ Claimed / Unverified`).
- **Combined Memory & Agent Communication Advisor (`state.py set-memory-arch`)**: Supports primary `--strategy` plus repeatable `--secondary-strategy` (`stateless`, `transactional-db`, `lexical-fts`, `rag-vector-db`, `hybrid-search`, `episodic-agent-state`), communication pattern, workflow lifecycle, and required `--failure-mode` entries.
- **Safe Fresh Reset (`state.py reset` & `state.py init --reset`)**: Deletes only ADR markdown files recorded in `.preflight/decisions.json` (preserving pre-existing repository ADRs) and supports `--keep-adrs` on both `reset` and `init --reset`.
- **Ordered Ticket Exporter (`state.py export-tickets` & `render_blueprint.py`)**: Exports individual vertical-slice tickets (`.preflight/issues/NN-<slug>.md` + `INDEX.md`) with word-boundary slugs, optional `Title :: Details :: BlockedBy` dependency edges, ticket-specific acceptance criteria, and strict `[DRAFT]` / `Status: draft` watermarking when `--force` is used.
- **Live Reproducible Case Study (`examples/edge-cron-scheduler/`)**: Committed real `scout.py` output (`.preflight/prior-art.json`), locked `.preflight/state.json`, `.preflight/decisions.json`, `SPEC.md`, `STACK.md`, `blueprint_report.html`, and ordered tickets.

### Changed
- **Programmatic Readiness Gate Agreement (`state.py`)**: `validate_dimension_evidence` (for `memory == 20`) and `evaluate_gate` now programmatically enforce `set-memory-arch` (strategy + communication + $\ge 1$ failure mode) and $\ge 1$ `add-tool` entry, matching `README.md` and `SKILL.md`.
- **Mermaid CDN Disclosure (`render_blueprint.py` & `README.md`)**: Clarified that visual diagram rendering in `blueprint_report.html` loads Mermaid.js from `cdn.jsdelivr.net` (internet required), with expandable raw Mermaid source blocks on every diagram card.

## [0.1.0] - 2026-10-27

### Added
- Initial release of PreFlight (`state.py`, `scout.py`, `render_blueprint.py`, `SKILL.md`, `GLOSSARY.md`, and `docs/adr/0001`–`0002`).
