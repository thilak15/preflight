# Implementation Ticket Graph: EdgeCron

Work these tickets sequentially in dependency order (one vertical slice per session/commit):

| # | Ticket File | Title | Blocked By | Status |
| :---: | :--- | :--- | :--- | :---: |
| `01` | [01-implement-sqlite-wal-schema-and-single-writer-batching-state.md](./01-implement-sqlite-wal-schema-and-single-writer-batching-state.md) | Implement SQLite WAL schema and single-writer batching state machine | None (can start immediately) | `ready-for-agent` |
| `02` | [02-implement-power-loss-watermark-calculator-skip-latest-only-b.md](./02-implement-power-loss-watermark-calculator-skip-latest-only-b.md) | Implement power-loss watermark calculator (skip, latest_only, backfill_serial) | `01` (01-implement-sqlite-wal-schema-and-single-writer-batching-state.md) | `ready-for-agent` |
| `03` | [03-implement-linux-cgroup-v2-scope-manager-with-memory-max-and-.md](./03-implement-linux-cgroup-v2-scope-manager-with-memory-max-and-.md) | Implement Linux cgroup v2 scope manager with memory.max and cgroup.kill teardown | `02` (02-implement-power-loss-watermark-calculator-skip-latest-only-b.md) | `ready-for-agent` |
| `04` | [04-add-crash-recovery-orphan-reaper-on-daemon-startup.md](./04-add-crash-recovery-orphan-reaper-on-daemon-startup.md) | Add crash-recovery orphan reaper on daemon startup | `03` (03-implement-linux-cgroup-v2-scope-manager-with-memory-max-and-.md) | `ready-for-agent` |
