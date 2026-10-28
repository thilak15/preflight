# ADR-0002: Linux cgroups v2 Per-Step Isolation and Node Concurrency Caps

- **Status:** Accepted
- **Date:** 2026-10-28
- **Dimension:** `bottlenecks`

## Decision

Place every DAG step in a dedicated `/sys/fs/cgroup/edgecron/<run_id>/<step_id>` scope enforcing `memory.max`, `cpu.max`, and `cgroup.kill` on timeout, gated by a node-level `max_parallel_jobs` semaphore (`dkron-io/dkron#966`).

## Context & Rationale

Prevents double-forked grandchild processes from leaking after step timeouts and prevents 80-node job shifts (`dkron-io/dkron#966`) from OOM-killing a 1GB edge gateway.

## Considered & Rejected Alternatives

Standard Go `os/exec` `cmd.Process.Kill()` without cgroup containment or unbounded parallel job spawning.
