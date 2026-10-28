#!/usr/bin/env python3
"""Unit and integration tests for PreFlight helper scripts (`state.py`, `scout.py`, `render_blueprint.py`)."""

from __future__ import annotations

import base64
import io
import json
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
        self.assertTrue(st["readiness_unlocked"])
        tools_by_name = {t["recommended"]: t for t in st["tooling_recommendations"]}
        self.assertEqual(tools_by_name["Docker (Dockerfile)"]["proof_status"], "verified")
        self.assertEqual(tools_by_name["Kubernetes Helm"]["proof_status"], "claimed-unverified")

        # render_blueprint.py should STILL fail if set-design hasn't populated Mermaid diagrams
        rc_no_diagrams = render_blueprint.main(["--workspace", str(self.workspace)])
        self.assertEqual(rc_no_diagrams, 2)

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


if __name__ == "__main__":
    unittest.main()
