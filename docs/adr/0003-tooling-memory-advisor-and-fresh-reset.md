# ADR-0003: Tooling & Maintenance Stack Advisor, Memory Architecture Advisor, and Fresh Workspace Reset

- **Status:** Accepted
- **Date:** 2026-10-27
- **Dimension:** `memory` / `scope`

## Decision

1. **Tooling, OSS Building Blocks & Project Maintenance Stack (`state.py add-tool` + `scout.py -t`)**:
   - Extend `scout.py` with `--tool-query` (`-t`) to discover actively maintained open-source building blocks (libraries, SDKs, frameworks) on GitHub alongside competitor repositories.
   - Extend `state.py` with `add-tool` across standard operational and engineering categories (`dependency-lock`, `container-runtime`, `orchestration-deploy`, `ci-cd-quality`, `core-oss`, `storage-memory`, `observability`) so every project blueprint recommends day-1 project maintenance tooling (e.g., `uv.lock` / `poetry.lock`, `Docker` multi-stage builds, `Docker Compose` vs. `Kubernetes`, CI pipelines) with explicit rationales and viable alternatives.
   - Auto-generate `.preflight/STACK.md` and render Tab 3 (`Tooling, Maintenance & Memory`) in `blueprint_report.html`.
2. **Memory, State & Agent Communication Advisor (`state.py set-memory-arch`)**:
   - Keep `memory` (`State, Memory & Agent Communication`) as a core `20%` Readiness Gate dimension.
   - Require explicit selection and justification among `stateless`, `transactional-db`, `lexical-fts`, `rag-vector-db`, `hybrid-search`, and `episodic-agent-state`, together with the agent/component communication pattern and anticipated memory failure modes.
3. **Fresh Reset (`state.py reset` and `state.py init --reset`)**:
   - Add a `reset` subcommand and `init --reset` flag that deletes all pre-performed scores, state, decisions, prior-art snapshots, and generated specs so users can run a new idea or re-run the same idea cleanly from zero in the same directory while preserving `.preflight/cache.db` by default (with `--purge-cache` to wipe SQLite cache).
4. **Implementation Ticket Graph Export (`state.py export-tickets` + `render_blueprint.py`)**:
   - Automatically compile locked decisions (ADRs), Day-1 `NOW` tools (`Stack Explained`), Memory Architecture rules, Red-Team mitigations, and ordered implementation steps into individual dependency-ordered issue files under `.preflight/issues/01-<slug>.md`, `02-<slug>.md`, ..., plus `.preflight/issues/INDEX.md`.

## Context & Rationale

- Users validating an idea need concrete guidance on **both** what open-source libraries exist to build the idea and what foundational project maintenance tools (`poetry.lock`/`uv.lock`, `Docker`, `Kubernetes`) fit the project's scale, plus when to swap to alternatives.
- Prematurely defaulting to a Vector DB or RAG—or passing raw uncompacted chat history between agents—is one of the most common failure modes in modern AI/agent systems. Explicitly modeling agent communication and memory strategy prevents over-engineering and context rot.
- Previously, running `state.py init` in a workspace that already had `.preflight/state.json` preserved old dimension scores and ADRs, polluting subsequent ideas or re-runs.

## Considered & Rejected Alternatives

- **Dropping the `memory` dimension from the 5-dimension rubric:** Rejected because state management, caching, and inter-agent context passing are primary production bottlenecks.
- **Manual file deletion for re-runs:** Rejected as error-prone; a dedicated `state.py reset` / `init --reset` command ensures all state, ADR, and spec artifacts are cleanly removed in one step.
