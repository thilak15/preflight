#!/usr/bin/env python3
"""Unit and integration tests for PreFlight helper scripts (`state.py`, `scout.py`, `render_blueprint.py`)."""

from __future__ import annotations

import base64
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "skills" / "preflight" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import render_blueprint  # noqa: E402
import scout  # noqa: E402
import state  # noqa: E402


class _FakeHTTPResponse:
    def __init__(self, payload: object, headers: dict[str, str] | None = None) -> None:
        self._bytes = json.dumps(payload).encode("utf-8")
        self.headers = headers or {
            "X-RateLimit-Remaining": "29",
            "X-RateLimit-Limit": "30",
            "X-RateLimit-Reset": "1999999999",
        }

    def read(self) -> bytes:
        return self._bytes

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


class TestPreFlightPipeline(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_evidence_gates_block_shallow_self_certification(self) -> None:
        state.main(
            [
                "--workspace",
                str(self.workspace),
                "init",
                "--name",
                "EdgeScheduler",
                "--summary",
                "Single-binary job scheduler for edge Linux nodes",
                "--runtime",
                "Rust 1.80",
                "--stack",
                "Rust,SQLite,gRPC",
            ]
        )

        # 1. Attempting score=20 with a short 2-word summary ("Locked problem") MUST fail
        rc_short = state.main(
            [
                "--workspace",
                str(self.workspace),
                "update-dimension",
                "--dimension",
                "problem",
                "--score",
                "20",
                "--summary",
                "Locked problem",
                "--edge-case",
                "Edge case 1",
                "--edge-case",
                "Edge case 2",
            ]
        )
        self.assertEqual(rc_short, 2)

        # 2. Attempting score=20 with < 2 edge cases MUST fail
        rc_no_ec = state.main(
            [
                "--workspace",
                str(self.workspace),
                "update-dimension",
                "--dimension",
                "problem",
                "--score",
                "20",
                "--summary",
                "Replaces heavy Python Airflow deployments on resource-constrained edge nodes with a 15MB binary.",
                "--edge-case",
                "Only one edge case provided",
            ]
        )
        self.assertEqual(rc_no_ec, 2)

        # 3. Attempting score=20 on 'memory' BEFORE running set-memory-arch MUST fail
        rc_mem_unset = state.main(
            [
                "--workspace",
                str(self.workspace),
                "update-dimension",
                "--dimension",
                "memory",
                "--score",
                "20",
                "--summary",
                "Single-writer SQLite WAL mode with bounded 50MB log ring buffer.",
                "--edge-case",
                "Concurrent step heartbeats serialized via single Go channel",
                "--edge-case",
                "Power-loss recovery replays WAL frames cleanly",
            ]
        )
        self.assertEqual(rc_mem_unset, 2)

        # 4. Attempting set-memory-arch with 0 failure modes MUST fail
        rc_mem_no_fm = state.main(
            [
                "--workspace",
                str(self.workspace),
                "set-memory-arch",
                "--strategy",
                "transactional-db",
                "--communication",
                "Single-writer channel",
                "--rationale",
                "Deterministic state transitions",
            ]
        )
        self.assertEqual(rc_mem_no_fm, 2)

        # 5. Attempting to score differentiation > 0 before running scout.py (.preflight/prior-art.json missing) MUST fail
        rc_no_scout = state.main(
            [
                "--workspace",
                str(self.workspace),
                "update-dimension",
                "--dimension",
                "differentiation",
                "--score",
                "10",
                "--summary",
                "Unlike existing schedulers, runs as a single static binary with embedded SQLite.",
            ]
        )
        self.assertEqual(rc_no_scout, 2)

    def test_full_evidence_verified_lifecycle_and_spec_export(self) -> None:
        state.main(
            [
                "--workspace",
                str(self.workspace),
                "init",
                "--name",
                "EdgeCron",
                "--summary",
                "Deterministic DAG runner for disconnected edge gateways",
                "--runtime",
                "Go 1.23",
                "--stack",
                "Go,SQLite WAL,mTLS",
            ]
        )

        # Write a realistic prior-art.json as produced by scout.py
        prior_art = {
            "scouted_at": "2026-10-28T00:00:00+00:00",
            "auth_source": "gh-cli",
            "rate_limit": {"search_api_quota": "30 req/min", "remaining": 28, "limit": 30},
            "queries": ["dagu language:go", "dkron language:go"],
            "active_incumbents": [
                {
                    "full_name": "dagucloud/dagu",
                    "html_url": "https://github.com/dagucloud/dagu",
                    "description": "Self-hostable workflow orchestrator in a single binary",
                    "stars": 4468,
                    "forks": 380,
                    "open_issues_count": 45,
                    "language": "Go",
                    "topics": ["workflow", "dag", "scheduler"],
                    "created_at": "2022-05-01T00:00:00Z",
                    "pushed_at": "2026-10-20T00:00:00Z",
                    "archived": False,
                    "inactive_days": 7,
                    "star_velocity_per_month": 81.29,
                    "classification": "active_incumbent",
                    "graveyard_reason": "",
                    "detected_configs": [
                        {"config_file": "Dockerfile", "tool": "Docker (Dockerfile)", "category": "container-runtime"}
                    ],
                }
            ],
            "graveyard_repos": [
                {
                    "full_name": "shunfei/cronsun",
                    "html_url": "https://github.com/shunfei/cronsun",
                    "description": "Distributed cron over etcd",
                    "stars": 2908,
                    "forks": 320,
                    "open_issues_count": 19,
                    "language": "Go",
                    "topics": [],
                    "created_at": "2019-01-01T00:00:00Z",
                    "pushed_at": "2023-01-01T00:00:00Z",
                    "archived": False,
                    "inactive_days": 874,
                    "star_velocity_per_month": 30.1,
                    "classification": "graveyard",
                    "graveyard_reason": "Dormant heuristic: no pushes in 874 days (>365d threshold)",
                }
            ],
            "observed_stack_configs": [
                {
                    "tool": "Docker (Dockerfile)",
                    "category": "container-runtime",
                    "config_file": "Dockerfile",
                    "repos": ["dagucloud/dagu"],
                }
            ],
            "pain_points": [
                {
                    "repo_full_name": "dagucloud/dagu",
                    "issue_number": 1260,
                    "title": "Worker Sync Mode for Remote Storage",
                    "issue_url": "https://github.com/dagucloud/dagu/issues/1260",
                    "category": "top_voted",
                    "labels": ["enhancement"],
                    "reactions_plus_one": 4,
                    "reactions_total": 4,
                    "comments_count": 5,
                    "body_excerpt": "Currently a distributed DAG run only succeeds when workers share the same filesystem tree.",
                    "top_comments": [
                        {
                            "author": "ghansham",
                            "reactions": 2,
                            "excerpt": "This feature is going to be a game changer for master worker coordination.",
                        }
                    ],
                    "created_at": "2026-04-10T00:00:00Z",
                }
            ],
            "warnings": [],
        }
        (self.workspace / ".preflight" / "prior-art.json").write_text(
            json.dumps(prior_art, indent=2), encoding="utf-8"
        )

        # Configure combined memory architecture (transactional-db + lexical-fts + episodic-agent-state)
        rc_mem = state.main(
            [
                "--workspace",
                str(self.workspace),
                "set-memory-arch",
                "--strategy",
                "transactional-db",
                "--secondary-strategy",
                "lexical-fts",
                "--secondary-strategy",
                "episodic-agent-state",
                "--communication",
                "Single-writer Go channel batching step heartbeats every 100ms into SQLite WAL",
                "--workflow",
                "Append-only state transitions + FTS5 log indexing",
                "--rationale",
                "Provides ACID recovery and exact log search without external servers",
                "--failure-mode",
                "SQLITE_BUSY under 50+ concurrent step heartbeats -> Mitigated by single writer goroutine",
            ]
        )
        self.assertEqual(rc_mem, 0)

        # Score the first 4 dimensions with real summaries and >=2 edge cases
        for dim in ("problem", "scope", "memory", "bottlenecks"):
            rc = state.main(
                [
                    "--workspace",
                    str(self.workspace),
                    "update-dimension",
                    "--dimension",
                    dim,
                    "--score",
                    "20",
                    "--summary",
                    f"Substantive architectural specification for {dim} with validated failure boundaries.",
                    "--edge-case",
                    f"{dim} edge case 1: network partition during execution",
                    "--edge-case",
                    f"{dim} edge case 2: power loss mid-transaction",
                ]
            )
            self.assertEqual(rc, 0)

        # Differentiation score=20 WITHOUT citing any repo in prior-art.json MUST fail
        rc_uncited = state.main(
            [
                "--workspace",
                str(self.workspace),
                "update-dimension",
                "--dimension",
                "differentiation",
                "--score",
                "20",
                "--summary",
                "Our scheduler is much faster and cleaner than generic competitors in the market.",
                "--edge-case",
                "Edge case A",
                "--edge-case",
                "Edge case B",
            ]
        )
        self.assertEqual(rc_uncited, 2)

        # Differentiation score=20 citing `dagucloud/dagu` and `shunfei/cronsun` succeeds
        rc_cited = state.main(
            [
                "--workspace",
                str(self.workspace),
                "update-dimension",
                "--dimension",
                "differentiation",
                "--score",
                "20",
                "--summary",
                "Unlike dagucloud/dagu (#1260 shared-filesystem requirement), EdgeCron uses an asynchronous mTLS outbox and avoids the etcd coupling in shunfei/cronsun.",
                "--edge-case",
                "Asynchronous mTLS outbox sync without shared NFS (solves dagucloud/dagu#1260)",
                "--edge-case",
                "Zero external coordination store required unlike shunfei/cronsun",
            ]
        )
        self.assertEqual(rc_cited, 0)

        # Even at 100% dimension score + memory strategy set, gate is STILL locked until >=1 tool, >=1 ADR, and >=1 Critique exist
        st = state.load_state(self.workspace)
        self.assertEqual(st["readiness_score"], 100)
        self.assertFalse(st["readiness_unlocked"])

        # Add a verified tool (Dockerfile is in prior-art.json observed_stack_configs) and an unverified tool (Chart.yaml)
        state.main(
            [
                "--workspace",
                str(self.workspace),
                "add-tool",
                "--category",
                "container-runtime",
                "--recommended",
                "Docker (Dockerfile)",
                "--stage",
                "now",
                "--config-proof",
                "Dockerfile",
                "--purpose",
                "Reproducible static binary build & cgroup v2 test harness",
                "--why",
                "Matches dagucloud/dagu setup",
                "--alternatives",
                "Bare host build",
            ]
        )
        state.main(
            [
                "--workspace",
                str(self.workspace),
                "add-tool",
                "--category",
                "orchestration-deploy",
                "--recommended",
                "Kubernetes Helm",
                "--stage",
                "later",
                "--config-proof",
                "Chart.yaml",
                "--purpose",
                "Central hub scaling",
                "--why",
                "Deferred until V2",
                "--alternatives",
                "Single binary systemd",
            ]
        )

        # Add ADR and Critique
        state.main(
            [
                "--workspace",
                str(self.workspace),
                "add-decision",
                "--title",
                "Linux cgroups v2 Step Isolation",
                "--decision",
                "Place each DAG step in an ephemeral systemd/cgroup v2 scope.",
                "--rejected",
                "Plain os/exec process groups",
                "--rationale",
                "Prevents double-forked orphan processes.",
                "--dimension",
                "bottlenecks",
            ]
        )
        state.main(
            [
                "--workspace",
                str(self.workspace),
                "add-critique",
                "--title",
                "SQLite WAL Lock Contention Under High Concurrency",
                "--severity",
                "high",
                "--attack",
                "50+ concurrent step heartbeats cause SQLITE_BUSY errors",
                "--mitigation",
                "Single writer goroutine batching state transitions every 100ms",
            ]
        )

        st = state.load_state(self.workspace)
        # Gate stays LOCKED until both Mermaid diagrams exist (spec rule #7), so status/export-tickets agree with render_blueprint.py
        self.assertFalse(st["readiness_unlocked"])
        self.assertEqual(len(st["missing_gate_requirements"]), 1)
        self.assertIn("topology_mermaid", st["missing_gate_requirements"][0])
        tools_by_name = {t["recommended"]: t for t in st["tooling_recommendations"]}
        self.assertEqual(tools_by_name["Docker (Dockerfile)"]["proof_status"], "verified")
        self.assertEqual(tools_by_name["Kubernetes Helm"]["proof_status"], "claimed-unverified")

        # render_blueprint.py should STILL fail if set-design hasn't populated Mermaid diagrams
        rc_no_diagrams = render_blueprint.main(["--workspace", str(self.workspace)])
        self.assertEqual(rc_no_diagrams, 2)

        # --force with only diagrams missing must watermark DRAFT (never "PASSED" over placeholder diagrams)
        rc_force_no_diagrams = render_blueprint.main(["--workspace", str(self.workspace), "--force"])
        self.assertEqual(rc_force_no_diagrams, 0)
        self.assertIn("[DRAFT]", (self.workspace / ".preflight" / "SPEC.md").read_text(encoding="utf-8"))
        self.assertIn("DRAFT BLUEPRINT", (self.workspace / "blueprint_report.html").read_text(encoding="utf-8"))
        forced_ticket = sorted((self.workspace / ".preflight" / "issues").glob("[0-9][0-9]-*.md"))[0]
        self.assertIn("**Status:** draft", forced_ticket.read_text(encoding="utf-8"))

        # Populate diagrams, trade-offs, and steps (including custom :: BlockedBy edge) via `set-design`
        rc_design = state.main(
            [
                "--workspace",
                str(self.workspace),
                "set-design",
                "--topology",
                "flowchart LR\n    CLI --> Daemon --> SQLite[(SQLite WAL)]",
                "--sequence",
                "sequenceDiagram\n    CLI->>Daemon: Trigger DAG\n    Daemon->>SQLite: Batch commit",
                "--option",
                "SQLite Single-Writer|Zero ops, single file|Single node only|Selected (ADR-0001)",
                "--option",
                "etcd Cluster|Multi-node HA|High operational overhead on edge|Rejected",
                "--step",
                "Implement SQLite WAL state machine and single-writer 100ms batch loop",
                "--step",
                "Implement cgroup v2 process runner :: Spawn each step in /sys/fs/cgroup/edgecron with cgroup.kill :: `01`",
            ]
        )
        self.assertEqual(rc_design, 0)
        self.assertTrue(state.load_state(self.workspace)["readiness_unlocked"])

        # Now render_blueprint.py succeeds and writes blueprint_report.html, .preflight/SPEC.md, .preflight/STACK.md, and .preflight/issues/
        rc_render_ok = render_blueprint.main(["--workspace", str(self.workspace)])
        self.assertEqual(rc_render_ok, 0)

        html_path = self.workspace / "blueprint_report.html"
        spec_path = self.workspace / ".preflight" / "SPEC.md"
        stack_path = self.workspace / ".preflight" / "STACK.md"
        issues_dir = self.workspace / ".preflight" / "issues"
        self.assertTrue(html_path.exists())
        self.assertTrue(spec_path.exists())
        self.assertTrue(stack_path.exists())
        self.assertTrue((issues_dir / "INDEX.md").exists())

        stack_text = stack_path.read_text(encoding="utf-8")
        self.assertIn("Verified (`scout:Dockerfile`)", stack_text)
        self.assertIn("Claimed / Unverified: `Chart.yaml`", stack_text)
        self.assertIn("transactional-db (primary) + lexical-fts, episodic-agent-state (secondary)", stack_text)

        ticket_files = sorted(f.name for f in issues_dir.glob("[0-9][0-9]-*.md"))
        self.assertEqual(len(ticket_files), 2)
        first_ticket = (issues_dir / ticket_files[0]).read_text(encoding="utf-8")
        second_ticket = (issues_dir / ticket_files[1]).read_text(encoding="utf-8")
        self.assertIn("**Blocked by:** None (can start immediately)", first_ticket)
        self.assertIn("**Status:** ready-for-agent", first_ticket)
        self.assertIn("SQLite WAL Lock Contention Under High Concurrency", first_ticket)
        self.assertIn("**Blocked by:** `01`", second_ticket)
        self.assertIn("Linux cgroups v2 Step Isolation", second_ticket)

        html_text = html_path.read_text(encoding="utf-8")
        spec_text = spec_path.read_text(encoding="utf-8")
        self.assertIn("dagucloud/dagu#1260", html_text)
        self.assertIn("@ghansham", html_text)
        self.assertIn("visual diagram rendering requires internet access for Mermaid CDN", html_text)
        self.assertNotIn("offline fallback", html_text)
        self.assertIn("## 6. System Architecture Diagrams", spec_text)
        self.assertIn("Linux cgroups v2 Step Isolation", spec_text)

    def test_reset_preserves_preexisting_adrs_and_supports_keep_adrs(self) -> None:
        # Create a pre-existing repository ADR that is NOT part of .preflight/decisions.json
        adr_dir = self.workspace / "docs" / "adr"
        adr_dir.mkdir(parents=True, exist_ok=True)
        preexisting_adr = adr_dir / "0001-existing-repo-architecture.md"
        preexisting_adr.write_text("# ADR-0001: Pre-existing Architecture\n", encoding="utf-8")

        state.main(["--workspace", str(self.workspace), "init", "--name", "TempIdea"])
        state.main(
            [
                "--workspace",
                str(self.workspace),
                "add-decision",
                "--title",
                "Session Specific Decision",
                "--decision",
                "Use SQLite WAL",
            ]
        )
        session_adr = adr_dir / "0002-session-specific-decision.md"
        self.assertTrue(preexisting_adr.exists())
        self.assertTrue(session_adr.exists())

        # 1. `reset --keep-adrs` preserves BOTH the pre-existing ADR and the session ADR
        state.main(["--workspace", str(self.workspace), "reset", "--keep-adrs"])
        self.assertTrue(preexisting_adr.exists())
        self.assertTrue(session_adr.exists())

        # Re-create state and a new session ADR (0003)
        state.main(["--workspace", str(self.workspace), "init", "--name", "TempIdea2"])
        state.main(
            [
                "--workspace",
                str(self.workspace),
                "add-decision",
                "--title",
                "Another Session Decision",
                "--decision",
                "Use cgroups v2",
            ]
        )
        session_adr_3 = adr_dir / "0003-another-session-decision.md"
        self.assertTrue(session_adr_3.exists())

        # 2. Default `reset` deletes ONLY 0003 (recorded in decisions.json) and MUST preserve 0001 (pre-existing)!
        state.main(["--workspace", str(self.workspace), "reset"])
        self.assertTrue(preexisting_adr.exists())
        self.assertFalse(session_adr_3.exists())

        # 3. `init --reset --keep-adrs` also respects --keep-adrs
        state.main(["--workspace", str(self.workspace), "init", "--name", "TempIdea3"])
        state.main(
            [
                "--workspace",
                str(self.workspace),
                "add-decision",
                "--title",
                "Kept On Init Reset",
                "--decision",
                "Keep me",
            ]
        )
        kept_adr = adr_dir / "0003-kept-on-init-reset.md"
        self.assertTrue(kept_adr.exists())
        state.main(
            [
                "--workspace",
                str(self.workspace),
                "init",
                "--reset",
                "--keep-adrs",
                "--name",
                "TempIdea4",
            ]
        )
        self.assertTrue(preexisting_adr.exists())
        self.assertTrue(kept_adr.exists())

    def test_force_bypass_stamps_draft_on_all_outputs_and_word_boundary_slugs(self) -> None:
        # Word-boundary slug truncation must never leave trailing fragments like '-b' or '-and-'
        long_title = "Implement power loss recovery planner skip latest only backfill serial and cron"
        slug = state.slugify(long_title, max_len=60)
        self.assertLessEqual(len(slug), 60)
        self.assertEqual(slug, "implement-power-loss-recovery-planner-skip-latest-only")

        # Initialize at 0% readiness and render with --force
        state.main(["--workspace", str(self.workspace), "init", "--name", "UnfinishedDraft"])
        rc = render_blueprint.main(["--workspace", str(self.workspace), "--force"])
        self.assertEqual(rc, 0)

        html_text = (self.workspace / "blueprint_report.html").read_text(encoding="utf-8")
        spec_text = (self.workspace / ".preflight" / "SPEC.md").read_text(encoding="utf-8")
        stack_text = (self.workspace / ".preflight" / "STACK.md").read_text(encoding="utf-8")
        index_text = (self.workspace / ".preflight" / "issues" / "INDEX.md").read_text(encoding="utf-8")
        ticket_files = sorted((self.workspace / ".preflight" / "issues").glob("[0-9][0-9]-*.md"))
        first_ticket = ticket_files[0].read_text(encoding="utf-8")

        self.assertIn("DRAFT BLUEPRINT (READINESS GATE LOCKED)", html_text)
        self.assertIn("[DRAFT] System Design Specification: UnfinishedDraft", spec_text)
        self.assertIn("DRAFT — Readiness Gate Bypassed via `--force`", spec_text)
        self.assertNotIn("(Evidence-Verified)", spec_text)
        self.assertIn("# [DRAFT] Stack Explained & Memory Architecture: UnfinishedDraft", stack_text)
        self.assertIn("# [DRAFT] Ordered Implementation Tickets: UnfinishedDraft", index_text)
        self.assertIn("`draft`", index_text)
        self.assertIn("**Status:** draft", first_ticket)
        self.assertNotIn("ready-for-agent", first_ticket)

    def test_scout_mocked_http_and_heuristics(self) -> None:
        # 1. Test normalize_repo_query and normalize_topic_query
        self.assertEqual(scout.normalize_repo_query("dagu workflow"), "dagu workflow in:name,description")
        self.assertEqual(scout.normalize_repo_query("repo:dagucloud/dagu"), "dagucloud/dagu in:name")
        self.assertEqual(scout.normalize_topic_query("Cron Scheduler"), "topic:cron-scheduler")

        # 2. Test full `scout_github` pipeline with mocked HTTP responses (zero network calls)
        py_b64 = base64.b64encode(b"[project]\nname='demo'\n[tool.uv]\n[tool.ruff]\n").decode("ascii")

        def fake_urlopen(req: object, timeout: int = 15) -> _FakeHTTPResponse:
            url = getattr(req, "full_url", str(req))
            if "/search/repositories" in url and "topic%3Acron" in url:
                return _FakeHTTPResponse(
                    {
                        "items": [
                            {
                                "full_name": "old-org/dormant-cron",
                                "html_url": "https://github.com/old-org/dormant-cron",
                                "description": "Old cron tool",
                                "stargazers_count": 120,
                                "forks_count": 15,
                                "open_issues_count": 2,
                                "has_issues": True,
                                "language": "Go",
                                "license": {"spdx_id": "MIT"},
                                "topics": ["cron"],
                                "created_at": "2020-01-01T00:00:00Z",
                                "pushed_at": "2022-01-01T00:00:00Z",
                                "archived": False,
                            }
                        ]
                    }
                )
            if "/search/repositories" in url:
                return _FakeHTTPResponse(
                    {
                        "items": [
                            {
                                "full_name": "acme/active-scheduler",
                                "html_url": "https://github.com/acme/active-scheduler",
                                "description": "Active scheduler",
                                "stargazers_count": 900,
                                "forks_count": 50,
                                "open_issues_count": 5,
                                "has_issues": True,
                                "language": "Python",
                                "license": {"spdx_id": "Apache-2.0"},
                                "topics": ["scheduler"],
                                "created_at": "2025-01-01T00:00:00Z",
                                "pushed_at": "2026-10-20T00:00:00Z",
                                "archived": False,
                            }
                        ]
                    }
                )
            if url.endswith("/repos/acme/active-scheduler/contents"):
                return _FakeHTTPResponse(
                    [
                        {"name": "pyproject.toml"},
                        {"name": "uv.lock"},
                        {"name": "Dockerfile"},
                        {"name": ".github"},
                    ]
                )
            if url.endswith("/repos/acme/active-scheduler/contents/pyproject.toml"):
                return _FakeHTTPResponse({"content": py_b64})
            if url.endswith("/repos/acme/active-scheduler/contents/.github"):
                return _FakeHTTPResponse([{"name": "workflows"}])
            if "/search/issues" in url:
                return _FakeHTTPResponse(
                    {
                        "items": [
                            {
                                "number": 42,
                                "title": "Worker leaks zombie processes on timeout",
                                "html_url": "https://github.com/acme/active-scheduler/issues/42",
                                "body": "When a job times out, child processes keep running.",
                                "labels": [{"name": "bug"}],
                                "reactions": {"+1": 7, "total_count": 7},
                                "comments": 2,
                                "created_at": "2026-09-01T00:00:00Z",
                            }
                        ]
                    }
                )
            if "/issues/42/comments" in url:
                return _FakeHTTPResponse(
                    [
                        {
                            "user": {"login": "kernel-dev"},
                            "body": "Use cgroups v2 cgroup.kill to reap double-forked children reliably.",
                            "reactions": {"+1": 4, "total_count": 4},
                        }
                    ]
                )
            return _FakeHTTPResponse({})

        cache = scout.RepoCache(self.workspace / ".preflight" / "cache.db")
        try:
            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                report = scout.scout_github(
                    queries=["active scheduler"],
                    cache=cache,
                    token="fake-token",
                    auth_source="env:GITHUB_TOKEN",
                    tool_queries=["sqlite"],
                    topics=["cron"],
                )
        finally:
            cache.close()

        self.assertIn("search_limits", report)
        self.assertEqual(len(report["active_incumbents"]), 1)
        self.assertEqual(report["active_incumbents"][0]["full_name"], "acme/active-scheduler")
        self.assertEqual(len(report["graveyard_repos"]), 1)
        self.assertIn("Dormant heuristic", report["graveyard_repos"][0]["graveyard_reason"])
        observed_tools = {c["tool"] for c in report["observed_stack_configs"]}
        self.assertIn("uv", observed_tools)
        self.assertIn("Docker (Dockerfile)", observed_tools)
        self.assertIn("GitHub Actions", observed_tools)
        self.assertEqual(len(report["pain_points"]), 1)
        self.assertEqual(report["pain_points"][0]["top_comments"][0]["author"], "kernel-dev")

    def test_repo_citation_requires_full_owner_repo_and_config_proof_rejects_mismatched_files(self) -> None:
        # Differentiation citations must match the full `owner/repo` token, not bare words like "cron"
        self.assertTrue(state.cites_repo("unlike `hanagantig/cron`, we avoid raft.", "hanagantig/cron"))
        self.assertTrue(state.cites_repo("solves dagucloud/dagu#1260", "dagucloud/dagu"))
        self.assertFalse(state.cites_repo("a cron scheduler with an acronym", "hanagantig/cron"))
        self.assertFalse(state.cites_repo("see xhanagantig/cron", "hanagantig/cron"))
        self.assertFalse(state.cites_repo("see hanagantig/cronsun", "hanagantig/cron"))

        preflight_dir = self.workspace / ".preflight"
        preflight_dir.mkdir(parents=True, exist_ok=True)
        prior_art = {
            "active_incumbents": [{"full_name": "hanagantig/cron", "detected_configs": []}],
            "graveyard_repos": [],
            "observed_stack_configs": [{"tool": "Docker (Dockerfile)", "config_file": "Dockerfile"}],
        }
        (preflight_dir / "prior-art.json").write_text(json.dumps(prior_art), encoding="utf-8")

        # A bare repo name in the summary must NOT satisfy the 20/20 differentiation citation rule
        msg = state.validate_dimension_evidence(
            self.workspace,
            "differentiation",
            20,
            "A lightweight cron scheduler that avoids distributed consensus entirely for edge nodes.",
            ["cron jobs run locally without a quorum", "no shared filesystem needed for workers"],
        )
        self.assertIsNotNone(msg)
        self.assertIn("must explicitly cite", msg or "")

        # An explicit config-proof filename that was never observed stays unverified, even if the tool name matches
        status, _ = state.verify_config_proof(self.workspace, "docker-compose.prod.yml", "Docker (Dockerfile)")
        self.assertEqual(status, "claimed-unverified")
        # A proof with no concrete filename may still be verified by tool name
        status, source = state.verify_config_proof(self.workspace, "multi-stage build", "Docker")
        self.assertEqual(status, "verified")
        self.assertEqual(source, "scout:Dockerfile")

    def test_link_skills_script(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        script = repo_root / "scripts" / "link-skills.sh"
        self.assertTrue(script.exists())

        dest1 = self.workspace / "claude_skills"
        dest2 = self.workspace / "agents_skills"

        # 1. Successful linking into custom destinations
        res = subprocess.run([str(script), str(dest1), str(dest2)], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("linked preflight ->", res.stdout)
        target1 = dest1 / "preflight"
        target2 = dest2 / "preflight"
        self.assertTrue(target1.is_symlink())
        self.assertTrue(target2.is_symlink())
        expected_src = (repo_root / "skills" / "preflight").resolve()
        self.assertEqual(target1.resolve(), expected_src)
        self.assertEqual(target2.resolve(), expected_src)

        # 2. Idempotency (running twice produces identical output)
        res_repeat = subprocess.run([str(script), str(dest1), str(dest2)], capture_output=True, text=True)
        self.assertEqual(res_repeat.returncode, 0)
        self.assertEqual(res_repeat.stdout, res.stdout)

        # 3. Existing real directory at target refuses without --force
        dest_real = self.workspace / "real_skills"
        real_target = dest_real / "preflight"
        real_target.mkdir(parents=True, exist_ok=True)
        (real_target / "existing.txt").write_text("pre-existing content", encoding="utf-8")

        res_refuse = subprocess.run([str(script), str(dest_real)], capture_output=True, text=True)
        self.assertNotEqual(res_refuse.returncode, 0)
        self.assertIn("Refusing to overwrite without --force", res_refuse.stderr)
        self.assertFalse(real_target.is_symlink())

        # 4. Existing real directory replaced with --force
        res_forced = subprocess.run([str(script), "--force", str(dest_real)], capture_output=True, text=True)
        self.assertEqual(res_forced.returncode, 0, res_forced.stderr)
        self.assertTrue(real_target.is_symlink())
        self.assertEqual(real_target.resolve(), expected_src)

        # 5. Guard: destination symlink into repo exits 1 with error
        bad_dest = self.workspace / "symlink_into_repo"
        bad_dest.symlink_to(repo_root / "skills")
        res_guard = subprocess.run([str(script), str(bad_dest)], capture_output=True, text=True)
        self.assertNotEqual(res_guard.returncode, 0)
        self.assertIn("is a symlink into this repo", res_guard.stderr)


class TestArchitectureDeepening(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name)
        self.store = state.WorkspaceStore(self.workspace)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_gate_verdict_value_object(self) -> None:
        # Immutable value object
        verdict = state.GateVerdict(score=75, unlocked=False, missing=["Need 80%"], is_draft=True)
        self.assertEqual(verdict.score, 75)
        self.assertFalse(verdict.unlocked)
        self.assertTrue(verdict.is_draft)
        self.assertEqual(verdict.missing, ["Need 80%"])
        with self.assertRaises(Exception):
            verdict.score = 80  # frozen dataclass

        # Backwards compatible tuple unpacking
        score, unlocked, missing = verdict
        self.assertEqual(score, 75)
        self.assertFalse(unlocked)
        self.assertEqual(missing, ["Need 80%"])

    def test_artifact_watermarker(self) -> None:
        # Draft watermarking
        self.assertEqual(state.ArtifactWatermarker.title("System Spec", is_draft=True), "[DRAFT] System Spec")
        draft_banner = "\n".join(state.ArtifactWatermarker.banner_markdown(is_draft=True, doc_name="Specification"))
        self.assertIn("DRAFT — READINESS GATE LOCKED", draft_banner)
        self.assertEqual(state.ArtifactWatermarker.ticket_status(is_draft=True), "draft")
        ticket_banner = "\n".join(state.ArtifactWatermarker.ticket_banner_markdown(is_draft=True))
        self.assertIn("DRAFT — DO NOT EXECUTE YET", ticket_banner)

        # Verified watermarking
        self.assertEqual(state.ArtifactWatermarker.title("System Spec", is_draft=False), "System Spec")
        self.assertEqual(state.ArtifactWatermarker.banner_markdown(is_draft=False), [])
        self.assertEqual(state.ArtifactWatermarker.ticket_status(is_draft=False), "ready-for-agent")
        self.assertEqual(state.ArtifactWatermarker.ticket_banner_markdown(is_draft=False), [])

    def test_workspace_store_paths_and_lifecycle(self) -> None:
        # Layout properties
        root = self.workspace.resolve()
        self.assertEqual(self.store.preflight_dir, root / ".preflight")
        self.assertEqual(self.store.state_path, root / ".preflight" / "state.json")
        self.assertEqual(self.store.decisions_path, root / ".preflight" / "decisions.json")
        self.assertEqual(self.store.prior_art_path, root / ".preflight" / "prior-art.json")
        self.assertEqual(self.store.cache_path, root / ".preflight" / "cache.db")
        self.assertEqual(self.store.spec_path, root / ".preflight" / "SPEC.md")
        self.assertEqual(self.store.stack_path, root / ".preflight" / "STACK.md")
        self.assertEqual(self.store.issues_dir, root / ".preflight" / "issues")
        self.assertEqual(self.store.adr_dir, root / "docs" / "adr")

        # Load empty state returns default schema without creating directory
        st = self.store.load_state()
        self.assertEqual(st["project_name"], "Untitled Project")

        # Save and atomic load state
        st["project_name"] = "DeepenedStoreTest"
        self.store.save_state(st)
        self.assertTrue(self.store.state_path.exists())
        loaded = self.store.load_state()
        self.assertEqual(loaded["project_name"], "DeepenedStoreTest")

        # Decisions lifecycle
        decs = self.store.load_decisions()
        self.assertEqual(decs, [])
        self.store.save_decisions([{"id": "ADR-0001", "file": "docs/adr/0001-test.md"}])
        self.assertEqual(len(self.store.load_decisions()), 1)

        # Safe reset removes state, decisions, and tracked ADRs, but preserves cache.db and pre-existing ADRs
        (self.workspace / "docs" / "adr").mkdir(parents=True, exist_ok=True)
        tracked_adr = self.workspace / "docs" / "adr" / "0001-test.md"
        tracked_adr.write_text("tracked adr", encoding="utf-8")
        pre_existing_adr = self.workspace / "docs" / "adr" / "0000-pre-existing.md"
        pre_existing_adr.write_text("keep me", encoding="utf-8")
        cache_file = self.store.cache_path
        cache_file.write_text("sqlite placeholder", encoding="utf-8")

        removed = self.store.reset(keep_adrs=False)
        self.assertFalse(self.store.state_path.exists())
        self.assertFalse(self.store.decisions_path.exists())
        self.assertFalse(tracked_adr.exists())
        self.assertTrue(pre_existing_adr.exists())
        self.assertTrue(cache_file.exists())
        self.assertIn("docs/adr/0001-test.md", removed)

    def test_preflight_ops_domain_operations(self) -> None:
        ops = state.PreFlightOps(self.store)

        # Init project
        st, verdict, removed = ops.init_project("DomainOpsTest", reset=False)
        self.assertEqual(st["project_name"], "DomainOpsTest")
        self.assertEqual(ops.get_scorecard().score, 0)

        # Update dimension with evidence validation
        st, verdict = ops.update_dimension(
            dimension="problem",
            score=20,
            summary="Rigorous architectural pain point explanation that is well over 20 characters.",
            edge_cases=["Edge case 1: race conditions in async queue", "Edge case 2: network timeout recovery"],
        )
        self.assertEqual(st["dimensions"]["problem"]["score"], 20)

        # Add tool to Stack Explained
        st, entry = ops.add_tool(
            category="dependency-lock",
            purpose="Deterministic package resolution",
            recommended="uv",
            why="Instant virtualenvs and cross-platform lockfiles",
            stage="now",
            alternatives="pip-tools, poetry",
            config_proof="pyproject.toml with uv.lock",
        )
        self.assertEqual(len(st["tooling_recommendations"]), 1)
        self.assertEqual(st["tooling_recommendations"][0]["recommended"], "uv")

        # Set memory architecture
        st, mem = ops.set_memory_architecture(
            strategy="transactional-db",
            communication="Synchronous internal messaging",
            workflow="Ephemeral workspace state stored in SQLite",
            rationale="ACID guarantees without distributed consensus",
            alternatives="stateless, redis",
            failure_modes=["SQLite locked on concurrent writes; mitigated with WAL mode"],
            secondary_strategies=["lexical-fts"],
        )
        self.assertEqual(st["memory_architecture"]["strategy"], "transactional-db")
        self.assertEqual(st["memory_architecture"]["secondary_strategies"], ["lexical-fts"])

        # Add red-team critique
        st, entry = ops.add_critique(
            title="Single SQLite scaling",
            severity="high",
            attack="Single SQLite instance cannot scale horizontally across pods.",
            mitigation="Edge runtime model pins one database per node by design.",
        )
        self.assertEqual(len(st["red_team_critiques"]), 1)

        # Add decision
        st, dec = ops.add_decision(
            title="Use SQLite WAL Mode",
            decision="Enable PRAGMA journal_mode=WAL on connection init",
            rejected="Rollback journal",
            rationale="Allows concurrent readers without blocking writers",
            dimension="memory",
        )
        self.assertEqual(dec["title"], "Use SQLite WAL Mode")
        self.assertTrue((self.workspace / dec["file"]).exists())

        # Set system design
        st, sys_design = ops.set_system_design(
            topology="graph TD\nA-->B",
            sequence="sequenceDiagram\nA->>B: ping",
        )
        self.assertEqual(st["system_design"]["topology_mermaid"], "graph TD\nA-->B")

    def test_scout_github_with_fake_github_client_seam(self) -> None:
        # Offline testing of scout_github via FakeGitHubClient without mocking urllib
        fake_client = scout.FakeGitHubClient()

        # Seed repository search
        fake_client.add_handler(
            lambda url: "/search/repositories" in url and "fast-queue" in url,
            {
                "items": [
                    {
                        "full_name": "acme/fast-queue",
                        "html_url": "https://github.com/acme/fast-queue",
                        "description": "High throughput async queue",
                        "stargazers_count": 1200,
                        "forks_count": 80,
                        "open_issues_count": 3,
                        "has_issues": True,
                        "language": "Python",
                        "topics": ["queue", "async"],
                        "created_at": "2025-01-01T00:00:00Z",
                        "pushed_at": "2026-10-25T00:00:00Z",
                        "archived": False,
                    }
                ]
            },
        )

        # Seed contents inspection
        fake_client.set_response(
            "https://api.github.com/repos/acme/fast-queue/contents",
            [{"name": "pyproject.toml"}, {"name": "Dockerfile"}],
        )

        pyproject_bytes = b"[tool.uv]\ndev-dependencies = ['pytest']\n"
        pyproject_b64 = base64.b64encode(pyproject_bytes).decode("ascii")
        fake_client.set_response(
            "https://api.github.com/repos/acme/fast-queue/contents/pyproject.toml",
            {"content": pyproject_b64},
        )

        # Seed issue search & comments
        fake_client.add_handler(
            lambda url: "/search/issues" in url,
            {
                "items": [
                    {
                        "number": 10,
                        "title": "Deadlock during consumer rebalance",
                        "html_url": "https://github.com/acme/fast-queue/issues/10",
                        "body": "Rebalancing workers hangs on lock acquisition.",
                        "reactions": {"+1": 8, "total_count": 8},
                        "comments": 2,
                        "created_at": "2026-09-01T00:00:00Z",
                    }
                ]
            },
        )

        fake_client.set_response(
            "https://api.github.com/repos/acme/fast-queue/issues/10/comments?per_page=15",
            [
                {
                    "user": {"login": "concurrency-expert"},
                    "body": "Use asymmetric lock timeouts to break deadlocks.",
                    "reactions": {"+1": 5, "total_count": 5},
                }
            ],
        )

        cache = scout.RepoCache(self.store.cache_path)
        try:
            report = scout.scout_github(
                queries=["fast-queue"],
                cache=cache,
                token=None,
                auth_source="unauthenticated",
                client=fake_client,
            )
        finally:
            cache.close()

        self.assertEqual(len(report["active_incumbents"]), 1)
        self.assertEqual(report["active_incumbents"][0]["full_name"], "acme/fast-queue")
        observed_tools = {sig["tool"] for sig in report["observed_stack_configs"]}
        self.assertIn("uv", observed_tools)
        self.assertIn("Docker (Dockerfile)", observed_tools)
        self.assertEqual(len(report["pain_points"]), 1)
        self.assertEqual(report["pain_points"][0]["top_comments"][0]["author"], "concurrency-expert")
        # Ensure FakeGitHubClient recorded the calls
        self.assertGreater(len(fake_client.calls), 0)

    def test_tool_config_signature_pairing_and_workspace_content_verification(self) -> None:
        # Create a workspace with a Dockerfile and a pyproject.toml
        (self.workspace / "Dockerfile").write_text("FROM alpine:latest\n", encoding="utf-8")
        (self.workspace / "pyproject.toml").write_text("[tool.uv]\ndev-dependencies = ['pytest']\n", encoding="utf-8")

        # 1. Dockerfile pairs with Docker, but NOT with an unrelated tool like Redis
        status_docker, src_docker = state.verify_config_proof(self.workspace, "Dockerfile", recommended="Docker")
        self.assertEqual(status_docker, "verified")
        self.assertEqual(src_docker, "workspace:Dockerfile")

        status_redis, _ = state.verify_config_proof(self.workspace, "Dockerfile", recommended="Redis")
        self.assertEqual(status_redis, "claimed-unverified")

        # 2. pyproject.toml content contains 'uv' token -> pairs with uv
        status_uv, src_uv = state.verify_config_proof(self.workspace, "pyproject.toml", recommended="uv")
        self.assertEqual(status_uv, "verified")
        self.assertEqual(src_uv, "workspace:pyproject.toml")

        # 3. pyproject.toml content does NOT contain 'redis' token -> fails pairing
        status_redis_toml, _ = state.verify_config_proof(self.workspace, "pyproject.toml", recommended="Redis")
        self.assertEqual(status_redis_toml, "claimed-unverified")

    def test_stateless_architecture_gate_exemption(self) -> None:
        ops = state.PreFlightOps(self.store)
        ops.init_project("StatelessCLI", reset=False)

        # 1. Short rationale raises error
        with self.assertRaises(ValueError):
            ops.set_memory_architecture(
                strategy="stateless",
                rationale="short",
            )

        # 2. Substantive rationale sets default communication and exempts failure modes
        st, mem = ops.set_memory_architecture(
            strategy="stateless",
            rationale="Single-process deterministic CLI tool with zero long-lived state or agent communication.",
        )
        self.assertEqual(mem["strategy"], "stateless")
        self.assertIn("Stateless", mem["agent_communication_pattern"])
        self.assertEqual(mem["failure_modes"], [])

        # 3. Memory dimension validation accepts stateless without failure modes
        err_stateless = state.validate_dimension_evidence(
            workspace=self.workspace,
            dimension="memory",
            score=20,
            summary="Deterministic CLI pipeline reading stdin and producing stdout with no state.",
            edge_cases=["Empty input stream", "Broken pipe on stdout"],
            state=st,
        )
        self.assertIsNone(err_stateless, f"Expected stateless memory dimension to validate, but got: {err_stateless}")

        # 4. In contrast, stateful transactional-db without failure modes is rejected
        st_stateful, mem_stateful = ops.set_memory_architecture(
            strategy="transactional-db",
            communication="Single-writer worker channel",
            rationale="SQLite database for persistent records across restarts.",
            failure_modes=["SQLITE_BUSY under concurrent writes -> mitigated by WAL mode and busy timeout"],
        )
        # Manually clear failure modes to test gate rejection
        st_stateful["memory_architecture"]["failure_modes"] = []
        err_broken = state.validate_dimension_evidence(
            workspace=self.workspace,
            dimension="memory",
            score=20,
            summary="Stateful SQLite database storing run records across process restarts.",
            edge_cases=["Crash recovery during WAL checkpoint", "Corrupted index"],
            state=st_stateful,
        )
        self.assertIsNotNone(err_broken)
        self.assertIn("requires at least 1 memory failure mode", str(err_broken))

    def test_ticket_criteria_specificity_and_no_blind_fallbacks(self) -> None:
        decisions = [
            {
                "id": "ADR-0001",
                "title": "SQLite WAL Engine",
                "decision": "Use SQLite WAL for persistent audit log storage",
            }
        ]
        critiques = [
            {
                "title": "SQLite WAL Write Lock Contention",
                "attack": "High-frequency writes block read transactions",
                "mitigation": "Single-writer channel with 100ms commit batches",
                "severity": "high",
            }
        ]
        tools = [
            {
                "recommended": "Docker",
                "category": "container-runtime",
                "config_proof": "Dockerfile",
                "purpose": "Reproducible build container",
                "why": "Consistent tests",
                "stage": "now",
            }
        ]
        mem = {
            "strategy": "transactional-db",
            "failure_modes": ["SQLITE_BUSY write contention -> mitigated by single writer channel loop"],
        }

        # Step 1: Pure CLI parsing slice - no sqlite, db, or container tokens
        step_cli = "Bootstrap CLI argument parser and config validation"
        crit_cli = state.build_ticket_acceptance_criteria(step_cli, step_cli, decisions, critiques, tools, mem)

        # Criteria must NOT blindly include ADR-0001 or Critique-0001
        self.assertFalse(any("ADR-0001" in c or "SQLite WAL Engine" in c for c in crit_cli))
        self.assertFalse(any("Write Lock Contention" in c for c in crit_cli))
        self.assertTrue(any("Bootstrap CLI argument parser" in c for c in crit_cli))

        # Step 2: Step that explicitly touches SQLite WAL engine with single writer channel
        step_db = "Implement SQLite WAL single writer channel storage engine and batch commit loop"
        crit_db = state.build_ticket_acceptance_criteria(step_db, step_db, decisions, critiques, tools, mem)

        # Criteria MUST include the matching ADR and matching Critique
        self.assertTrue(any("ADR-0001" in c for c in crit_db))
        self.assertTrue(any("Write Lock Contention" in c for c in crit_db))
        self.assertTrue(any("Verifies memory failure guard" in c for c in crit_db))

        # Test export tickets blocked-by syntax for independent slices
        target_dir = self.workspace / ".preflight" / "issues"
        fake_state = {
            "project_name": "TestSlices",
            "system_design": {
                "implementation_steps": [
                    "Ticket One :: First slice :: None",
                    "Ticket Two :: Independent second slice :: Independent",
                ]
            },
            "decisions": decisions,
            "red_team_critiques": critiques,
            "tooling_recommendations": tools,
            "memory_architecture": mem,
        }
        exported = state.export_tickets_to_dir(
            workspace=self.workspace,
            state=fake_state,
            decisions=decisions,
            issues_dir=target_dir,
            is_draft=False,
        )
        self.assertEqual(len(exported), 2)
        ticket_two_text = exported[1].read_text(encoding="utf-8")
        self.assertIn("**Blocked by:** None (Independent slice)", ticket_two_text)

    def test_scout_pagination_and_quota_separation(self) -> None:
        fake_client = scout.FakeGitHubClient()

        # Page 1 handler (with Search API headers)
        def handle_page1(url: str) -> dict[str, Any]:
            return {
                "items": [
                    {
                        "full_name": f"acme/tool-p1-{i}",
                        "html_url": f"https://github.com/acme/tool-p1-{i}",
                        "description": "Paginated tool repo",
                        "stargazers_count": 1000 - i,
                        "forks_count": 50,
                        "open_issues_count": 2,
                        "has_issues": True,
                        "language": "Go",
                        "topics": ["scheduler"],
                        "created_at": "2025-01-01T00:00:00Z",
                        "pushed_at": "2026-10-25T00:00:00Z",
                        "archived": False,
                    }
                    for i in range(5)
                ]
            }

        # Page 2 handler (with Search API headers)
        def handle_page2(url: str) -> dict[str, Any]:
            return {
                "items": [
                    {
                        "full_name": f"acme/tool-p2-{i}",
                        "html_url": f"https://github.com/acme/tool-p2-{i}",
                        "description": "Page 2 competitor",
                        "stargazers_count": 800 - i,
                        "forks_count": 30,
                        "open_issues_count": 1,
                        "has_issues": True,
                        "language": "Go",
                        "topics": ["scheduler"],
                        "created_at": "2025-02-01T00:00:00Z",
                        "pushed_at": "2026-10-25T00:00:00Z",
                        "archived": False,
                    }
                    for i in range(3)
                ]
            }

        fake_client.add_handler(
            lambda url: "/search/repositories" in url and "page=1" in url,
            handle_page1,
        )
        fake_client.add_handler(
            lambda url: "/search/repositories" in url and "page=2" in url,
            handle_page2,
        )

        # Override get_json on fake_client to inject search vs core headers dynamically
        orig_get_json = fake_client.get_json

        def get_json_with_quotas(url: str, token: str | None = None) -> tuple[Any, dict[str, str]]:
            payload, headers = orig_get_json(url, token)
            if "/search/" in url:
                return payload, {
                    "X-RateLimit-Limit": "30",
                    "X-RateLimit-Remaining": "27",
                    "X-RateLimit-Reset": "1793183060",
                }
            return payload, {
                "X-RateLimit-Limit": "5000",
                "X-RateLimit-Remaining": "4967",
                "X-RateLimit-Reset": "1793183000",
            }
        fake_client.get_json = get_json_with_quotas

        cache = scout.RepoCache(self.store.cache_path)
        try:
            report = scout.scout_github(
                queries=["paginated-query"],
                cache=cache,
                token="test-token",
                auth_source="token",
                max_repos_per_query=5,
                max_pages=2,
                client=fake_client,
            )
        finally:
            cache.close()

        # Both pages should be discovered (5 from page 1 + 3 from page 2 = 8 repos)
        self.assertEqual(len(report["active_incumbents"]), 8)
        self.assertEqual(report["search_limits"]["max_pages_per_query"], 2)

        # Quotas must be segregated: Search API vs Core API
        rl = report["rate_limit"]
        self.assertEqual(rl["search_api"]["remaining"], 27)
        self.assertEqual(rl["search_api"]["limit"], 30)
        self.assertEqual(rl["remaining"], 27)
        self.assertEqual(rl["limit"], 30)

    def test_no_unreachable_code_in_scripts_or_tests(self) -> None:
        """AST static check ensuring no unreachable statements follow return/raise/break/continue."""
        import ast

        TERMINAL_NODES = (ast.Return, ast.Raise, ast.Break, ast.Continue)
        root_dir = Path(__file__).resolve().parent.parent
        py_files = list((root_dir / "skills" / "preflight" / "scripts").glob("*.py")) + list(
            (root_dir / "tests").glob("*.py")
        )
        violations: list[str] = []

        def check_body(stmts: list[ast.stmt], filepath: Path) -> None:
            for idx, stmt in enumerate(stmts):
                if isinstance(stmt, TERMINAL_NODES) and idx + 1 < len(stmts):
                    next_stmt = stmts[idx + 1]
                    violations.append(
                        f"{filepath.name}:{next_stmt.lineno} unreachable statement ({type(next_stmt).__name__}) after {type(stmt).__name__} at line {stmt.lineno}"
                    )
                    break

        for py_file in py_files:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for node in ast.walk(tree):
                for attr in ("body", "orelse", "finalbody"):
                    block = getattr(node, attr, None)
                    if isinstance(block, list) and all(isinstance(x, ast.stmt) for x in block):
                        check_body(block, py_file)

        self.assertEqual(violations, [], f"Unreachable code detected: {violations}")


if __name__ == "__main__":
    unittest.main()
