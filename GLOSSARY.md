# PreFlight

An adversarial pre-implementation architecture and prior-art validation system that stress-tests project ideas, mines GitHub repositories and open issues for real-world pain points, tracks architectural decisions, and compiles a visual system design blueprint.

## Language

### Interrogation & Gatekeeping

**Grilling Session**:
A structured Socratic interview across five architectural dimensions (Problem, Scope, Memory, Bottlenecks, Differentiation) to expose blind spots before code is written.
_Avoid_: Brainstorming, chat session, Q&A

**Readiness Gate**:
A threshold across the five grilling dimensions that blocks blueprint generation until key architectural risks are resolved.
_Avoid_: Validation check, completion score, progress bar

### Prior-Art Scouting

**Prior-Art Scout**:
The process of searching GitHub repositories and issue boards to evaluate existing solutions to the same problem.
_Avoid_: Competitor research, market analysis, repo scraper

**Active Incumbent**:
A competing repository pushed within the last 365 days that represents a live, maintained alternative in the problem space.
_Avoid_: Competitor repo, active project

**Graveyard Repo**:
A competing repository that has been inactive for more than 365 days (or archived), signaling a stalled or abandoned attempt at the problem.
_Avoid_: Dead repo, stale project, archived repo

**Pain-Point Mining**:
Extracting top-voted open issues and user complaints from competing repositories to identify unsolved flaws in existing tools.
_Avoid_: Issue scraping, bug analysis, sentiment analysis

### State & Output

**Working State**:
The mutable snapshot of the current project's problem statement, target runtime, tech stack, bottlenecks, and Readiness Gate rubric scores.
_Avoid_: Session state, temp state, Tier 1 memory

**Decision Ledger**:
An append-only record of architectural choices locked in or rejected during a Grilling Session, along with the rationale.
_Avoid_: ADR log, history table, decision cache

**Repo Cache**:
The local SQLite store of scraped GitHub repository metadata, star velocity, and issue threads used to prevent redundant API calls.
_Avoid_: GitHub cache, Tier 3 memory, API cache

**Blueprint**:
The final standalone HTML artifact combining the red-team critique, prior-art matrix, system topology diagrams, and implementation plan.
_Avoid_: Report, dashboard, spec doc

