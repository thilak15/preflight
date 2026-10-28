#!/usr/bin/env python3
"""Unit and integration tests for PreFlight helper scripts (`state.py`, `scout.py`, `render_blueprint.py`)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "skills" / "preflight" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import render_blueprint  # noqa: E402
import scout  # noqa: E402
import state  # noqa: E402


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

        # 3. Attempting to score differentiation > 0 before running scout.py (.preflight/prior-art.json missing) MUST fail
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
            "scouted_at": "2026-10-27T20:00:00+00:00",
            "auth_source": "gh-cli",
            "rate_limit": {"search_api_quota": "30 req/min", "remaining": 28, "limit": 30},
            "queries": ["dag scheduler single binary", "dagu workflow"],
            "active_incumbents": [
                {
                    "full_name": "dagu-org/dagu",
                    "html_url": "https://github.com/dagu-org/dagu",
                    "description": "Cron alternative with a Web UI and DAG runner in a single binary",
                    "stars": 6500,
                    "forks": 380,
                    "open_issues_count": 45,
                    "language": "Go",
                    "topics": ["workflow", "dag", "scheduler"],
                    "created_at": "2022-05-01T00:00:00Z",
                    "pushed_at": "2026-10-20T00:00:00Z",
                    "archived": False,
                    "inactive_days": 7,
                    "star_velocity_per_month": 120.4,
                    "classification": "active_incumbent",
                    "graveyard_reason": "",
                }
            ],
            "graveyard_repos": [
                {
                    "full_name": "old-org/dead-cron",
                    "html_url": "https://github.com/old-org/dead-cron",
                    "description": "Distributed cron over etcd",
                    "stars": 410,
                    "forks": 32,
                    "open_issues_count": 19,
                    "language": "Go",
                    "topics": [],
                    "created_at": "2019-01-01T00:00:00Z",
                    "pushed_at": "2023-01-01T00:00:00Z",
                    "archived": True,
                    "inactive_days": 1395,
                    "star_velocity_per_month": 4.3,
                    "classification": "graveyard",
                    "graveyard_reason": "Explicitly archived by maintainer",
                }
            ],
            "pain_points": [
                {
                    "repo_full_name": "dagu-org/dagu",
                    "issue_number": 412,
                    "title": "Zombie child processes survive when parent daemon receives SIGKILL",
                    "issue_url": "https://github.com/dagu-org/dagu/issues/412",
                    "category": "bug_or_failure",
                    "labels": ["bug"],
                    "reactions_plus_one": 14,
                    "reactions_total": 16,
                    "comments_count": 6,
                    "body_excerpt": "When the worker crashes, spawned bash subshells continue running in the background.",
                    "top_comments": [
                        {
                            "author": "ops-lead",
                            "reactions": 8,
                            "excerpt": "We had to wrap every step in Linux cgroups v2 or set PR_SET_PDEATHSIG so orphans get reaped.",
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

        # Differentiation score=20 citing `dagu-org/dagu` and `old-org/dead-cron` succeeds
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
                "Unlike dagu-org/dagu (#412 orphan process leak), EdgeCron isolates every step in a cgroup v2 scope and avoids the etcd dependency that killed old-org/dead-cron.",
                "--edge-case",
                "Orphaned subprocess cleanup on SIGKILL via cgroup.kill (solves dagu-org/dagu#412)",
                "--edge-case",
                "Zero external coordination store required unlike old-org/dead-cron",
            ]
        )
        self.assertEqual(rc_cited, 0)

        # Even at 100% dimension score, gate is STILL locked until >=1 ADR and >=1 Critique exist
        st = state.load_state(self.workspace)
        self.assertEqual(st["readiness_score"], 100)
        self.assertFalse(st["readiness_unlocked"])

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
                "Prevents double-forked orphan processes (dagu-org/dagu#412).",
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

        # render_blueprint.py should STILL fail if set-design hasn't populated Mermaid diagrams
        rc_no_diagrams = render_blueprint.main(["--workspace", str(self.workspace)])
        self.assertEqual(rc_no_diagrams, 2)

        # Populate diagrams, trade-offs, and steps via `set-design`
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
                "Implement SQLite WAL state machine and single-writer batch loop",
                "--step",
                "Implement cgroup v2 process runner with orphan reaping",
            ]
        )
        self.assertEqual(rc_design, 0)

        # Now render_blueprint.py succeeds and writes both blueprint_report.html and .preflight/SPEC.md
        rc_render_ok = render_blueprint.main(["--workspace", str(self.workspace)])
        self.assertEqual(rc_render_ok, 0)

        html_path = self.workspace / "blueprint_report.html"
        spec_path = self.workspace / ".preflight" / "SPEC.md"
        self.assertTrue(html_path.exists())
        self.assertTrue(spec_path.exists())

        html_text = html_path.read_text(encoding="utf-8")
        spec_text = spec_path.read_text(encoding="utf-8")
        self.assertIn("dagu-org/dagu#412", html_text)
        self.assertIn("@ops-lead", html_text)
        self.assertIn("Copy Spec Markdown", html_text)
        self.assertIn("## 5. System Architecture Diagrams", spec_text)
        self.assertIn("Linux cgroups v2 Step Isolation", spec_text)

    def test_scout_heuristics_preserve_markdown_skills_and_filter_zero_vote_issues(self) -> None:
        # Markdown-only skill repo (language=None, small size, but has stars and description) MUST NOT be filtered out
        md_skill_repo = {
            "full_name": "author/agent-skill-pack",
            "description": "A collection of markdown agent skills",
            "stargazers_count": 25,
            "forks_count": 4,
            "has_issues": True,
            "language": None,
            "size": 4,
        }
        self.assertFalse(scout.is_noise_repo(md_skill_repo))

        # Org profile repo (.github) or 0-star/0-fork empty repo MUST be filtered out
        self.assertTrue(
            scout.is_noise_repo(
                {"full_name": "some-org/.github", "stargazers_count": 500, "forks_count": 10}
            )
        )
        self.assertTrue(
            scout.is_noise_repo(
                {"full_name": "user/empty-repo", "stargazers_count": 0, "forks_count": 0}
            )
        )

        # 0-vote, 0-comment issue MUST NOT qualify as a substantive pain point
        zero_vote_issue = {
            "number": 10,
            "title": "Random unvalidated suggestion",
            "reactions": {"+1": 0, "total_count": 0},
            "comments": 0,
        }
        self.assertFalse(scout.is_substantive_pain_point(zero_vote_issue))

        # Issue with reactions or comments DOES qualify
        valid_issue = {
            "number": 11,
            "title": "Crash when config path has spaces",
            "reactions": {"+1": 3, "total_count": 3},
            "comments": 1,
        }
        self.assertTrue(scout.is_substantive_pain_point(valid_issue))

        # Top comment extraction sorts by reaction score and strips ultra-short "+1" noise comments
        comments = [
            {"user": {"login": "spammer"}, "body": "+1", "reactions": {"+1": 10, "total_count": 10}},
            {
                "user": {"login": "dev1"},
                "body": "This happens because path quoting is missing in the subshell exec call.",
                "reactions": {"+1": 5, "total_count": 6},
            },
            {
                "user": {"login": "dev2"},
                "body": "Confirmed on macOS 15 as well; workaround is using a symlink without spaces.",
                "reactions": {"+1": 2, "total_count": 2},
            },
        ]
        top = scout.extract_top_comments(comments, max_comments=2)
        self.assertEqual(len(top), 2)
        self.assertEqual(top[0]["author"], "dev1")
        self.assertEqual(top[1]["author"], "dev2")


if __name__ == "__main__":
    unittest.main()
