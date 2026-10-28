# ADR-0004: Codebase Deepening, Domain Facades, and Test Seams

- **Status:** Accepted
- **Date:** 2026-10-28
- **Dimension:** `codebase-architecture` / `testability`

## Decision

Deepen the internal architecture of `skills/preflight/scripts/` (`state.py`, `scout.py`, `render_blueprint.py`) across five key seams to eliminate shallow modules, fix hidden calling coupling, and enable zero-dependency deterministic testing:

1. **Readiness Gate Verdict Value Object (`GateVerdict`)**:
   - Replace raw 3-tuples `(score, unlocked, missing)` with a frozen, immutable `GateVerdict` value object carrying `score: int`, `unlocked: bool`, `missing: list[str]`, and `is_draft: bool`.
   - Implement `__iter__` returning `(score, unlocked, missing)` to maintain 100% backward compatibility with legacy tuple unpacking while providing clean, named access (`verdict.is_draft`, `verdict.unlocked`).
2. **Consolidated Draft Watermarking Pipeline (`ArtifactWatermarker`)**:
   - Consolidate all draft watermarking rules (specification headers, HTML report warning banners, issue ticket statuses, and markdown ticket notices) into a single cohesive module.
   - Eliminates scattered ad-hoc string formatting across `state.py` and `render_blueprint.py`.
3. **Workspace Store Module (`WorkspaceStore`)**:
   - Encapsulate all `.preflight/` paths (`state_path`, `decisions_path`, `prior_art_path`, `cache_path`, `spec_path`, `stack_path`, `issues_dir`, `adr_dir`), schema defaults, atomic state persistence, and reset lifecycle.
   - Eliminate read side-effects: calling `load_state()`, `load_decisions()`, or `load_prior_art()` no longer creates directories on disk if they do not exist.
4. **Domain Operations Facade (`PreFlightOps`)**:
   - Extract domain operations (`init_project`, `update_dimension`, `add_tool`, `set_memory_architecture`, `add_critique`, `add_decision`, `set_system_design`) from CLI argument parsing in `state.py`.
   - Provide a dual-mode interface: methods can be invoked statically by CLI adapters (`PreFlightOps.init_project(workspace, ...)`) or called as instance methods on an initialized store (`ops = PreFlightOps(workspace); ops.init_project(...)`).
5. **GitHub Client Seam & Fake Adapter (`GitHubClient`, `HttpGitHubClient`, `FakeGitHubClient`)**:
   - Define a `GitHubClient` interface in `scout.py` with standard production implementation `HttpGitHubClient` (using Python stdlib `urllib.request`) and in-memory test implementation `FakeGitHubClient`.
   - Allow prior-art search, config-file inspection, and pain-point mining to be tested deterministically offline without monkey-patching `urllib.request.urlopen`.

## Context & Rationale

- Previously, understanding how the Readiness Gate unlocked or how draft watermarking worked required navigating across three files (`state.py`, `render_blueprint.py`, `scout.py`).
- Testing domain rules required invoking CLI dispatchers (`state.main([...argv])`) and capturing stdout/stderr, obscuring test failures when parameter types or flags changed.
- Unit testing GitHub API responses required global monkey-patching of `urllib.request.urlopen`, which leaked across tests and made testing edge cases (like rate-limiting or contents inspection) brittle.

## Considered & Rejected Alternatives

- **External Mocking / Dependency Libraries (e.g. `requests-mock`, `responses`, `pydantic`):** Rejected. PreFlight maintains a strict zero external runtime dependency policy (Python 3.10+ standard library only: `sqlite3`, `urllib`, `dataclasses`, `pathlib`).
- **Splitting `state.py` into multiple subpackages:** Evaluated and deferred. Keeping the scripts single-file (`skills/preflight/scripts/state.py`) preserves portability when installed via copy or symlink into agent harnesses (`~/.gemini/config/skills`, `~/.claude/skills`, `~/.agents/skills`). Deepening classes within the existing script files achieved identical architectural separation without deployment friction.
