# PreFlight Repository Rules

## Architecture & Coding Standards

- **Zero External Dependencies:** All scripts under `skills/preflight/scripts/` must use the Python 3.10+ standard library only (`sqlite3`, `urllib`, `json`, `argparse`, `html`, `unittest`).
- **Evidence-Based Readiness Gate:** `state.py` must programmatically verify evidence before allowing `20/20` dimension scores or unlocking `render_blueprint.py`. Never bypass validation rules in production code paths.
- **Self-Contained Repository:** Do not add references to external skill repositories or uncommitted local paths. Keep `GLOSSARY.md` and `docs/adr/` accurate and up to date.
- **Testing:** Run `python3 -m unittest discover -s tests -v` before committing any change to `skills/preflight/scripts/`.
