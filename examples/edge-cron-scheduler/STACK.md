# Stack Explained & Memory Architecture: EdgeCron

## 1. Stack Explained (Tooling, Alternatives, Now vs. Later & Proof Status)

| Tool | Stage (`Now` / `Later`) | What Job It Does | Why Needed | Alternative Considered | Config Proof & Verification |
| :--- | :---: | :--- | :--- | :--- | :--- |
| **Go Modules (go.sum)** (`dependency-lock`) | **NOW** | Cryptographic dependency locking and reproducible static Go builds | Verifies exact module SHA-256 checksums with `CGO_ENABLED=0` for zero-libc-drift Linux ARM64/AMD64 binaries. | Vendored `vendor/` tree in git (bloats diffs); dynamically linked CGo dependencies (breaks across older factory glibc versions). | ✅ Verified (`scout:go.sum`): `go.sum` |
| **modernc-org/sqlite + flc1125/go-cron** (`core-oss`) | **NOW** | CGo-free embedded SQLite WAL engine and cron schedule parser | Scouted via `scout.py -t`: `modernc-org/sqlite` (BSD-3-Clause) compiles SQLite to pure Go without CGo, and `flc1125/go-cron` (MIT) provides cron parsing with second/descriptor support. | mattn/go-sqlite3 (requires CGo and cross-compiler toolchains); etcd/boltdb (lacks relational SQL + FTS5 log indexing). | ✅ Verified (`scout:go.sum`): `go.sum` |
| **Docker (Dockerfile)** (`container-runtime`) | **NOW** | Multi-stage static binary build and privileged cgroups v2 integration test container | Proven across scouted incumbents (`dkron-io/dkron`, `dagucloud/dagu`); lets CI test cgroup v2 `memory.max` and `cgroup.kill` behavior reproducibly. | Host-only `go test` (cannot safely simulate OOM kills or power-loss recovery on developer laptops). | ✅ Verified (`scout:Dockerfile`): `Dockerfile` |
| **GitHub Actions (.github/workflows) + Makefile** (`ci-cd-quality`) | **NOW** | Automated cross-arch matrix builds, race-detector tests (`go test -race`), and static analysis | Proven in `dkron-io/dkron` and `dagucloud/dagu`; catches concurrency bugs in the single-writer SQLite channel on every PR. | Manual local release builds (high risk of shipping untested ARM64 binaries). | ✅ Verified (`scout:.github/workflows`): `.github/workflows` |
| **Kubernetes / Helm Charts** (`orchestration-deploy`) | **LATER** | Multi-cluster central hub orchestration for >1,000 edge gateways | Defer until the central observability hub is built in V2; V1 targets single-binary systemd deployment on individual edge nodes (`docker-compose.yml` for local dev). | systemd unit + single static binary (selected NOW for Day-1 edge node deployment). | ⚠️ Claimed / Unverified: `Chart.yaml` |

- **Verification Summary:** 4 Verified (backed by `scout.py` or workspace files) | 1 Claimed / Unverified (recommended for target architecture, not yet present on disk).

## 2. Memory, State & Agent Communication Architecture

- **Primary Memory Strategy:** `transactional-db`
- **Secondary / Combined Strategies:** `lexical-fts`
- **Combined Memory Profile:** `transactional-db (primary) + lexical-fts (secondary)`
- **Agent / Component Communication Pattern:** Single-writer Go channel (`chan StateTransition`) batching step heartbeats from worker goroutines into SQLite WAL every 100ms; asynchronous mTLS push outbox (`sync_outbox`) to hub.
- **Workflow Memory Lifecycle:** Append-only `dag_runs` and `step_attempts` state transitions committed with `PRAGMA synchronous=NORMAL`, paired with SQLite FTS5 over structured step stderr/stdout logs (`step_logs_fts`) and a 50MB ring-buffer cap.
- **Why This Strategy (vs. RAG / Vector DB / Alternatives):** EdgeCron schedules deterministic DAG transitions and searches exact exit codes/error symbols in local step logs. Embedded SQLite WAL + FTS5 provides ACID crash recovery and fast exact log search with zero external daemons, avoiding the Raft quorum loss seen in `dkron-io/dkron#1001` and the shared-filesystem coupling in `dagucloud/dagu#1260`.
- **Alternatives Considered:** Embedded etcd/Raft (`dkron-io/dkron#1001` — loses cluster quorum when 2 of 3 nodes restart or change IP); Flat YAML/JSON status files (`dagucloud/dagu#1260` — requires shared filesystem across workers); Vector DB / RAG (unnecessary overhead for deterministic state and exact log tokens).

### Anticipated Memory Failure Modes & Mitigations

- ⚠️ SQLITE_BUSY lock contention under 50+ concurrent step heartbeats -> Mitigated by funneling all writes through a single Go channel batching commits every 100ms.
- ⚠️ Unbounded disk growth on 8GB industrial eMMC flash -> Mitigated by 50MB per-DAG ring buffer and automatic 30-day run history pruning.

