#!/usr/bin/env python3
"""
PreFlight GitHub Deep-Scout, Config-File Stack Inspector & Pain-Point Miner (`scripts/scout.py`).

Responsibilities:
1. Authenticate via `gh auth token` -> `GITHUB_TOKEN` -> unauthenticated fallback.
2. Inspect GitHub API rate-limit headers (`X-RateLimit-Remaining`, `X-RateLimit-Reset`, `Retry-After`)
   for the Search API (30 req/min authenticated, 10 req/min unauthenticated).
3. Cache all GitHub API repository, contents, issue, and comment responses in `.preflight/cache.db` (SQLite3, 7-day TTL).
4. Classify discovered competitor repositories (`-q`) into:
   - Active Incumbents (pushed within last 365 days and not archived)
   - Graveyard / Dormant Repos (archived by maintainer, or no pushes in >365 days)
5. Inspect repository config files ("Stack Explained" evidence) across top incumbents:
   - Checks root directory contents (and `pyproject.toml` when present) for empirical proof of tools used:
     `pyproject.toml` (`[tool.poetry]`, `[tool.uv]`, `[tool.ruff]`), `uv.lock`, `poetry.lock`,
     `Dockerfile`, `docker-compose.yml`, `.github/workflows`, `.pre-commit-config.yaml`, `Cargo.lock`,
     `go.sum`, `pnpm-lock.yaml`, `Chart.yaml` / `k8s/`, `Makefile`, etc.
6. Scout Open-Source Building Blocks & Tooling (`--tool-query` / `-t`) to build the project.
7. Mine Pain Points with real engagement thresholds (`reactions_plus_one >= 1` or `comments_count >= 2`)
   and fetch top-voted comments (`top_comments`).
8. Write structured output to `.preflight/prior-art.json` and print a compact Markdown digest.
"""

from __future__ import annotations

import argparse
import base64
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

# Minimum engagement required for an open issue to qualify as a "Mined Pain Point"
MIN_ISSUE_PLUS_ONE = 1
MIN_ISSUE_COMMENTS = 2

