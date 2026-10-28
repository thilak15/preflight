# PreFlight

An adversarial pre-implementation architecture, tooling, and prior-art validation system that stress-tests project ideas, mines GitHub repositories and open issues for real-world pain points, recommends open-source building blocks and project maintenance tooling, prescribes memory and agent communication workflows, tracks architectural decisions, and compiles a visual system design blueprint.

## Language

### Interrogation & Gatekeeping

**Grilling Session**:
A structured Socratic interview across five architectural dimensions (Problem, Scope, Memory, Bottlenecks, Differentiation) to expose blind spots before code is written.
_Avoid_: Brainstorming, chat session, Q&A

**Readiness Gate**:
A threshold across the five grilling dimensions that blocks blueprint generation until key architectural risks are resolved.
_Avoid_: Validation check, completion score, progress bar

**Fresh Reset**:
The explicit clearing of all previously recorded dimension scores, state, decisions, prior-art snapshots, and generated specs (`state.py reset` or `state.py init --reset`) so a new idea or clean re-run starts from zero in the same workspace.
_Avoid_: Folder wipe, manual delete

### Prior-Art & Tooling Scouting

**Prior-Art Scout**:
The process of searching GitHub repositories and issue boards to evaluate existing solutions and open-source building blocks for the problem.
_Avoid_: Competitor research, market analysis, repo scraper

**Active Incumbent**:
A competing repository pushed within the last 365 days that represents a live, maintained alternative in the problem space.
_Avoid_: Competitor repo, active project

**Graveyard Repo**:
A competing repository that has been inactive for more than 365 days (or archived), signaling a stalled or abandoned attempt at the problem.
_Avoid_: Dead repo, stale project, archived repo

**OSS Building Block**:
An actively maintained open-source library, SDK, or tool discovered via `scout.py --tool-query` that can be used to construct the project rather than reinventing components from scratch.
_Avoid_: Random repo, third-party dependency

**Project Maintenance Stack**:
The operational and day-1 engineering tooling recommended for the project—covering dependency lockfiles (`uv.lock`, `poetry.lock`), containerization (`Docker`), orchestration (`Docker Compose`, `Kubernetes`), and CI/CD—along with viable alternatives and selection rationale.
_Avoid_: DevOps stuff, boilerplate

**Stack Explained**:
A per-tool architectural record (`state.py add-tool` and `.preflight/STACK.md`) that answers four questions for every tool in the project: what job it does, why the project needs it now, what the alternative was, and whether it is `now` (Day 1) or `later` (deferred), backed by **Config Proof** from scouted repositories.
_Avoid_: Generic tech stack list, unverified tool wish-list

**Config Proof**:
Empirical evidence from a scouted repository's configuration files (`pyproject.toml`, `uv.lock`, `poetry.lock`, `Dockerfile`, `.github/workflows`, `.pre-commit-config.yaml`) proving that a specific build, container, or CI tool is used in production.
_Avoid_: README keyword match, guessed stack

**Implementation Ticket Graph**:
The set of dependency-ordered, self-contained vertical-slice issue files (`.preflight/issues/01-<slug>.md`, `02-<slug>.md`, ..., and `.preflight/issues/INDEX.md`) exported by `state.py export-tickets` and `render_blueprint.py` once the Readiness Gate unlocks.
_Avoid_: Unordered task list, horizontal layer tasks

**Pain-Point Mining**:
Extracting top-voted open issues and user complaints from competing repositories to identify unsolved flaws in existing tools.
_Avoid_: Issue scraping, bug analysis, sentiment analysis

### Memory, State & Output

**Memory & Communication Strategy**:
The prescribed pattern for how components or agents communicate and persist state across the workflow (`stateless`, `transactional-db`, `lexical-fts`, `rag-vector-db`, `hybrid-search`, or `episodic-agent-state`), paired with its specific memory failure modes.
_Avoid_: Just add RAG, vector store

**Working State**:
The mutable snapshot of the current project's problem statement, target runtime, tech stack, tooling recommendations, memory architecture, bottlenecks, and Readiness Gate rubric scores.
_Avoid_: Session state, temp state, Tier 1 memory

**Decision Ledger**:
An append-only record of architectural choices locked in or rejected during a Grilling Session, along with the rationale.
_Avoid_: ADR log, history table, decision cache

**Repo Cache**:
The local SQLite store of scraped GitHub repository metadata, star velocity, and issue threads used to prevent redundant API calls.
_Avoid_: GitHub cache, Tier 3 memory, API cache

**Blueprint**:
The final standalone HTML artifact (`blueprint_report.html`) and companion markdown specifications (`.preflight/SPEC.md` and `.preflight/STACK.md`) combining the red-team critique, prior-art matrix, tooling/maintenance stack, memory advisor, system topology diagrams, and implementation plan.
_Avoid_: Report, dashboard, spec doc
