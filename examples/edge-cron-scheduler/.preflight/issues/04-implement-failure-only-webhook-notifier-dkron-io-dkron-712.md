# 04: Implement failure-only webhook notifier (`dkron-io/dkron#712`), 50MB FTS5 log ring-buffer pruning, and asynchronous mTLS `sync_outbox` hub pusher (`dagucloud/dagu#1260`)

**What to build:** Implement failure-only webhook notifier (`dkron-io/dkron#712`), 50MB FTS5 log ring-buffer pruning, and asynchronous mTLS `sync_outbox` hub pusher (`dagucloud/dagu#1260`)

**Blocked by:** `03` (03-implement-dag-yaml-parser-cron-schedule-planner-flc1125-go.md)

**Status:** ready-for-agent

## Locked Architecture & Stack Constraints

- **Spec Reference:** `.preflight/SPEC.md` & `.preflight/STACK.md`
- **Memory & Agent Communication (`transactional-db (primary) + lexical-fts (secondary)`):** Single-writer Go channel (`chan StateTransition`) batching step heartbeats from worker goroutines into SQLite WAL every 100ms; asynchronous mTLS push outbox (`sync_outbox`) to hub.

### Day-1 Stack (`NOW` Tools to Use)
- **Go Modules (go.sum)** (`go.sum` — `verified`): Cryptographic dependency locking and reproducible static Go builds — _Verifies exact module SHA-256 checksums with `CGO_ENABLED=0` for zero-libc-drift Linux ARM64/AMD64 binaries._
- **modernc-org/sqlite + flc1125/go-cron** (`go.sum` — `verified`): CGo-free embedded SQLite WAL engine and cron schedule parser — _Scouted via `scout.py -t`: `modernc-org/sqlite` (BSD-3-Clause) compiles SQLite to pure Go without CGo, and `flc1125/go-cron` (MIT) provides cron parsing with second/descriptor support._
- **Docker (Dockerfile)** (`Dockerfile` — `verified`): Multi-stage static binary build and privileged cgroups v2 integration test container — _Proven across scouted incumbents (`dkron-io/dkron`, `dagucloud/dagu`); lets CI test cgroup v2 `memory.max` and `cgroup.kill` behavior reproducibly._
- **GitHub Actions (.github/workflows) + Makefile** (`.github/workflows` — `verified`): Automated cross-arch matrix builds, race-detector tests (`go test -race`), and static analysis — _Proven in `dkron-io/dkron` and `dagucloud/dagu`; catches concurrency bugs in the single-writer SQLite channel on every PR._

### Locked ADRs to Respect
- **ADR-0001 (Autonomous Per-Node SQLite WAL Over Embedded Raft/etcd)**: Each edge node runs an autonomous scheduler backed by local SQLite3 in WAL mode with a single-writer batching goroutine and an asynchronous mTLS `sync_outbox` queue.
- **ADR-0002 (Linux cgroups v2 Per-Step Isolation and Node Concurrency Caps)**: Place every DAG step in a dedicated `/sys/fs/cgroup/edgecron/<run_id>/<step_id>` scope enforcing `memory.max`, `cpu.max`, and `cgroup.kill` on timeout, gated by a node-level `max_parallel_jobs` semaphore (`dkron-io/dkron#966`).

### Red-Team Mitigations to Enforce
- **[CRITICAL] Post-Outage Reboot Stampede on High-Frequency Schedules**: Require an explicit `catchup_policy` (`skip`, `latest_only`, or `backfill_serial` with date bounds as requested in `dagucloud/dagu#695`), defaulting to `latest_only`.
- **[HIGH] Unprivileged Or cgroup v1 Kernel Fallback**: Run a startup pre-check verifying `/sys/fs/cgroup/cgroup.controllers` delegation; fail fast with a clear `systemd` `Delegate=yes` unit snippet or explicitly require `--allow-pgid-fallback` (`Setpgid: true` + `PR_SET_PDEATHSIG`).

## Acceptance Criteria

- [ ] Deliverable verified: **Implement failure-only webhook notifier (`dkron-io/dkron#712`), 50MB FTS5 log ring-buffer pruning**.
- [ ] Deliverable verified: **asynchronous mTLS `sync_outbox` hub pusher (`dagucloud/dagu#1260`)**.
- [ ] Enforces **ADR-0001 (Autonomous Per-Node SQLite WAL Over Embedded Raft/etcd)**: Each edge node runs an autonomous scheduler backed by local SQLite3 in WAL mode with a single-writer batching goroutine and an asynchronous mTLS `sync_outbox` queue.
- [ ] Enforces **ADR-0002 (Linux cgroups v2 Per-Step Isolation and Node Concurrency Caps)**: Place every DAG step in a dedicated `/sys/fs/cgroup/edgecron/<run_id>/<step_id>` scope enforcing `memory.max`, `cpu.max`, and `cgroup.kill` on timeout, gated by a node-level `max_parallel_jobs` semaphore (`dkron-io/dkron#966`).
- [ ] Stress-tested against **[CRITICAL] Post-Outage Reboot Stampede on High-Frequency Schedules**: Require an explicit `catchup_policy` (`skip`, `latest_only`, or `backfill_serial` with date bounds as requested in `dagucloud/dagu#695`), defaulting to `latest_only`.
- [ ] Automated unit/integration tests for `implement-failure-only-webhook` pass with zero regressions.