# Config file signatures used to prove which maintenance/infra tools a scouted repo actually uses
CONFIG_SIGNATURES: list[tuple[str, str, str]] = [
    ("uv.lock", "uv (uv.lock)", "dependency-lock"),
    ("poetry.lock", "Poetry (poetry.lock)", "dependency-lock"),
    ("pdm.lock", "PDM (pdm.lock)", "dependency-lock"),
    ("Pipfile.lock", "Pipenv (Pipfile.lock)", "dependency-lock"),
    ("requirements.txt", "pip (requirements.txt)", "dependency-lock"),
    ("pnpm-lock.yaml", "pnpm (pnpm-lock.yaml)", "dependency-lock"),
    ("bun.lockb", "Bun (bun.lockb)", "dependency-lock"),
    ("bun.lock", "Bun (bun.lock)", "dependency-lock"),
    ("yarn.lock", "Yarn (yarn.lock)", "dependency-lock"),
    ("package-lock.json", "npm (package-lock.json)", "dependency-lock"),
    ("Cargo.lock", "Cargo (Cargo.lock)", "dependency-lock"),
    ("go.sum", "Go Modules (go.sum)", "dependency-lock"),
    ("Dockerfile", "Docker (Dockerfile)", "container-runtime"),
    ("Containerfile", "Podman/OCI (Containerfile)", "container-runtime"),
    (".devcontainer", "Dev Containers (.devcontainer)", "container-runtime"),
    ("docker-compose.yml", "Docker Compose (docker-compose.yml)", "orchestration-deploy"),
    ("docker-compose.yaml", "Docker Compose (docker-compose.yaml)", "orchestration-deploy"),
    ("compose.yml", "Docker Compose (compose.yml)", "orchestration-deploy"),
    ("compose.yaml", "Docker Compose (compose.yaml)", "orchestration-deploy"),
    ("Chart.yaml", "Helm / Kubernetes (Chart.yaml)", "orchestration-deploy"),
    ("k8s", "Kubernetes Manifests (k8s/)", "orchestration-deploy"),
    ("kubernetes", "Kubernetes Manifests (kubernetes/)", "orchestration-deploy"),
    ("helm", "Helm Charts (helm/)", "orchestration-deploy"),
    ("fly.toml", "Fly.io (fly.toml)", "orchestration-deploy"),
    ("render.yaml", "Render (render.yaml)", "orchestration-deploy"),
    ("vercel.json", "Vercel (vercel.json)", "orchestration-deploy"),
    (".github", "GitHub Actions (.github/workflows)", "ci-cd-quality"),
    (".gitlab-ci.yml", "GitLab CI (.gitlab-ci.yml)", "ci-cd-quality"),
    (".pre-commit-config.yaml", "pre-commit (.pre-commit-config.yaml)", "ci-cd-quality"),
    ("ruff.toml", "Ruff (ruff.toml)", "ci-cd-quality"),
    (".ruff.toml", "Ruff (.ruff.toml)", "ci-cd-quality"),
    ("Makefile", "Make (Makefile)", "ci-cd-quality"),
    ("justfile", "just (justfile)", "ci-cd-quality"),
]


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
    """SQLite3 cache for GitHub repositories, queries, mined issues, and top comments."""

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
                    category TEXT NOT NULL,
                    reactions_plus_one INTEGER NOT NULL,
                    reactions_total INTEGER NOT NULL,
                    comments_count INTEGER NOT NULL,
                    body_excerpt TEXT,
                    top_comments_json TEXT,
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
                    issue_url, repo_full_name, issue_number, title, category,
                    reactions_plus_one, reactions_total, comments_count,
                    body_excerpt, top_comments_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(issue_url) DO UPDATE SET
                    category = excluded.category,
                    reactions_plus_one = excluded.reactions_plus_one,
                    reactions_total = excluded.reactions_total,
                    comments_count = excluded.comments_count,
                    body_excerpt = excluded.body_excerpt,
                    top_comments_json = excluded.top_comments_json,
                    updated_at = excluded.updated_at
                """,
                (
                    item["issue_url"],
                    item["repo_full_name"],
                    item["issue_number"],
                    item["title"],
                    item.get("category") or "general",
                    item["reactions_plus_one"],
                    item["reactions_total"],
                    item["comments_count"],
                    item.get("body_excerpt") or "",
                    json.dumps(item.get("top_comments", [])),
                    item.get("created_at") or "",
                    now_ts(),
                ),
            )

    def close(self) -> None:
        self.conn.close()


def normalize_repo_query(q: str) -> str:
    """
    Scope free-text queries to repository name and description by default.
    GitHub's default search includes full README bodies, which frequently matches unrelated
    keyword-stuffed list repositories. Callers can still pass explicit `in:`, `topic:`, or `repo:` qualifiers.
    If `repo:owner/name` is passed, strips `repo:` and uses `owner/name in:name` so `/search/repositories` succeeds.
    """
    clean = q.strip()
    if clean.startswith("repo:") and "/" in clean and " " not in clean:
        owner_repo = clean.split("repo:", 1)[1]
        return f"{owner_repo} in:name"
    if "in:" not in clean and "topic:" not in clean and "repo:" not in clean:
        return f"{clean} in:name,description"
    return clean


def normalize_topic_query(topic: str) -> str:
    """Ensure a topic string is formatted with the GitHub `topic:` search qualifier."""
    clean = topic.strip()
    if clean.startswith("topic:"):
        return clean
    slug = clean.lower().replace(" ", "-")
    return f"topic:{slug}"


def is_noise_repo(raw: dict[str, Any]) -> bool:
    """
    Documented heuristic filter to exclude non-software/profile repositories from prior-art analysis:
    1. Exclude organization/user profile meta-repositories (`.github`).
    2. Exclude repositories with zero stars AND zero forks.
    3. Exclude repositories that have disabled issues (`has_issues == False`) AND have no description/topics,
       as they provide neither architectural metadata nor an issue board for pain-point mining.
    Note: Markdown-only repositories (where GitHub reports `language: None`) ARE preserved so Agent Skills
    and documentation-first specifications are not filtered out.
    """
    full_name = (raw.get("full_name") or "").lower()
    if full_name.endswith("/.github"):
        return True
    stars = int(raw.get("stargazers_count", 0))
    forks = int(raw.get("forks_count", 0))
    if stars == 0 and forks == 0:
        return True
    has_issues = bool(raw.get("has_issues", True))
    desc = (raw.get("description") or "").strip()
    topics = raw.get("topics") or []
    if not has_issues and not desc and not topics:
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
        graveyard_reason = "Explicitly archived by maintainer"
    elif is_graveyard:
        graveyard_reason = (
            f"Dormant heuristic: no pushes in {inactive_days} days (>365d threshold; "
            "inactivity signal only — verify via issues/commits before attributing cause)"
        )

    license_obj = raw.get("license") or {}
    license_spdx = license_obj.get("spdx_id") if isinstance(license_obj, dict) else ""
    if not license_spdx or license_spdx == "NOASSERTION":
        license_spdx = "Unspecified"

    return {
        "full_name": raw["full_name"],
        "html_url": raw["html_url"],
        "description": (raw.get("description") or "").strip(),
        "stars": stars,
        "forks": int(raw.get("forks_count", 0)),
        "open_issues_count": int(raw.get("open_issues_count", 0)),
        "language": raw.get("language") or "Markdown/Other",
        "license": license_spdx,
        "topics": raw.get("topics") or [],
        "created_at": created_at or "",
        "pushed_at": pushed_at or "",
        "archived": archived,
        "inactive_days": inactive_days,
        "star_velocity_per_month": velocity,
        "classification": classification,
        "graveyard_reason": graveyard_reason,
        "detected_configs": [],
    }


def parse_stack_signals_from_files(
    root_entries: list[str],
    pyproject_text: str = "",
    has_github_workflows: bool = False,
) -> list[dict[str, str]]:
    """
    Given a list of root file/directory names in a repository and optional `pyproject.toml` text,
    return structured config-file evidence proving which build/lock/container/CI tools are used.
    """
    entry_set = set(root_entries)
    signals: list[dict[str, str]] = []
    seen_tools: set[str] = set()

    # 1. Inspect pyproject.toml sections first if present
    if "pyproject.toml" in entry_set:
        py_lower = pyproject_text.lower()
        if "[tool.poetry" in py_lower:
            has_lock = "poetry.lock" in entry_set
            cfg_desc = "pyproject.toml ([tool.poetry]) + poetry.lock" if has_lock else "pyproject.toml ([tool.poetry])"
            signals.append(
                {
                    "config_file": cfg_desc,
                    "tool": "Poetry",
                    "category": "dependency-lock",
                }
            )
            seen_tools.update({"Poetry", "Poetry (poetry.lock)"})
        if "[tool.uv" in py_lower:
            has_lock = "uv.lock" in entry_set
            cfg_desc = "pyproject.toml ([tool.uv]) + uv.lock" if has_lock else "pyproject.toml ([tool.uv])"
            signals.append(
                {
                    "config_file": cfg_desc,
                    "tool": "uv",
                    "category": "dependency-lock",
                }
            )
            seen_tools.update({"uv", "uv (uv.lock)"})
        if "[tool.ruff" in py_lower:
            signals.append(
                {
                    "config_file": "pyproject.toml ([tool.ruff])",
                    "tool": "Ruff",
                    "category": "ci-cd-quality",
                }
            )
            seen_tools.update({"Ruff", "Ruff (ruff.toml)", "Ruff (.ruff.toml)"})
        if "[tool.pytest" in py_lower:
            signals.append(
                {
                    "config_file": "pyproject.toml ([tool.pytest])",
                    "tool": "pytest",
                    "category": "ci-cd-quality",
                }
            )
            seen_tools.add("pytest")
        if not any(k in py_lower for k in ("[tool.poetry", "[tool.uv")) and "[project]" in py_lower:
            signals.append(
                {
                    "config_file": "pyproject.toml ([project] PEP 621)",
                    "tool": "PEP 621 Python Packaging",
                    "category": "dependency-lock",
                }
            )

    # 2. Match known root config files & directories
    for filename, tool_label, category in CONFIG_SIGNATURES:
        if filename == ".github":
            if has_github_workflows:
                signals.append(
                    {
                        "config_file": ".github/workflows",
                        "tool": "GitHub Actions",
                        "category": "ci-cd-quality",
                    }
                )
            continue
        if filename in entry_set and tool_label not in seen_tools:
            signals.append(
                {
                    "config_file": filename,
                    "tool": tool_label,
                    "category": category,
                }
            )
            seen_tools.add(tool_label)

    return signals


def inspect_repo_stack_configs(
    repo_full_name: str,
    token: str | None,
    cache: RepoCache,
    rate_limit_info: dict[str, Any],
) -> list[dict[str, str]]:
    """
    Fetch root directory contents (and `pyproject.toml` / `.github` if present) from GitHub REST API
    to prove which dependency managers, containers, orchestrators, and CI tools the repo uses.
    """
    contents_url = f"https://api.github.com/repos/{repo_full_name}/contents"
    try:
        items = github_get_json(contents_url, token, cache, rate_limit_info)
        if not isinstance(items, list):
            return []
        root_names = [str(it.get("name") or "") for it in items if isinstance(it, dict)]
    except Exception:
        return []

    pyproject_text = ""
    if "pyproject.toml" in root_names:
        py_url = f"https://api.github.com/repos/{repo_full_name}/contents/pyproject.toml"
        try:
            py_payload = github_get_json(py_url, token, cache, rate_limit_info)
            if isinstance(py_payload, dict) and py_payload.get("content"):
                raw_b64 = str(py_payload["content"]).replace("\n", "")
                pyproject_text = base64.b64decode(raw_b64).decode("utf-8", errors="ignore")
        except Exception:
            pass

    has_workflows = False
    if ".github" in root_names:
        gh_url = f"https://api.github.com/repos/{repo_full_name}/contents/.github"
        try:
            gh_items = github_get_json(gh_url, token, cache, rate_limit_info)
            if isinstance(gh_items, list):
                has_workflows = any(
                    isinstance(it, dict) and str(it.get("name") or "") == "workflows" for it in gh_items
                )
        except Exception:
            pass

    return parse_stack_signals_from_files(
        root_entries=root_names,
        pyproject_text=pyproject_text,
        has_github_workflows=has_workflows,
    )


def is_substantive_pain_point(raw_issue: dict[str, Any]) -> bool:
    """
    Require minimum community validation before calling an open issue a 'Mined Pain Point':
    at least `MIN_ISSUE_PLUS_ONE` (+1) reactions OR at least `MIN_ISSUE_COMMENTS` comments.
    """
    reactions = raw_issue.get("reactions") or {}
    plus_one = int(reactions.get("+1", 0))
    total_reactions = int(reactions.get("total_count", plus_one))
    comments = int(raw_issue.get("comments", 0))
    return plus_one >= MIN_ISSUE_PLUS_ONE or total_reactions >= 2 or comments >= MIN_ISSUE_COMMENTS


def extract_pain_point(
    repo_full_name: str,
    raw_issue: dict[str, Any],
    category: str = "top_voted",
    top_comments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    reactions = raw_issue.get("reactions") or {}
    plus_one = int(reactions.get("+1", 0))
    total_reactions = int(reactions.get("total_count", plus_one))
    body = (raw_issue.get("body") or "").strip()
    clean_excerpt = " ".join(body.split())[:280]
    if len(body) > 280:
        clean_excerpt += "..."
    labels = [lbl.get("name", "") for lbl in (raw_issue.get("labels") or []) if isinstance(lbl, dict)]
    if any("bug" in l.lower() for l in labels):
        category = "bug_or_failure"
    return {
        "repo_full_name": repo_full_name,
        "issue_number": int(raw_issue.get("number", 0)),
        "title": (raw_issue.get("title") or "").strip(),
        "issue_url": raw_issue.get("html_url") or "",
        "category": category,
        "labels": labels,
        "reactions_plus_one": plus_one,
        "reactions_total": total_reactions,
        "comments_count": int(raw_issue.get("comments", 0)),
        "body_excerpt": clean_excerpt,
        "top_comments": top_comments or [],
        "created_at": raw_issue.get("created_at") or "",
    }


def extract_top_comments(raw_comments: list[dict[str, Any]], max_comments: int = 2) -> list[dict[str, Any]]:
    """Sort issue comments by reaction count and return the top substantive excerpts."""
    scored: list[tuple[int, dict[str, Any]]] = []
    for c in raw_comments:
        body = " ".join((c.get("body") or "").split()).strip()
        if len(body) < 25:
            continue
        reactions = c.get("reactions") or {}
        score = int(reactions.get("+1", 0)) * 2 + int(reactions.get("total_count", 0))
        author = (c.get("user") or {}).get("login") or "user"
        excerpt = body[:240] + ("..." if len(body) > 240 else "")
        scored.append(
            (
                score,
                {
                    "author": author,
                    "reactions": int(reactions.get("total_count", 0)),
                    "excerpt": excerpt,
                },
            )
        )
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored[:max_comments]]


def github_get_json(
    url: str,
    token: str | None,
    cache: RepoCache,
    rate_limit_info: dict[str, Any] | None = None,
) -> Any:
    cached = cache.get_cached(url)
    if cached is not None:
        return cached

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "PreFlight-PriorArt-Scout/0.4",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        if rate_limit_info is not None:
            rem = resp.headers.get("X-RateLimit-Remaining")
            lim = resp.headers.get("X-RateLimit-Limit")
            rst = resp.headers.get("X-RateLimit-Reset")
            if rem is not None:
                rate_limit_info["remaining"] = int(rem)
            if lim is not None:
                rate_limit_info["limit"] = int(lim)
            if rst is not None:
                rate_limit_info["reset_epoch"] = int(rst)
        data = json.loads(resp.read().decode("utf-8"))

    cache.set_cached(url, data)
    return data


def fetch_issue_top_comments(
    repo_full_name: str,
    issue_number: int,
    token: str | None,
    cache: RepoCache,
    rate_limit_info: dict[str, Any],
) -> list[dict[str, Any]]:
    url = f"https://api.github.com/repos/{repo_full_name}/issues/{issue_number}/comments?per_page=15"
    try:
        raw_comments = github_get_json(url, token, cache, rate_limit_info)
        if isinstance(raw_comments, list):
            return extract_top_comments(raw_comments, max_comments=2)
    except Exception:
        pass
    return []


def scout_github(
    queries: list[str],
    cache: RepoCache,
    token: str | None,
    auth_source: str,
    tool_queries: list[str] | None = None,
    topics: list[str] | None = None,
    tool_topics: list[str] | None = None,
    max_repos_per_query: int = 8,
    max_incumbents_for_issues: int = 4,
    issues_per_repo: int = 5,
) -> dict[str, Any]:
    # GitHub Search API rate limits: 30 req/min (authenticated) vs 10 req/min (unauthenticated)
    if auth_source == "unauthenticated":
        max_repos_per_query = min(max_repos_per_query, 5)
        max_incumbents_for_issues = min(max_incumbents_for_issues, 2)
        issues_per_repo = min(issues_per_repo, 3)

    discovered: dict[str, dict[str, Any]] = {}
    building_blocks: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    rate_limit_info: dict[str, Any] = {
        "search_api_quota": "30 req/min" if token else "10 req/min",
        "remaining": None,
        "limit": None,
        "reset_epoch": None,
    }

    combined_competitor_queries = list(queries) + [normalize_topic_query(t) for t in (topics or []) if t.strip()]
    combined_tool_queries = list(tool_queries or []) + [normalize_topic_query(t) for t in (tool_topics or []) if t.strip()]

    for q in combined_competitor_queries:
        if rate_limit_info.get("remaining") is not None and int(rate_limit_info["remaining"]) <= 1:
            errors.append("GitHub Search API rate limit nearly exhausted; skipping remaining queries.")
            break
        scoped_q = normalize_repo_query(q)
        encoded_q = urllib.parse.quote(scoped_q)
        url = f"https://api.github.com/search/repositories?q={encoded_q}&sort=stars&order=desc&per_page={max_repos_per_query}"
        try:
            payload = github_get_json(url, token, cache, rate_limit_info)
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
            retry_after = e.headers.get("Retry-After") if e.headers else None
            msg = f"Search query '{q}' failed: HTTP {e.code} ({e.reason})"
            if retry_after:
                msg += f" [Retry-After: {retry_after}s]"
            errors.append(msg)
        except Exception as e:
            errors.append(f"Search query '{q}' failed: {e}")

    # Scout open-source building blocks / libraries / tooling if requested
    for tq in combined_tool_queries:
        if rate_limit_info.get("remaining") is not None and int(rate_limit_info["remaining"]) <= 1:
            errors.append("GitHub Search API rate limit nearly exhausted; skipping remaining tool queries.")
            break
        scoped_tq = normalize_repo_query(tq)
        encoded_tq = urllib.parse.quote(scoped_tq)
        url = f"https://api.github.com/search/repositories?q={encoded_tq}&sort=stars&order=desc&per_page=5"
        try:
            payload = github_get_json(url, token, cache, rate_limit_info)
            for item in payload.get("items", []):
                if item.get("fork") or is_noise_repo(item):
                    continue
                classified = classify_repo(item)
                if classified["classification"] != "active_incumbent":
                    continue
                classified["classification"] = "oss_building_block"
                classified["matched_query"] = tq
                full_name = classified["full_name"]
                if full_name not in building_blocks:
                    building_blocks[full_name] = classified
                    cache.upsert_repo(classified)
        except urllib.error.HTTPError as e:
            errors.append(f"Tool query '{tq}' failed: HTTP {e.code} ({e.reason})")
        except Exception as e:
            errors.append(f"Tool query '{tq}' failed: {e}")

    all_repos = sorted(discovered.values(), key=lambda r: r["stars"], reverse=True)
    incumbents = [r for r in all_repos if r["classification"] == "active_incumbent"]
    graveyard = [r for r in all_repos if r["classification"] == "graveyard"]
    oss_tools = sorted(building_blocks.values(), key=lambda r: r["stars"], reverse=True)

    # Inspect config files (pyproject.toml, Dockerfile, .github/workflows, .pre-commit-config.yaml, etc.)
    # across top incumbents to prove what tooling real repos in this space use.
    max_config_inspections = 4 if token else 2
    observed_stack_signals: dict[str, dict[str, Any]] = {}
    for repo in incumbents[:max_config_inspections]:
        signals = inspect_repo_stack_configs(repo["full_name"], token, cache, rate_limit_info)
        repo["detected_configs"] = signals
        for sig in signals:
            key = f"{sig['category']}:{sig['tool']}"
            entry = observed_stack_signals.setdefault(
                key,
                {
                    "tool": sig["tool"],
                    "category": sig["category"],
                    "config_file": sig["config_file"],
                    "repos": [],
                },
            )
            if repo["full_name"] not in entry["repos"]:
                entry["repos"].append(repo["full_name"])

    pain_points_by_url: dict[str, dict[str, Any]] = {}
    for repo in incumbents[:max_incumbents_for_issues]:
        full_name = repo["full_name"]
        if int(repo.get("open_issues_count", 0)) == 0:
            continue

        # Pass A: Top-voted open issues (+1 reactions)
        # Pass B: Bug-labeled open issues (+1 reactions) to surface engineering/architecture failures
        issue_passes = [
            ("top_voted", f"repo:{full_name} is:issue is:open sort:reactions-+1-desc"),
            ("bug_or_failure", f"repo:{full_name} is:issue is:open label:bug sort:reactions-+1-desc"),
        ]
        for category, raw_q in issue_passes:
            if auth_source == "unauthenticated" and category == "bug_or_failure":
                continue
            issue_q = urllib.parse.quote(raw_q)
            issue_url = f"https://api.github.com/search/issues?q={issue_q}&per_page={issues_per_repo}"
            try:
                issue_payload = github_get_json(issue_url, token, cache, rate_limit_info)
                for raw_issue in issue_payload.get("items", []):
                    if "pull_request" in raw_issue:
                        continue
                    if not is_substantive_pain_point(raw_issue):
                        continue
                    html_url = raw_issue.get("html_url") or ""
                    if html_url in pain_points_by_url:
                        if category == "bug_or_failure":
                            pain_points_by_url[html_url]["category"] = "bug_or_failure"
                        continue
                    pp = extract_pain_point(full_name, raw_issue, category=category)
                    pain_points_by_url[html_url] = pp
            except urllib.error.HTTPError as e:
                errors.append(f"Pain-point mining ({category}) for '{full_name}' failed: HTTP {e.code}")
            except Exception as e:
                errors.append(f"Pain-point mining ({category}) for '{full_name}' failed: {e}")

    pain_points = sorted(
        pain_points_by_url.values(),
        key=lambda p: (
            1 if p.get("category") == "bug_or_failure" else 0,
            p["reactions_plus_one"],
            p["reactions_total"],
            p["comments_count"],
        ),
        reverse=True,
    )

    # Fetch top comments for the top 6 highest-signal issues
    max_comment_fetches = 6 if token else 2
    for pp in pain_points[:max_comment_fetches]:
        if int(pp.get("comments_count", 0)) > 0:
            pp["top_comments"] = fetch_issue_top_comments(
                pp["repo_full_name"],
                pp["issue_number"],
                token,
                cache,
                rate_limit_info,
            )
        cache.upsert_pain_point(pp)

    for pp in pain_points[max_comment_fetches:]:
        cache.upsert_pain_point(pp)

    search_limits = {
        "max_repos_per_query": max_repos_per_query,
        "max_incumbents_for_issues": max_incumbents_for_issues,
        "issues_per_repo": issues_per_repo,
        "sort_order": "stars:desc (single page per query; star-weighted sample)",
        "default_free_text_scope": "in:name,description (unless explicit topic:, in:, or repo: qualifier is passed)",
        "graveyard_heuristic": (
            f"Archived by maintainer OR >{GRAVEYARD_DAYS_THRESHOLD} days since last git push. "
            "Inactivity is a maintenance signal only — never claim a repo stalled due to a specific "
            "architectural choice without issue/commit evidence."
        ),
        "star_velocity_heuristic": "Approximate lifetime average (total_stars / age_months), not recent adoption momentum.",
    }

    return {
        "scouted_at": now_iso(),
        "auth_source": auth_source,
        "rate_limit": rate_limit_info,
        "search_limits": search_limits,
        "queries": combined_competitor_queries,
        "tool_queries": combined_tool_queries,
        "active_incumbents": incumbents,
        "graveyard_repos": graveyard,
        "oss_building_blocks": oss_tools,
        "observed_stack_configs": list(observed_stack_signals.values()),
        "pain_points": pain_points,
        "warnings": errors,
    }


def format_markdown_digest(report: dict[str, Any]) -> str:
    incumbents = report.get("active_incumbents", [])
    graveyard = report.get("graveyard_repos", [])
    oss_tools = report.get("oss_building_blocks", [])
    observed_configs = report.get("observed_stack_configs", [])
    pain_points = report.get("pain_points", [])
    warnings = report.get("warnings", [])
    rl = report.get("rate_limit") or {}
    limits = report.get("search_limits") or {}

    rl_str = rl.get("search_api_quota", "unknown")
    if rl.get("remaining") is not None and rl.get("limit") is not None:
        rl_str += f" ({rl['remaining']}/{rl['limit']} remaining in current window)"

    lines = [
        "# Prior-Art & Stack Config Scout Digest",
        f"- **Auth Mode:** `{report.get('auth_source', 'unknown')}` — Search API Quota: `{rl_str}`",
        f"- **Competitor Queries (`-q` / `--topic`):** {', '.join(f'`{q}`' for q in report.get('queries', []))}",
    ]
    if report.get("tool_queries"):
        lines.append(f"- **OSS Tooling Queries (`-t` / `--tool-topic`):** {', '.join(f'`{q}`' for q in report.get('tool_queries', []))}")
    if limits:
        lines.append(
            f"- **Search Scope & Heuristics:** Up to {limits.get('max_repos_per_query', 8)} star-sorted repos/query "
            f"(`{limits.get('default_free_text_scope', 'in:name,description')}`). "
            "Star velocity (`stars / age_months`) and the >365d dormant threshold are heuristics, not causal proof."
        )
    lines.extend(
        [
            f"- **Discovered:** {len(incumbents)} Active Incumbents | {len(graveyard)} Graveyard/Dormant Repos | "
            f"{len(observed_configs)} Verified Config Signals | {len(oss_tools)} OSS Building Blocks | {len(pain_points)} Verified Pain Points",
            "",
        ]
    )

    if warnings:
        lines.append("## Warnings")
        for w in warnings:
            lines.append(f"- ⚠️ {w}")
        lines.append("")

    lines.append("## Active Incumbents (Top Maintained Alternatives)")
    if not incumbents:
        lines.append("_No active incumbents found._")
    else:
        lines.append("| Repo | Stars | Avg Velocity (Heuristic) | Last Push | Verified Config Files | Summary |")
        lines.append("| :--- | :---: | :---: | :---: | :--- | :--- |")
        for r in incumbents[:8]:
            desc = (r.get("description") or "—").replace("|", "\\|")[:90]
            cfgs = ", ".join(f"`{c['config_file']}`" for c in (r.get("detected_configs") or [])[:4]) or "—"
            lines.append(
                f"| [{r['full_name']}]({r['html_url']}) | ⭐ {r['stars']} | {r['star_velocity_per_month']}/mo | {r['inactive_days']}d ago | {cfgs} | {desc} |"
            )
    lines.append("")

    if observed_configs:
        lines.append("## Stack Config Evidence Across Scouted Repos (Proof of Tool Usage)")
        lines.append("| Category | Tool Proven | Config File Evidence | Seen In Repos |")
        lines.append("| :--- | :--- | :--- | :--- |")
        for item in observed_configs:
            repos_str = ", ".join(f"`{r}`" for r in item.get("repos", []))
            lines.append(
                f"| `{item.get('category')}` | **{item.get('tool')}** | `{item.get('config_file')}` | {repos_str} |"
            )
        lines.append("")

    lines.append("## Graveyard & Dormant Check (Heuristic: Archived or >365d No Pushes)")
    lines.append(
        "_Note: >365d inactivity is a maintenance heuristic only. Do not claim a repository stalled due to a specific architectural choice without citing an issue or maintainer post-mortem._"
    )
    if not graveyard:
        lines.append("_No archived or dormant repos flagged for these queries._")
    else:
        lines.append("| Repo | Stars | Inactive | Heuristic Signal | Summary |")
        lines.append("| :--- | :---: | :---: | :--- | :--- |")
        for r in graveyard[:6]:
            desc = (r.get("description") or "—").replace("|", "\\|")[:90]
            lines.append(
                f"| [{r['full_name']}]({r['html_url']}) | ⭐ {r['stars']} | {r['inactive_days']}d | {r['graveyard_reason']} | {desc} |"
            )
    lines.append("")

    if oss_tools:
        lines.append("## Scouted OSS Building Blocks & Libraries (`--tool-query` / `--tool-topic`)")
        lines.append("| Repo | Stars | License | Language | Last Push | Purpose / Summary |")
        lines.append("| :--- | :---: | :---: | :---: | :---: | :--- |")
        for t in oss_tools[:10]:
            desc = (t.get("description") or "—").replace("|", "\\|")[:95]
            lines.append(
                f"| [{t['full_name']}]({t['html_url']}) | ⭐ {t['stars']} | `{t.get('license', 'Unspecified')}` | "
                f"{t.get('language', '—')} | {t['inactive_days']}d ago | {desc} |"
            )
        lines.append("")

    lines.append("## Pain-Point Mining (Bugs & Top-Voted Open Issues Across Incumbents)")
    if not pain_points:
        lines.append("_No open issues met the minimum reaction/comment threshold._")
    else:
        for p in pain_points[:10]:
            cat_badge = "🐛 BUG/FAILURE" if p.get("category") == "bug_or_failure" else "🔥 TOP-VOTED"
            lines.append(
                f"- [{cat_badge}] **[{p['repo_full_name']}#{p['issue_number']}]({p['issue_url']})**: {p['title']} "
                f"(👍 {p['reactions_plus_one']} | 💬 {p['comments_count']})"
            )
            if p.get("body_excerpt"):
                lines.append(f"  > **Issue:** {p['body_excerpt']}")
            for tc in p.get("top_comments", []):
                lines.append(
                    f"  > 💬 **@{tc['author']}** (👍 {tc['reactions']}): {tc['excerpt']}"
                )

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PreFlight GitHub Prior-Art, Config Inspector & OSS Building-Block Scout")
    parser.add_argument("--workspace", default=".", help="Target workspace directory")
    parser.add_argument(
        "--query",
        "-q",
        action="append",
        default=[],
        help="GitHub competitor repository search query (can be passed multiple times)",
    )
    parser.add_argument(
        "--topic",
        action="append",
        default=[],
        help="GitHub topic qualifier for competitor repositories (e.g. 'workflow-engine', 'job-scheduler')",
    )
    parser.add_argument(
        "--tool-query",
        "-t",
        action="append",
        default=[],
        help="GitHub search query for open-source building blocks, SDKs, or tools to build the project",
    )
    parser.add_argument(
        "--tool-topic",
        action="append",
        default=[],
        help="GitHub topic qualifier for open-source building blocks (e.g. 'sqlite', 'cron')",
    )
    parser.add_argument("--max-repos", type=int, default=8, help="Max repos per query")
    parser.add_argument("--json", action="store_true", help="Print JSON output instead of Markdown digest")

    args = parser.parse_args(argv)
    if not args.query and not args.topic:
        parser.error("At least one `--query` (`-q`) or `--topic` is required.")

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
            tool_queries=args.tool_query,
            topics=args.topic,
            tool_topics=args.tool_topic,
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
