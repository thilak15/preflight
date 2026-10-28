# Case Study: EdgeCron — How PreFlight Pivoted a Flawed Distributed Design

This case study shows a complete before-and-after PreFlight session on a developer pitch, demonstrating how Socratic interrogation and live GitHub issue mining expose fatal architectural assumptions before a single line of code is written.

---

## 1. The Initial User Pitch ("Before PreFlight")

> **Developer Pitch:**
> *"I want to build a lightweight distributed cron and workflow scheduler in Go for edge Linux gateways (factories, retail stores, IoT clusters). Existing tools like Apache Airflow and Temporal are way too heavy and need Postgres/Cassandra. I'll use embedded `etcd` (raft) across the edge nodes to coordinate jobs and run bash scripts on schedule."*

A typical "yes-man" LLM assistant immediately replies: *"Great idea! Here is a Go project layout with `go.etcd.io/etcd/server/v3` and a cron parser..."*

---

## 2. PreFlight Execution Transcript

### Round 1 — Socratic Interrogation (`problem`, `scope`, `memory`, `bottlenecks`)

PreFlight initializes `.preflight/state.json` (`0%` Readiness — **LOCKED**) and challenges the initial pitch:

> **❓ Q1 — Embedded `etcd` Quorum Under Edge Network Partitions (`bottlenecks`):**
> You pitched running an embedded `etcd` Raft cluster across factory/retail edge nodes to avoid Postgres.
> In Raft, if a 3-node edge cluster loses WAN/LAN connectivity or 2 nodes reboot during a power flicker, quorum is lost and **zero local cron jobs can fire** on the surviving node—even for purely local health checks or data buffering.
> Do edge nodes actually need cross-node distributed consensus to schedule local jobs, or does each edge gateway need autonomous local execution with asynchronous status sync?
>
> ➡️ **Recommended:** Drop distributed Raft/`etcd` on edge nodes. Run an autonomous single-node daemon backed by local SQLite (WAL mode) on each gateway so local jobs run during 100% network blackouts.

> **Developer Answer:** *"Wait, that's a good point. If the internet goes down at a retail store, local backups and sensor collection still have to run. Let's drop etcd and make each node autonomous with SQLite WAL."*

---

### Step 2 — GitHub Prior-Art & Pain-Point Scout (`scout.py`)

PreFlight runs `scout.py`:

```bash
python3 skills/preflight/scripts/scout.py --workspace . \
  -q "dag scheduler single binary" \
  -q "cron alternative web ui go" \
  -q "distributed cron etcd"
```

#### Discovered Prior Art & Mined Pain Points:
1. **Active Incumbent — `dagu-org/dagu` (⭐ 6,500+, Go)**:Already provides a single-binary DAG runner and cron alternative with zero external DBMS!
2. **Graveyard / Dormant Repos — `dkron/dkron` & archived etcd-cron wrappers**: Multiple Raft-based cron tools stalled or accumulated open issues around split-brain quorum recovery on unstable networks.
3. **Mined Bug / Failure Mode (`dagu-org/dagu` open issues & comments)**:
   - **Orphaned child processes on daemon crash / timeout**: When a parent scheduler process is killed (`SIGKILL`) or a step times out, grand-child bash processes continue running in the background and hold file locks or ports.
   - **Top Comment Insight**: *"Standard `cmd.Process.Kill()` in Go only kills the immediate shell PID, not double-forked child processes. On Linux you have to put each step in a dedicated process group (`Setpgid: true`) or ephemeral cgroup v2 scope (`cgroup.kill`)."*
   - **Concurrent SQLite / File State Contention**: High-frequency step heartbeats from 50+ parallel jobs cause lock contention unless writes are serialized through a single batching writer.

---

### Round 2 — Challenging Differentiation with Mined GitHub Evidence

> **❓ Q2 — Why Not Just Use `dagu-org/dagu`? (`differentiation`):**
> `scout.py` found `dagu-org/dagu` (6,500+ stars, Go single binary, local DAG YAML files, built-in Web UI). If you just build "a single-binary Go DAG runner with SQLite", you are reinventing `dagu`.
> However, mined issues on `dagu` and similar Go runners show three concrete gaps for industrial edge deployments:
> 1. **Orphan Process Leaks**: Subprocesses survive `SIGKILL` or step timeouts unless isolated in Linux `cgroups v2` (`cgroup.kill`) with hard memory/CPU caps per step.
> 2. **Idempotent Catch-Up Policy**: When an edge box loses power for 4 hours and boots back up, naive cron runners either drop all missed runs or stampede 240 missed 1-minute jobs at once.
> 3. **SQLite WAL Write Serialization**: 50 concurrent job heartbeats hit `SQLITE_BUSY` without a single-writer batch loop.
>
> Should we pivot EdgeCron's scope specifically to **Deterministic Linux Edge Execution** (enforcing `cgroups v2` resource/orphan isolation + explicit power-loss `catchup_policy: skip | latest_only | backfill_serial` + single-writer SQLite WAL)?
>
> ➡️ **Recommended:** Yes — lock these three guarantees as EdgeCron's core differentiation and record ADR-0001 (Autonomous SQLite WAL over Raft) and ADR-0002 (Linux cgroup v2 Step Isolation).

> **Developer Answer:** *"Yes! Cgroup v2 memory/orphan control and power-outage catch-up policies are the exact problems we actually hit on edge boxes."*

---

## 3. Before vs. After Architecture Comparison

| Aspect | Before PreFlight (Initial Pitch) | After PreFlight (Validated Spec) |
| :--- | :--- | :--- |
| **Coordination Model** | Embedded `etcd` Raft cluster across edge nodes | Autonomous single-node daemon with SQLite WAL (`ADR-0001`) |
| **Offline / Partition Behavior** | **Total outage** when quorum is lost during WAN/LAN cut | **100% local availability** during network blackouts |
| **Process Isolation** | Naive `os/exec` bash execution (leaks orphan processes on crash) | Per-step Linux `cgroups v2` scope (`cgroup.kill` + `memory.max` limits, `ADR-0002`) |
| **Power-Loss Recovery** | Unspecified (risk of 200x job stampede on reboot) | Explicit per-DAG `catchup_policy` (`skip`, `latest_only`, `backfill_serial`) |
| **Prior-Art Awareness** | Unaware of `dagu-org/dagu` (6.5k stars) | Directly differentiated against `dagu` on cgroup isolation and power-recovery semantics |
