# Case Study: EdgeCron — How PreFlight Pivoted a Flawed Distributed Design

> **Provenance & Reproducibility Note:**
> - **Dialogue Format:** The Socratic interview dialogue below is an **Illustrative Walkthrough** showing how PreFlight's frontier questions and developer answers flow in practice.
> - **Committed Live Evidence:** All repository star counts, config-file detections, dormant signals, and issue numbers (`dkron-io/dkron#1001`, `dkron-io/dkron#966`, `dkron-io/dkron#712`, `dagucloud/dagu#1260`, `dagucloud/dagu#695`, `dagucloud/dagu#2806`) come from a **real `scout.py` execution** committed in [`.preflight/prior-art.json`](./.preflight/prior-art.json), with the full locked state in [`.preflight/state.json`](./.preflight/state.json) and [`.preflight/decisions.json`](./.preflight/decisions.json).
> - **Canonical Tickets Destination:** [`.preflight/issues/`](./.preflight/issues/) is the canonical generator output of `render_blueprint.py` / `state.py export-tickets`; [`issues/`](./issues/) is committed as an unhidden root mirror so developers can browse tickets directly on GitHub without expanding dotfiles.

---

## 1. The Initial User Pitch ("Before PreFlight")

> **Developer Pitch:**
> *"I want to build a lightweight distributed cron and workflow scheduler in Go for edge Linux gateways (factories, retail stores, IoT clusters). Existing tools like Apache Airflow and Temporal are way too heavy and need Postgres/Cassandra. I'll use embedded Raft/Serf across the edge nodes to coordinate jobs and run bash scripts on schedule."*

A typical "yes-man" LLM assistant immediately replies: *"Great idea! Here is a Go project layout with Raft consensus and a cron parser..."*

---

## 2. Illustrative PreFlight Walkthrough (Backed by Committed `prior-art.json`)

### Round 1 — Socratic Interrogation (`problem`, `scope`, `memory`, `bottlenecks`)

PreFlight initializes `.preflight/state.json` (`0%` Readiness — **LOCKED**) and challenges the initial pitch:

> **❓ Q1 — Embedded Raft Quorum Under Edge Network Partitions (`bottlenecks`):**
> You pitched running an embedded Raft cluster across factory/retail edge nodes to avoid Postgres.
> In Raft, if a 3-node edge cluster loses WAN/LAN connectivity or 2 nodes restart with new dynamic IPs, quorum is lost and **zero local cron jobs can fire** on the surviving node—even for purely local health checks or data buffering.
> Do edge nodes actually need cross-node distributed consensus to schedule local jobs, or does each edge gateway need autonomous local execution with asynchronous status sync?
>
> ➡️ **Recommended:** Drop distributed Raft on edge nodes. Run an autonomous single-node daemon backed by local SQLite (WAL mode) on each gateway so local jobs run during 100% network blackouts.

> **Developer Answer:** *"Wait, that's a good point. If the internet goes down at a retail store, local backups and sensor collection still have to run. Let's drop Raft and make each node autonomous with SQLite WAL."*

---

### Step 2 — Live GitHub Prior-Art, Config & Pain-Point Scout (`scout.py`)

PreFlight runs `scout.py` (output committed in [`.preflight/prior-art.json`](./.preflight/prior-art.json)):

```bash
python3 skills/preflight/scripts/scout.py --workspace examples/edge-cron-scheduler \
  -q "dagu language:go" \
  -q "dkron language:go" \
  -q "distributed cron language:go" \
  --topic "cron-scheduler" \
  -t "modernc.org/sqlite" \
  -t "robfig/cron"
```

