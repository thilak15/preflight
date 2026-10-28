# ADR-0001: Autonomous Per-Node SQLite WAL Over Embedded Raft/etcd

- **Status:** Accepted
- **Date:** 2026-10-28
- **Dimension:** `memory`

## Decision

Each edge node runs an autonomous scheduler backed by local SQLite3 in WAL mode with a single-writer batching goroutine and an asynchronous mTLS `sync_outbox` queue.

## Context & Rationale

`dkron-io/dkron#1001` proves that multi-node restarts or IP changes break Raft leader election until raft data is manually deleted. Edge gateways require 100% local scheduling availability during WAN blackouts.

## Considered & Rejected Alternatives

Embedded Raft/Serf cluster across edge nodes (as in `dkron-io/dkron` and `wj596/gojob`) or shared NFS worker directories (`dagucloud/dagu#1260`).
