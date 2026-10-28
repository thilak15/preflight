# Hybrid Repo-Native Markdown/JSON State and SQLite Repo Cache

PreFlight splits its 3-tier persistence across human-readable repo files and a local SQLite cache rather than storing all three tiers in a single opaque SQLite database:

- **Working State & Decision Ledger**: Stored as structured JSON (`.preflight/state.json`, `.preflight/decisions.json`) alongside standard Markdown Architecture Decision Records (`docs/adr/NNNN-*.md`) so decisions are git-diffable and immediately readable by downstream coding agents.
- **Repo Cache**: Stored in SQLite (`.preflight/cache.db`) with a 7-day TTL to cache raw GitHub repository metadata, star velocity, and issue threads without polluting version control.
