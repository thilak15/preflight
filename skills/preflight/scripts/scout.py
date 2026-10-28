#!/usr/bin/env python3
"""
PreFlight GitHub Deep-Scout & Pain-Point Miner (`scripts/scout.py`).

Responsibilities:
1. Authenticate via `gh auth token` -> `GITHUB_TOKEN` -> unauthenticated fallback.
2. Cache all GitHub API repository & issue search responses in `.preflight/cache.db` (SQLite3, 7-day TTL).
3. Classify discovered repositories into:
   - Active Incumbents (pushed within last 365 days and not archived)
   - Graveyard Repos (inactive > 365 days or archived)
4. Mine Pain Points: fetch top-voted open issues (sorted by +1 reactions/interactions) from top incumbents.
5. Write structured output to `.preflight/prior-art.json` and print a compact Markdown digest for the agent.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CACHE_TTL_SECONDS = 7 * 24 * 3600
GRAVEYARD_DAYS_THRESHOLD = 365


def now_ts() -> int:
    return int(time.time())


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_github_ts(iso_str: str | None) -> datetime | None:
    if not iso_str:
        return None
    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except ValueError:
        return None


def days_since(iso_str: str | None, ref: datetime | None = None) -> int:
    dt = parse_github_ts(iso_str)
    if not dt:
        return 0
    ref_dt = ref or datetime.now(timezone.utc)
    return max(0, int((ref_dt - dt).total_seconds() // 86400))


def resolve_github_token() -> tuple[str | None, str]:
    """Return (token, auth_source) following `gh auth token` -> `GITHUB_TOKEN` -> unauthenticated."""
    try:
        proc = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        token = proc.stdout.strip()
        if proc.returncode == 0 and token:
            return token, "gh-cli"
    except (FileNotFoundError, subprocess.SubprocessError):
        pass

    env_token = os.environ.get("GITHUB_TOKEN", "").strip()
    if env_token:
        return env_token, "env:GITHUB_TOKEN"

    return None, "unauthenticated"


class RepoCache:
    """Tier 3 SQLite3 cache for GitHub repositories, queries, and mined issues."""

    def __init__(self, db_path: Path, ttl_seconds: int = CACHE_TTL_SECONDS) -> None:
        self.db_path = db_path
        self.ttl_seconds = ttl_seconds
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self._init_schema()

    def _init_schema(self) -> None:
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_cache (
                    cache_key TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    fetched_at INTEGER NOT NULL
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS repositories (
                    full_name TEXT PRIMARY KEY,
                    html_url TEXT NOT NULL,
                    description TEXT,
                    stars INTEGER NOT NULL,
                    forks INTEGER NOT NULL,
                    open_issues_count INTEGER NOT NULL,
                    language TEXT,
                    topics_json TEXT,
                    created_at TEXT,
                    pushed_at TEXT,
                    archived INTEGER NOT NULL,
                    classification TEXT NOT NULL,
                    inactive_days INTEGER NOT NULL,
                    star_velocity_per_month REAL NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pain_points (
                    issue_url TEXT PRIMARY KEY,
                    repo_full_name TEXT NOT NULL,
                    issue_number INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    reactions_plus_one INTEGER NOT NULL,
                    reactions_total INTEGER NOT NULL,
                    comments_count INTEGER NOT NULL,
                    body_excerpt TEXT,
                    created_at TEXT,
                    updated_at INTEGER NOT NULL
                )
                """
            )

    def get_cached(self, key: str) -> Any | None:
        cur = self.conn.execute(
            "SELECT payload_json, fetched_at FROM api_cache WHERE cache_key = ?",
            (key,),
        )
        row = cur.fetchone()
        if not row:
            return None
        payload_json, fetched_at = row
        if now_ts() - int(fetched_at) > self.ttl_seconds:
            return None
        return json.loads(payload_json)

    def set_cached(self, key: str, payload: Any) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO api_cache (cache_key, payload_json, fetched_at)
                VALUES (?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    fetched_at = excluded.fetched_at
                """,
                (key, json.dumps(payload), now_ts()),
            )

    def upsert_repo(self, repo: dict[str, Any]) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO repositories (
                    full_name, html_url, description, stars, forks,
                    open_issues_count, language, topics_json, created_at,
                    pushed_at, archived, classification, inactive_days,
                    star_velocity_per_month, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(full_name) DO UPDATE SET
                    stars = excluded.stars,
                    forks = excluded.forks,
                    open_issues_count = excluded.open_issues_count,
                    pushed_at = excluded.pushed_at,
                    archived = excluded.archived,
                    classification = excluded.classification,
                    inactive_days = excluded.inactive_days,
                    star_velocity_per_month = excluded.star_velocity_per_month,
                    updated_at = excluded.updated_at
                """,
                (
                    repo["full_name"],
                    repo["html_url"],
                    repo.get("description") or "",
                    repo["stars"],
                    repo["forks"],
                    repo["open_issues_count"],
                    repo.get("language") or "",
                    json.dumps(repo.get("topics", [])),
                    repo.get("created_at") or "",
                    repo.get("pushed_at") or "",
                    1 if repo.get("archived") else 0,
                    repo["classification"],
                    repo["inactive_days"],
                    repo["star_velocity_per_month"],
                    now_ts(),
                ),
            )

    def upsert_pain_point(self, item: dict[str, Any]) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO pain_points (
                    issue_url, repo_full_name, issue_number, title,
                    reactions_plus_one, reactions_total, comments_count,
                    body_excerpt, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(issue_url) DO UPDATE SET
                    reactions_plus_one = excluded.reactions_plus_one,
                    reactions_total = excluded.reactions_total,
                    comments_count = excluded.comments_count,
                    body_excerpt = excluded.body_excerpt,
                    updated_at = excluded.updated_at
                """,
                (
                    item["issue_url"],
                    item["repo_full_name"],
                    item["issue_number"],
                    item["title"],
                    item["reactions_plus_one"],
                    item["reactions_total"],
                    item["comments_count"],
                    item.get("body_excerpt") or "",
                    item.get("created_at") or "",
                    now_ts(),
                ),
            )

    def close(self) -> None:
        self.conn.close()


def normalize_repo_query(q: str) -> str:
    """Scope free-text queries to name,description,readme so README keyword-stuffing spam is excluded."""
    if "in:" not in q and "topic:" not in q and "repo:" not in q:
        return f"{q} in:name,description"
    return q


def is_noise_repo(raw: dict[str, Any]) -> bool:
    """Filter out known GitHub search keyword-stuffed spam or empty non-code repos."""
    full_name = (raw.get("full_name") or "").lower()
    desc = (raw.get("description") or "").lower()
    if "dictatorship" in full_name or "dictatroship" in full_name or "dictattorshrip" in full_name:
        return True
    if full_name.endswith("/.github"):
        return True
    if not raw.get("language") and int(raw.get("size", 0)) < 10:
        return True
    if desc and len(desc.encode("utf-8")) > 400 and raw.get("language") is None:
        return True
    return False


def classify_repo(raw: dict[str, Any], ref_dt: datetime | None = None) -> dict[str, Any]:
    pushed_at = raw.get("pushed_at") or raw.get("updated_at")
    created_at = raw.get("created_at")
    inactive_days = days_since(pushed_at, ref_dt)
    age_days = max(30, days_since(created_at, ref_dt))
    archived = bool(raw.get("archived", False))
    stars = int(raw.get("stargazers_count", 0))
    velocity = round(stars / max(1.0, age_days / 30.0), 2)

    is_graveyard = archived or inactive_days > GRAVEYARD_DAYS_THRESHOLD
    classification = "graveyard" if is_graveyard else "active_incumbent"

    graveyard_reason = ""
    if archived:
        graveyard_reason = "Repository explicitly archived by maintainer"
    elif is_graveyard:
        graveyard_reason = f"No commits pushed in {inactive_days} days (>365d threshold)"

    return {
        "full_name": raw["full_name"],
        "html_url": raw["html_url"],
        "description": (raw.get("description") or "").strip(),
        "stars": stars,
        "forks": int(raw.get("forks_count", 0)),
        "open_issues_count": int(raw.get("open_issues_count", 0)),
        "language": raw.get("language") or "Unknown",
        "topics": raw.get("topics") or [],
        "created_at": created_at or "",
        "pushed_at": pushed_at or "",
        "archived": archived,
        "inactive_days": inactive_days,
        "star_velocity_per_month": velocity,
        "classification": classification,
        "graveyard_reason": graveyard_reason,
    }


def extract_pain_point(repo_full_name: str, raw_issue: dict[str, Any]) -> dict[str, Any]:
    reactions = raw_issue.get("reactions") or {}
    plus_one = int(reactions.get("+1", 0))
    total_reactions = int(reactions.get("total_count", plus_one))
    body = (raw_issue.get("body") or "").strip()
    clean_excerpt = " ".join(body.split())[:280]
    if len(body) > 280:
        clean_excerpt += "..."
    return {
        "repo_full_name": repo_full_name,
        "issue_number": int(raw_issue.get("number", 0)),
        "title": (raw_issue.get("title") or "").strip(),
        "issue_url": raw_issue.get("html_url") or "",
        "reactions_plus_one": plus_one,
        "reactions_total": total_reactions,
        "comments_count": int(raw_issue.get("comments", 0)),
        "body_excerpt": clean_excerpt,
        "created_at": raw_issue.get("created_at") or "",
    }


def github_get_json(url: str, token: str | None, cache: RepoCache) -> Any:
    cached = cache.get_cached(url)
    if cached is not None:
        return cached

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "PreFlight-PriorArt-Scout/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    cache.set_cached(url, data)
    return data


def scout_github(
    queries: list[str],
    cache: RepoCache,
    token: str | None,
    auth_source: str,
    max_repos_per_query: int = 8,
    max_incumbents_for_issues: int = 4,
    issues_per_repo: int = 5,
) -> dict[str, Any]:
    if auth_source == "unauthenticated":
        max_repos_per_query = min(max_repos_per_query, 5)
        max_incumbents_for_issues = min(max_incumbents_for_issues, 2)
        issues_per_repo = min(issues_per_repo, 3)

    discovered: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    for q in queries:
        scoped_q = normalize_repo_query(q)
        encoded_q = urllib.parse.quote(scoped_q)
        url = f"https://api.github.com/search/repositories?q={encoded_q}&sort=stars&order=desc&per_page={max_repos_per_query}"
        try:
            payload = github_get_json(url, token, cache)
            for item in payload.get("items", []):
                if item.get("fork") or is_noise_repo(item):
                    continue
                classified = classify_repo(item)
                classified["matched_query"] = q
                full_name = classified["full_name"]
                if full_name not in discovered:
                    discovered[full_name] = classified
                    cache.upsert_repo(classified)
        except urllib.error.HTTPError as e:
            errors.append(f"Search query '{q}' failed: HTTP {e.code} ({e.reason})")
        except Exception as e:
            errors.append(f"Search query '{q}' failed: {e}")

    all_repos = sorted(discovered.values(), key=lambda r: r["stars"], reverse=True)
    incumbents = [r for r in all_repos if r["classification"] == "active_incumbent"]
    graveyard = [r for r in all_repos if r["classification"] == "graveyard"]

    pain_points: list[dict[str, Any]] = []
    for repo in incumbents[:max_incumbents_for_issues]:
        full_name = repo["full_name"]
        issue_q = urllib.parse.quote(f"repo:{full_name} is:issue is:open sort:reactions-+1-desc")
        issue_url = f"https://api.github.com/search/issues?q={issue_q}&per_page={issues_per_repo}"
        try:
            issue_payload = github_get_json(issue_url, token, cache)
            for raw_issue in issue_payload.get("items", []):
                if "pull_request" in raw_issue:
                    continue
                pp = extract_pain_point(full_name, raw_issue)
                pain_points.append(pp)
                cache.upsert_pain_point(pp)
        except urllib.error.HTTPError as e:
            errors.append(f"Pain-point mining for '{full_name}' failed: HTTP {e.code}")
        except Exception as e:
            errors.append(f"Pain-point mining for '{full_name}' failed: {e}")

    pain_points.sort(
        key=lambda p: (p["reactions_plus_one"], p["reactions_total"], p["comments_count"]),
        reverse=True,
    )

    return {
        "scouted_at": now_iso(),
        "auth_source": auth_source,
        "queries": queries,
        "active_incumbents": incumbents,
        "graveyard_repos": graveyard,
        "pain_points": pain_points,
        "warnings": errors,
    }


def format_markdown_digest(report: dict[str, Any]) -> str:
    incumbents = report.get("active_incumbents", [])
    graveyard = report.get("graveyard_repos", [])
    pain_points = report.get("pain_points", [])
    warnings = report.get("warnings", [])

    lines = [
        "# Prior-Art Scout Digest",
        f"- **Auth Mode:** `{report.get('auth_source', 'unknown')}`",
        f"- **Queries Executed:** {', '.join(f'`{q}`' for q in report.get('queries', []))}",
        f"- **Discovered:** {len(incumbents)} Active Incumbents | {len(graveyard)} Graveyard Repos | {len(pain_points)} Mined Pain Points",
        "",
    ]

    if warnings:
        lines.append("## Warnings")
        for w in warnings:
            lines.append(f"- ⚠️ {w}")
        lines.append("")

    lines.append("## Active Incumbents (Top Maintained Alternatives)")
    if not incumbents:
        lines.append("_No active incumbents found._")
    else:
        lines.append("| Repo | Stars | Star Velocity | Last Push | Summary |")
        lines.append("| :--- | :---: | :---: | :---: | :--- |")
        for r in incumbents[:8]:
            desc = (r.get("description") or "—").replace("|", "\\|")[:100]
            lines.append(
                f"| [{r['full_name']}]({r['html_url']}) | ⭐ {r['stars']} | {r['star_velocity_per_month']}/mo | {r['inactive_days']}d ago | {desc} |"
            )
    lines.append("")

    lines.append("## Graveyard Check (Abandoned / Stalled Attempts >365d)")
    if not graveyard:
        lines.append("_No graveyard repos flagged for these queries._")
    else:
        lines.append("| Repo | Stars | Inactive | Graveyard Signal | Summary |")
        lines.append("| :--- | :---: | :---: | :--- | :--- |")
        for r in graveyard[:6]:
            desc = (r.get("description") or "—").replace("|", "\\|")[:90]
            lines.append(
                f"| [{r['full_name']}]({r['html_url']}) | ⭐ {r['stars']} | {r['inactive_days']}d | {r['graveyard_reason']} | {desc} |"
            )
    lines.append("")

    lines.append("## Pain-Point Mining (Top-Voted Open Issues Across Incumbents)")
    if not pain_points:
        lines.append("_No open issues mined._")
    else:
        for p in pain_points[:10]:
            lines.append(
                f"- **[{p['repo_full_name']}#{p['issue_number']}]({p['issue_url']})**: {p['title']} "
                f"(👍 {p['reactions_plus_one']} | 💬 {p['comments_count']})"
            )
            if p.get("body_excerpt"):
                lines.append(f"  > {p['body_excerpt']}")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PreFlight GitHub Prior-Art Scout")
    parser.add_argument("--workspace", default=".", help="Target workspace directory")
    parser.add_argument(
        "--query",
        "-q",
        action="append",
        required=True,
        help="GitHub repository search query (can be passed multiple times)",
    )
    parser.add_argument("--max-repos", type=int, default=8, help="Max repos per query")
    parser.add_argument("--json", action="store_true", help="Print JSON output instead of Markdown digest")

    args = parser.parse_args(argv)
    workspace = Path(args.workspace).resolve()
    preflight_dir = workspace / ".preflight"
    preflight_dir.mkdir(parents=True, exist_ok=True)

    token, auth_source = resolve_github_token()
    cache = RepoCache(preflight_dir / "cache.db")
    try:
        report = scout_github(
            queries=args.query,
            cache=cache,
            token=token,
            auth_source=auth_source,
            max_repos_per_query=args.max_repos,
        )
    finally:
        cache.close()

    prior_art_path = preflight_dir / "prior-art.json"
    prior_art_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(format_markdown_digest(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
