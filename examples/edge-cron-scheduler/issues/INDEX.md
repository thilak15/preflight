# Ordered Implementation Tickets: EdgeCron

Work these tickets in order (one vertical slice per session/commit). Use `Title :: Details :: BlockedBy` in `set-design --step` to declare custom or parallel dependency edges:

| # | Ticket File | Title | Blocked By | Status |
| :---: | :--- | :--- | :--- | :---: |
| `01` | [01-bootstrap-go-1-23-module-pure-go-sqlite-wal-schema-dag-runs.md](./01-bootstrap-go-1-23-module-pure-go-sqlite-wal-schema-dag-runs.md) | Bootstrap Go 1.23 module, pure-Go SQLite WAL schema (`dag_runs`, `step_attempts`, `step_logs_fts`, `sync_outbox`), and single-writer 100ms batch channel (`ADR-0001`) | None (can start immediately) | `ready-for-agent` |
| `02` | [02-implement-linux-cgroups-v2-step-runner-memory-max-cpu-max.md](./02-implement-linux-cgroups-v2-step-runner-memory-max-cpu-max.md) | Implement Linux cgroups v2 step runner (`memory.max`, `cpu.max`, `cgroup.kill`) with `Setpgid` fallback and per-node `max_parallel_jobs` semaphore (`ADR-0002`, `dkron-io/dkron#966`) | `01` (01-bootstrap-go-1-23-module-pure-go-sqlite-wal-schema-dag-runs.md) | `ready-for-agent` |
| `03` | [03-implement-dag-yaml-parser-cron-schedule-planner-flc1125-go.md](./03-implement-dag-yaml-parser-cron-schedule-planner-flc1125-go.md) | Implement DAG YAML parser, cron schedule planner (`flc1125/go-cron`), and power-loss `catchup_policy` (`skip`, `latest_only`, `backfill_serial`, `dagucloud/dagu#695`) | `02` (02-implement-linux-cgroups-v2-step-runner-memory-max-cpu-max.md) | `ready-for-agent` |
| `04` | [04-implement-failure-only-webhook-notifier-dkron-io-dkron-712.md](./04-implement-failure-only-webhook-notifier-dkron-io-dkron-712.md) | Implement failure-only webhook notifier (`dkron-io/dkron#712`), 50MB FTS5 log ring-buffer pruning, and asynchronous mTLS `sync_outbox` hub pusher (`dagucloud/dagu#1260`) | `03` (03-implement-dag-yaml-parser-cron-schedule-planner-flc1125-go.md) | `ready-for-agent` |
