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

    def test_state_and_readiness_gate_lifecycle(self) -> None:
        rc = state.main(
            [
                "--workspace",
                str(self.workspace),
                "init",
                "--name",
                "TestApp",
                "--summary",
                "Test summary",
                "--runtime",
                "Python 3.11",
                "--stack",
                "SQLite,Mermaid",
            ]
        )
        self.assertEqual(rc, 0)
        st = state.load_state(self.workspace)
        self.assertEqual(st["readiness_score"], 0)
        self.assertFalse(st["readiness_unlocked"])

        # Gate should block rendering when < 80%
        rc_render = render_blueprint.main(["--workspace", str(self.workspace)])
        self.assertEqual(rc_render, 2)

        # Score 4 dimensions to 20 = 80%, but 1 dimension is still 0 -> should remain locked
        for dim in ("problem", "scope", "memory", "bottlenecks"):
            state.main(
                [
                    "--workspace",
                    str(self.workspace),
                    "update-dimension",
                    "--dimension",
                    dim,
                    "--score",
                    "20",
                    "--summary",
                    f"Locked {dim}",
                    "--edge-case",
                    f"Edge case for {dim}",
                ]
            )
        st = state.load_state(self.workspace)
        self.assertEqual(st["readiness_score"], 80)
        self.assertFalse(st["readiness_unlocked"])  # differentiation is still 0

        # Score differentiation to 10 -> total 90%, no 0% dimensions -> UNLOCKED
        state.main(
            [
                "--workspace",
                str(self.workspace),
                "update-dimension",
                "--dimension",
                "differentiation",
                "--score",
                "10",
                "--summary",
                "Contrasted against incumbents",
            ]
        )
        st = state.load_state(self.workspace)
        self.assertEqual(st["readiness_score"], 90)
        self.assertTrue(st["readiness_unlocked"])

        # Record ADR and Critique
        state.main(
            [
                "--workspace",
                str(self.workspace),
                "add-decision",
                "--title",
                "Use SQLite Cache",
                "--decision",
                "Store repo cache in SQLite",
                "--rejected",
                "Redis",
                "--rationale",
                "Zero external dependencies",
                "--dimension",
                "memory",
            ]
        )
        adr_files = list((self.workspace / "docs" / "adr").glob("*.md"))
        self.assertEqual(len(adr_files), 1)

        state.main(
            [
                "--workspace",
                str(self.workspace),
                "add-critique",
                "--title",
                "GitHub Rate Limit Exhaustion",
                "--severity",
                "critical",
                "--attack",
                "60 req/hr unauthenticated limit hit during multi-query scout",
                "--mitigation",
                "Use gh auth token + 7-day SQLite cache",
            ]
        )

        # Render blueprint now succeeds
        rc_render_ok = render_blueprint.main(["--workspace", str(self.workspace)])
        self.assertEqual(rc_render_ok, 0)
        html_file = self.workspace / "blueprint_report.html"
        self.assertTrue(html_file.exists())
        content = html_file.read_text(encoding="utf-8")
        self.assertIn("TestApp", content)
        self.assertIn("90%", content)
        self.assertIn("Use SQLite Cache", content)
        self.assertIn("GitHub Rate Limit Exhaustion", content)

    def test_scout_classification_and_sqlite_cache(self) -> None:
        ref_dt = datetime(2026, 10, 27, tzinfo=timezone.utc)
        active_raw = {
            "full_name": "org/active-tool",
            "html_url": "https://github.com/org/active-tool",
            "description": "An active repo",
            "stargazers_count": 1200,
            "forks_count": 80,
            "open_issues_count": 15,
            "language": "Python",
            "topics": ["agent", "architecture"],
            "created_at": "2025-10-27T00:00:00Z",
            "pushed_at": "2026-10-15T00:00:00Z",
            "archived": False,
        }
        graveyard_raw = {
            "full_name": "org/dead-tool",
            "html_url": "https://github.com/org/dead-tool",
            "description": "An abandoned repo",
            "stargazers_count": 450,
            "forks_count": 20,
            "open_issues_count": 42,
            "language": "TypeScript",
            "topics": [],
            "created_at": "2022-01-01T00:00:00Z",
            "pushed_at": "2024-01-01T00:00:00Z",
            "archived": False,
        }

        c_active = scout.classify_repo(active_raw, ref_dt=ref_dt)
        self.assertEqual(c_active["classification"], "active_incumbent")
        self.assertEqual(c_active["inactive_days"], 12)

        c_grave = scout.classify_repo(graveyard_raw, ref_dt=ref_dt)
        self.assertEqual(c_grave["classification"], "graveyard")
        self.assertGreater(c_grave["inactive_days"], 365)

        cache = scout.RepoCache(self.workspace / ".preflight" / "cache.db")
        try:
            cache.set_cached("test_url", {"items": [1, 2, 3]})
            self.assertEqual(cache.get_cached("test_url"), {"items": [1, 2, 3]})
            cache.upsert_repo(c_active)
            cache.upsert_repo(c_grave)
            pp = scout.extract_pain_point(
                "org/active-tool",
                {
                    "number": 99,
                    "title": "Hangs on large repos",
                    "html_url": "https://github.com/org/active-tool/issues/99",
                    "reactions": {"+1": 42, "total_count": 50},
                    "comments": 18,
                    "body": "Whenever I run this on a monorepo it times out after 60s.",
                    "created_at": "2026-08-01T00:00:00Z",
                },
            )
            cache.upsert_pain_point(pp)
            self.assertEqual(pp["reactions_plus_one"], 42)
        finally:
            cache.close()


if __name__ == "__main__":
    unittest.main()
