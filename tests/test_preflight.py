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
        issues_dir = self.workspace / ".preflight" / "issues"
        self.assertTrue(html_path.exists())
        self.assertTrue(spec_path.exists())
        self.assertTrue((issues_dir / "INDEX.md").exists())
        ticket_files = sorted(f.name for f in issues_dir.glob("[0-9][0-9]-*.md"))
        self.assertEqual(len(ticket_files), 2)
        first_ticket = (issues_dir / ticket_files[0]).read_text(encoding="utf-8")
        second_ticket = (issues_dir / ticket_files[1]).read_text(encoding="utf-8")
        self.assertIn("**Blocked by:** None (can start immediately)", first_ticket)
        self.assertIn("ADR-0001", first_ticket)
        self.assertIn(f"**Blocked by:** `01` ({ticket_files[0]})", second_ticket)

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

    def test_tooling_maintenance_memory_advisor_and_fresh_reset(self) -> None:
        # 0. Test scout.py config-file stack detection (pyproject.toml for Poetry/uv, Dockerfile, .github/workflows, .pre-commit-config.yaml)
        signals = scout.parse_stack_signals_from_files(
            root_entries=[
                "pyproject.toml",
                "uv.lock",
                "Dockerfile",
                "docker-compose.yml",
                ".github",
                ".pre-commit-config.yaml",
            ],
            pyproject_text="[project]\nname = 'demo'\n[tool.uv]\ndev-dependencies = []\n[tool.ruff]\nline-length = 100\n",
            has_github_workflows=True,
        )
        signal_tools = {s["tool"]: s["config_file"] for s in signals}
        self.assertEqual(signal_tools.get("uv"), "pyproject.toml ([tool.uv]) + uv.lock")
        self.assertEqual(signal_tools.get("Ruff"), "pyproject.toml ([tool.ruff])")
        self.assertEqual(signal_tools.get("Docker (Dockerfile)"), "Dockerfile")
        self.assertEqual(signal_tools.get("GitHub Actions"), ".github/workflows")
        self.assertEqual(signal_tools.get("pre-commit (.pre-commit-config.yaml)"), ".pre-commit-config.yaml")
        # Ensure uv.lock is not duplicated as a separate entry when [tool.uv] was already detected
        self.assertNotIn("uv (uv.lock)", signal_tools)

        state.main(
            [
                "--workspace",
                str(self.workspace),
                "init",
                "--name",
                "AgentDocRouter",
                "--summary",
                "Multi-agent incident responder over runbooks",
                "--runtime",
                "Python 3.12",
                "--stack",
                "Python,SQLite FTS5,Docker",
            ]
        )

        # 1. Record "Stack Explained" entries (what job it does, why needed now, alternative, now vs later, config proof)
        rc_lock = state.main(
            [
                "--workspace",
                str(self.workspace),
                "add-tool",
                "--category",
                "dependency-lock",
                "--purpose",
                "Deterministic Python dependency locking and virtualenv reproducibility",
                "--recommended",
                "uv (uv.lock)",
                "--stage",
                "now",
                "--config-proof",
                "pyproject.toml ([tool.uv]) + uv.lock",
                "--why",
                "10-50x faster lockfile resolution than pip/Poetry with exact cross-platform hashes",
                "--alternatives",
                "Poetry (poetry.lock) if publishing complex multi-package workspaces; pip-tools (requirements.txt)",
            ]
        )
        self.assertEqual(rc_lock, 0)

        rc_container = state.main(
            [
                "--workspace",
                str(self.workspace),
                "add-tool",
                "--category",
                "container-runtime",
                "--purpose",
                "Reproducible production packaging and local dev parity",
                "--recommended",
                "Docker (multi-stage distroless/slim build)",
                "--stage",
                "now",
                "--config-proof",
                "Dockerfile",
                "--why",
                "Isolates Python runtime and native SQLite extensions into a 45MB read-only rootfs image",
                "--alternatives",
                "Nix flakes (steeper learning curve); bare virtualenv on host (drift risk)",
            ]
        )
        self.assertEqual(rc_container, 0)

        rc_orch = state.main(
            [
                "--workspace",
                str(self.workspace),
                "add-tool",
                "--category",
                "orchestration-deploy",
                "--purpose",
                "Multi-node horizontal container orchestration",
                "--recommended",
                "Kubernetes (k3s / Helm)",
                "--stage",
                "later",
                "--config-proof",
                "Chart.yaml / k8s/",
                "--why",
                "Defer until >100 RPS or multi-node HA is required; V1 uses single-node SQLite WAL over Docker Compose",
                "--alternatives",
                "Docker Compose (used NOW for Day-1 single-node deployment); Fly.io Machines",
            ]
        )
        self.assertEqual(rc_orch, 0)

        # 2. Configure Memory & Agent Communication Architecture (set-memory-arch)
        rc_mem = state.main(
            [
                "--workspace",
                str(self.workspace),
                "set-memory-arch",
                "--strategy",
                "hybrid-search",
                "--communication",
                "Typed JSON handoff envelopes between Triage Agent and Runbook Executor (no raw chat history forwarding)",
                "--workflow",
                "Triage Agent writes structured incident state to SQLite WAL; Runbook Executor queries SQLite FTS5 + local embeddings",
                "--rationale",
                "Pure Vector DB misses exact error codes (e.g. ERR_TLS_CERT_ALTNAME_INVALID); hybrid FTS5 + embeddings catches both exact symbols and semantic runbooks",
                "--alternatives",
                "Pure Vector DB (Pinecone/Chroma — poor exact error-code recall); Full context window stuffing (causes context rot after 5 turns)",
                "--failure-mode",
                "Context window bloat across multi-agent turns -> Mitigated by strict 2KB JSON handoff schema",
                "--failure-mode",
                "Stale runbook embeddings after markdown edits -> Mitigated by content-SHA256 invalidation hook on git pull",
            ]
        )
        self.assertEqual(rc_mem, 0)

        # Verify .preflight/STACK.md was automatically created and populated
        stack_md_path = self.workspace / ".preflight" / "STACK.md"
        self.assertTrue(stack_md_path.exists())
        stack_md = stack_md_path.read_text(encoding="utf-8")
        self.assertIn("uv (uv.lock)", stack_md)
        self.assertIn("poetry.lock", stack_md)
        self.assertIn("Docker", stack_md)
        self.assertIn("Kubernetes", stack_md)
        self.assertIn("hybrid-search", stack_md)
        self.assertIn("Context window bloat", stack_md)

        # 3. Score a dimension and add an ADR so state is populated
        state.main(
            [
                "--workspace",
                str(self.workspace),
                "update-dimension",
                "--dimension",
                "memory",
                "--score",
                "20",
                "--summary",
                "Hybrid SQLite FTS5 + local vector search with typed JSON agent handoffs.",
                "--edge-case",
                "Context bloat prevented by 2KB JSON handoff schema",
                "--edge-case",
                "Stale embeddings invalidated via file SHA256 check",
            ]
        )
        state.main(
            [
                "--workspace",
                str(self.workspace),
                "add-decision",
                "--title",
                "Use Hybrid FTS5 over Pure Vector DB",
                "--decision",
                "Use SQLite FTS5 + embeddings instead of standalone Vector DB",
                "--dimension",
                "memory",
            ]
        )
        self.assertTrue((self.workspace / "docs" / "adr").exists())
        self.assertEqual(len(list((self.workspace / "docs" / "adr").glob("*.md"))), 1)

        # 4. Now test `state.py reset` to wipe all pre-performed scores, ADRs, and state for a fresh run
        rc_reset = state.main(["--workspace", str(self.workspace), "reset"])
        self.assertEqual(rc_reset, 0)
        self.assertFalse((self.workspace / ".preflight" / "state.json").exists())
        self.assertFalse((self.workspace / ".preflight" / "decisions.json").exists())
        self.assertFalse((self.workspace / ".preflight" / "STACK.md").exists())
        self.assertEqual(len(list((self.workspace / "docs" / "adr").glob("*.md"))), 0)

        # 5. Re-initialize a brand new idea in the same folder and verify all scores start at 0
        state.main(
            [
                "--workspace",
                str(self.workspace),
                "init",
                "--reset",
                "--name",
                "FreshIdeaTwo",
                "--summary",
                "Brand new idea in the same directory",
            ]
        )
        fresh_state = state.load_state(self.workspace)
        self.assertEqual(fresh_state["project_name"], "FreshIdeaTwo")
        self.assertEqual(fresh_state["readiness_score"], 0)
        self.assertEqual(fresh_state["dimensions"]["memory"]["score"], 0)
        self.assertEqual(len(fresh_state["tooling_recommendations"]), 0)


if __name__ == "__main__":
    unittest.main()