#### Discovered Prior Art & Mined Pain Points (from `.preflight/prior-art.json`):
1. **Active Incumbents**:
   - **[`dkron-io/dkron`](https://github.com/dkron-io/dkron) (⭐ 4,740, Go)** — Verified configs: `go.sum`, `Dockerfile`, `docker-compose.yml`, `.github/workflows`, `Makefile`.
   - **[`dagucloud/dagu`](https://github.com/dagucloud/dagu) (⭐ 4,468, Go)** — Verified configs: `go.sum`, `Dockerfile`, `.devcontainer`, `.github/workflows`, `Makefile`.
   - **[`egeominotti/bunqueue`](https://github.com/egeominotti/bunqueue) (⭐ 590, TypeScript/Bun)** — SQLite-by-default job queue.
2. **Dormant / Graveyard Check (>365d inactivity heuristic)**:
   - [`shunfei/cronsun`](https://github.com/shunfei/cronsun) (⭐ 2,908 — dormant >870d), [`wj596/gojob`](https://github.com/wj596/gojob) (⭐ 127 — dormant >1,390d), [`imiskolee/litecron`](https://github.com/imiskolee/litecron) (⭐ 45 — dormant >3,130d). *(Note: >365d inactivity is recorded as a maintenance heuristic, not causal proof of architectural failure.)*
3. **Scouted OSS Building Blocks (`-t`)**:
   - [`modernc-org/sqlite`](https://github.com/modernc-org/sqlite) (`BSD-3-Clause`, pure-Go SQLite without CGo) and [`flc1125/go-cron`](https://github.com/flc1125/go-cron) (`MIT`, maintained `robfig/cron` fork).
4. **Verified Issues & Developer Comments Mined from Incumbents**:
   - **[`dkron-io/dkron#1001`](https://github.com/dkron-io/dkron/issues/1001)** (*"No way to recover cluster without deleting raft data. Older pod IPs are getting used on multipler server failure"*, 👍 5 | 💬 11):
     > 💬 **@rmuehlbauer**: *"after all dkron nodes/servers were down simultaneously I'm not able to get the cluster back working again - leader election never succeeds."*
   - **[`dkron-io/dkron#966`](https://github.com/dkron-io/dkron/issues/966)** (*"Limit number of parrallel jobs per node/worker"*, 👍 2 | 💬 4):
     > 💬 **@LevonW-IIS**: *"This would be incredibly useful. Without this feature, will likely have to move to using a different task scheduler."*
   - **[`dkron-io/dkron#712`](https://github.com/dkron-io/dkron/issues/712)** (*"Webhook execution only on failure"*, 👍 5 | 💬 2).
   - **[`dagucloud/dagu#1260`](https://github.com/dagucloud/dagu/issues/1260)** (*"Worker Sync Mode for Remote Storage"*, 👍 4 | 💬 5):
     > *"Currently a distributed DAG run only succeeds when workers, coordinators, schedulers, and the UI server share the same filesystem tree."*
   - **[`dagucloud/dagu#695`](https://github.com/dagucloud/dagu/issues/695)** (*"scheduler: Ability to create a DAG where it is repeatable given start date, end date and CRON"*, 👍 2).

---

### Round 2 — Challenging Differentiation with Mined GitHub Evidence

> **❓ Q2 — Differentiating Against `dkron-io/dkron` and `dagucloud/dagu` (`differentiation`):**
> `scout.py` found `dkron-io/dkron` (4,740 stars) and `dagucloud/dagu` (4,468 stars). Mined issues prove three concrete operational pain points on edge nodes:
> 1. **Raft Cluster Brick on Dual Restart (`dkron-io/dkron#1001`)**: Restarting 2 nodes or changing IPs stalls Raft leader election until Raft data is wiped.
> 2. **Shared-Filesystem Coupling (`dagucloud/dagu#1260`)**: Distributed workers require a shared filesystem tree unless an asynchronous sync outbox is built.
> 3. **Node Overload & Missing Concurrency Caps (`dkron-io/dkron#966`) + Date-Bounded Catch-Up (`dagucloud/dagu#695`)**: Without per-node `max_parallel_jobs`, Linux `cgroups v2` (`memory.max` + `cgroup.kill`), and an explicit reboot `catchup_policy`, a 4-hour power outage can stampede 240 missed 1-minute jobs at once.
>
> Should we lock EdgeCron's architecture around **Autonomous SQLite WAL + FTS5 (`ADR-0001`)** and **Linux `cgroups v2` Step Isolation + Node Concurrency Semaphores (`ADR-0002`)**?
>
> ➡️ **Recommended:** Yes — lock both ADRs, use `modernc-org/sqlite` (CGo-free) + `flc1125/go-cron`, and generate the 4 ordered vertical-slice tickets.

> **Developer Answer:** *"Yes! Seeing `dkron-io/dkron#1001` where Raft bricks after a 2-node restart completely validates dropping Raft. Let's lock ADR-0001 and ADR-0002."*

---

## 3. Before vs. After Architecture Comparison

| Aspect | Before PreFlight (Initial Pitch) | After PreFlight (Validated Spec) |
| :--- | :--- | :--- |
| **Coordination Model** | Embedded Raft cluster across edge nodes | Autonomous single-node daemon with pure-Go SQLite WAL (`ADR-0001`, avoids `dkron-io/dkron#1001`) |
| **Remote Sync** | Synchronous Raft consensus or shared NFS | Asynchronous mTLS `sync_outbox` push queue (solves `dagucloud/dagu#1260`) |
| **Process & Node Isolation** | Unbounded `os/exec` bash scripts | Per-step Linux `cgroups v2` (`memory.max`, `cgroup.kill`) + per-node `max_parallel_jobs` (`ADR-0002`, `dkron-io/dkron#966`) |
| **Power-Loss Recovery** | Unspecified (risk of 240x job stampede on reboot) | Explicit per-DAG `catchup_policy` (`skip`, `latest_only`, `backfill_serial`, `dagucloud/dagu#695`) |
| **Alerting Noise** | Webhook on every run | Failure-only webhook policy (`dkron-io/dkron#712`) |
