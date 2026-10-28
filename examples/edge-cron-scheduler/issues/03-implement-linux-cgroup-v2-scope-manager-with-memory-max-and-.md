# 03: Implement Linux cgroup v2 scope manager with memory.max and cgroup.kill teardown

**What to build:** Implement Linux cgroup v2 scope manager with memory.max and cgroup.kill teardown

**Blocked by:** `02` (02-implement-power-loss-watermark-calculator-skip-latest-only-b.md)

**Status:** ready-for-agent

## Locked Architecture & Stack Constraints

- **Spec Reference:** `.preflight/SPEC.md` & `.preflight/STACK.md`
- **Memory & Agent Communication (`transactional-db`):** In-process typed Go channels feeding a single 100ms batch-writer goroutine into SQLite WAL

### Day-1 Stack (`NOW` Tools to Use)
- **Go Modules (go.sum)** (`go.mod + go.sum`): Cryptographic dependency pinning and reproducible static binary builds — _Built into Go toolchain; guarantees identical module checksums across dev and CI without external package managers_
- **modernc.org/sqlite** (`go.mod`): CGo-free embedded SQLite3 engine in WAL mode — _Allows compiling a pure static Linux binary (CGO_ENABLED=0) for amd64/arm64 edge gateways without glibc mismatches_
- **Docker (Multi-stage build + privileged cgroup test container)** (`Dockerfile`): Consistent cross-compilation and integration testing of Linux cgroup v2 teardown — _Developers on macOS need a Linux kernel container to test /sys/fs/cgroup/edgecron/cgroup.kill behavior_
- **GitHub Actions + golangci-lint** (`.github/workflows/ci.yml`): Automated unit tests, race-detector runs (go test -race), and static analysis on every PR — _Catches concurrency bugs in the single-writer SQLite batch loop before merge_

### Locked ADRs to Respect
- **ADR-0001 (Autonomous Local SQLite WAL Over Embedded etcd Raft)**: Run each edge gateway as an autonomous scheduler backed by local SQLite WAL instead of a multi-node etcd Raft cluster.
- **ADR-0002 (Linux cgroups v2 Per-Step Process Isolation)**: Spawn every DAG step inside a dedicated /sys/fs/cgroup/edgecron/<run_id>/<step_id> scope with memory.max and teardown via cgroup.kill.

### Red-Team Mitigations to Enforce
- **[CRITICAL] Embedded etcd Quorum Loss Halts All Local Jobs (Pivoted in Round 1)**: Replaced embedded etcd with autonomous per-node SQLite WAL (ADR-0001).
- **[HIGH] Post-Outage Cron Stampede on Reboot**: Enforce explicit catchup_policy (default: latest_only) evaluated against the SQLite watermark before scheduling.

## Acceptance Criteria

- [ ] End-to-end vertical slice for **Implement Linux cgroup v2 scope manager with memory.max and cgroup.kill teardown** is implemented and verifiable.
- [ ] Unit/integration tests written test-first covering happy path and stress-tested edge cases.
- [ ] Respects all locked ADRs in `docs/adr/` and Day-1 stack constraints in `.preflight/STACK.md`.
- [ ] Full test suite passes with zero regressions.
