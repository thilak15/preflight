# Stack Explained & Memory Architecture: EdgeCron

## 1. Stack Explained (Config-Verified Tooling, Alternatives & Now vs. Later)

| Tool | Stage (`Now` / `Later`) | What Job It Does | Why Needed | Alternative Considered | Config Proof in Prior-Art |
| :--- | :---: | :--- | :--- | :--- | :--- |
| **Go Modules (go.sum)** (`dependency-lock`) | **NOW** | Cryptographic dependency pinning and reproducible static binary builds | Built into Go toolchain; guarantees identical module checksums across dev and CI without external package managers | Vendored directory (bloats git history unless air-gapped build is required) | `go.mod + go.sum` |
| **modernc.org/sqlite** (`core-oss`) | **NOW** | CGo-free embedded SQLite3 engine in WAL mode | Allows compiling a pure static Linux binary (CGO_ENABLED=0) for amd64/arm64 edge gateways without glibc mismatches | mattn/go-sqlite3 (requires CGo and matching target libc); etcd (rejected due to quorum loss) | `go.mod` |
| **Docker (Multi-stage build + privileged cgroup test container)** (`container-runtime`) | **NOW** | Consistent cross-compilation and integration testing of Linux cgroup v2 teardown | Developers on macOS need a Linux kernel container to test /sys/fs/cgroup/edgecron/cgroup.kill behavior | Bare host builds (cannot test Linux cgroups v2 natively on macOS) | `Dockerfile` |
| **GitHub Actions + golangci-lint** (`ci-cd-quality`) | **NOW** | Automated unit tests, race-detector runs (go test -race), and static analysis on every PR | Catches concurrency bugs in the single-writer SQLite batch loop before merge | Local pre-push hooks only (can be bypassed) | `.github/workflows/ci.yml` |
| **Kubernetes / k3s Fleet Controller** (`orchestration-deploy`) | **LATER** | Centralized fleet rollout across 500+ edge gateways | Defer until V2; V1 targets single-binary systemd installation on constrained 1GB RAM nodes where k3s overhead (~500MB) is too heavy | systemd unit file + atomic binary swap (used NOW for V1) | `Chart.yaml / k8s/ (Deferred)` |

## 2. Memory, State & Agent Communication Architecture

- **Selected Memory Strategy:** `transactional-db`
- **Agent / Component Communication Pattern:** In-process typed Go channels feeding a single 100ms batch-writer goroutine into SQLite WAL
- **Workflow Memory Flow:** Ticker reads watermark -> Supervisor spawns cgroup step -> Heartbeats batch-committed to SQLite WAL -> Startup scanner reaps orphaned RUNNING rows
- **Why This Strategy (vs. RAG / Vector DB / Alternatives):** EdgeCron stores structured state transitions and cron watermarks, not unstructured text; SQLite WAL provides ACID durability on power loss with 0MB idle overhead, whereas a Vector DB / RAG or external Postgres adds zero value and breaks offline autonomy
- **Alternatives Considered:** Embedded etcd Raft (rejected: loses quorum on 2-node WAN splits); Redis (volatile on power loss); Vector DB / RAG (not applicable to deterministic DAG state)

### Anticipated Memory Failure Modes & Mitigations

- ⚠️ SQLITE_BUSY lock contention when 50+ steps emit heartbeats concurrently -> Mitigated by funneling all writes through a single 100ms batching goroutine
- ⚠️ Stale RUNNING state after sudden power pull -> Mitigated by startup reconciliation against /sys/fs/cgroup/edgecron/<run_id>

