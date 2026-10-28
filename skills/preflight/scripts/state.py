#!/usr/bin/env python3
"""
PreFlight State, Tooling Matrix, Memory Advisor & Decision Ledger CLI (`scripts/state.py`).

Manages:
- .preflight/state.json (Working State + Evidence-Gated 5-dimension Readiness Rubric + Tooling & Memory Architecture)
- .preflight/decisions.json + docs/adr/NNNN-<slug>.md (Decision Ledger)
- .preflight/STACK.md (Tooling, OSS Building Blocks & Project Maintenance Stack document)

Programmatic Evidence Rules (anti-theater enforcement):
1. `score == 20` ("stress-tested") requires:
   - A substantive summary (>= 40 characters)
   - At least 2 concrete edge cases (`--edge-case`)
2. `dimension == "differentiation"` with `score > 0` requires:
   - `.preflight/prior-art.json` must exist and contain at least 1 scouted repository
   - For `score == 20`, the summary or edge cases must explicitly cite at least one discovered
     repository by its full `owner/repo` name from `prior-art.json` (bare repo names such as
     `cron` are rejected because they collide with ordinary words).
3. `dimension == "memory"` with `score == 20` requires `set-memory-arch` (strategy, communication
   pattern, and >= 1 failure mode).
4. `readiness_unlocked` requires:
   - Total score >= 80%
   - Zero dimensions at 0%
   - `.preflight/prior-art.json` present with >= 1 discovered repository
   - At least 1 recorded ADR in `.preflight/decisions.json`
   - At least 1 recorded Red-Team Critique in `red_team_critiques`
   - A Memory Architecture (`set-memory-arch`: strategy, communication pattern, >= 1 failure mode)
   - At least 1 Stack Explained tool entry (`add-tool`)
   - Both `topology_mermaid` and `sequence_mermaid` populated via `set-design`
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DIMENSIONS = (
    "problem",
    "scope",
    "memory",
    "bottlenecks",
    "differentiation",
)

DIMENSION_LABELS = {
    "problem": "Problem & User Pain",
    "scope": "Scope & Non-Goals",
    "memory": "State, Memory & Agent Communication",
    "bottlenecks": "Bottlenecks & Failure Modes",
    "differentiation": "Prior-Art Differentiation",
}

TOOL_CATEGORIES = (
    "core-oss",
    "dependency-lock",
    "container-runtime",
    "orchestration-deploy",
    "ci-cd-quality",
    "storage-memory",
    "observability",
)

MEMORY_STRATEGIES = (
    "stateless",
    "transactional-db",
    "lexical-fts",
    "rag-vector-db",
    "hybrid-search",
    "episodic-agent-state",
)

MIN_SUMMARY_LEN_FOR_20 = 40
MIN_EDGE_CASES_FOR_20 = 2


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(text: str, max_len: int = 60) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if not slug:
        return "decision"
    if len(slug) <= max_len:
        return slug
    truncated = slug[:max_len]
    if "-" in truncated:
        word_cut = truncated.rsplit("-", 1)[0].strip("-")
        if word_cut:
            return word_cut
    return truncated.strip("-") or "decision"


class GateVerdict:
    """
    Immutable value object representing the Readiness Gate evaluation.
    Unpacks as `(score, unlocked, missing)` for backwards compatibility.
    """

    def __init__(
        self,
        score: int,
        unlocked: bool,
        missing: list[str] | tuple[str, ...],
        is_draft: bool | None = None,
    ) -> None:
        self._score = int(score)
        self._unlocked = bool(unlocked)
        self._missing = tuple(missing)
        self._is_draft = (not self._unlocked) if is_draft is None else bool(is_draft)

    @property
    def score(self) -> int:
        return self._score

    @property
    def unlocked(self) -> bool:
        return self._unlocked

    @property
    def missing(self) -> list[str]:
        return list(self._missing)

    @property
    def is_draft(self) -> bool:
        return self._is_draft

    def __iter__(self):
        yield self._score
        yield self._unlocked
        yield list(self._missing)

    def __getitem__(self, index: int) -> Any:
        return (self._score, self._unlocked, list(self._missing))[index]

    def __repr__(self) -> str:
        return f"GateVerdict(score={self._score}, unlocked={self._unlocked}, missing={len(self._missing)} items, is_draft={self._is_draft})"


class ArtifactWatermarker:
    """Unified watermarking pipeline for PreFlight specifications, stacks, blueprints, and tickets."""

    @staticmethod
    def title(title: str, is_draft: bool) -> str:
        return f"[DRAFT] {title}" if is_draft else title

    @staticmethod
    def banner_markdown(is_draft: bool, doc_name: str = "document") -> list[str]:
        if not is_draft:
            return []
        return [
            f"> ⚠️ **DRAFT — READINESS GATE LOCKED:** This {doc_name} was exported before all PreFlight readiness requirements passed.",
            "",
        ]

    @staticmethod
    def ticket_status(is_draft: bool) -> str:
        return "draft" if is_draft else "ready-for-agent"

    @staticmethod
    def ticket_banner_markdown(is_draft: bool) -> list[str]:
        if not is_draft:
            return []
        return [
            "> ⚠️ **DRAFT — DO NOT EXECUTE YET:** Exported via `--force` while Readiness Gate is locked.",
            "",
        ]


class WorkspaceStore:
    """
    Manages `.preflight/` file paths, defaults, persistence, and reset lifecycle.
    Prevents path leakage and eliminates loader side effects.
    """

    def __init__(self, workspace: Path | str) -> None:
        self.workspace = Path(workspace).resolve()

    @property
    def preflight_dir(self) -> Path:
        return self.workspace / ".preflight"

    @property
    def state_path(self) -> Path:
        return self.preflight_dir / "state.json"

    @property
    def decisions_path(self) -> Path:
        return self.preflight_dir / "decisions.json"

    @property
    def prior_art_path(self) -> Path:
        return self.preflight_dir / "prior-art.json"

    @property
    def cache_path(self) -> Path:
        return self.preflight_dir / "cache.db"

    @property
    def spec_path(self) -> Path:
        return self.preflight_dir / "SPEC.md"

    @property
    def stack_path(self) -> Path:
        return self.preflight_dir / "STACK.md"

    @property
    def issues_dir(self) -> Path:
        return self.preflight_dir / "issues"

    @property
    def adr_dir(self) -> Path:
        return self.workspace / "docs" / "adr"

    @property
    def blueprint_html_path(self) -> Path:
        return self.workspace / "blueprint_report.html"

    def ensure_preflight_dir(self) -> Path:
        self.preflight_dir.mkdir(parents=True, exist_ok=True)
        return self.preflight_dir

    def load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            state = default_state()
            evaluate_gate(state, self.workspace)
            return state
        data = json.loads(self.state_path.read_text(encoding="utf-8"))
        data.setdefault("tooling_recommendations", [])
        mem = data.setdefault(
            "memory_architecture",
            {
                "strategy": "",
                "secondary_strategies": [],
                "agent_communication_pattern": "",
                "workflow_memory_flow": "",
                "rationale": "",
                "alternatives_considered": "",
                "failure_modes": [],
            },
        )
        mem.setdefault("secondary_strategies", [])
        evaluate_gate(data, self.workspace)
        return data

    def save_state(self, state: dict[str, Any]) -> Path:
        state["updated_at"] = now_iso()
        status_clean(state, self.workspace)
        self.ensure_preflight_dir()
        self.state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

        # Keep STACK.md synchronized whenever tooling or memory exists
        if state.get("tooling_recommendations") or (state.get("memory_architecture") or {}).get("strategy"):
            verdict = evaluate_gate(state, self.workspace)
            self.stack_path.write_text(build_stack_markdown(state, is_draft=verdict.is_draft) + "\n", encoding="utf-8")

        return self.state_path

    def load_decisions(self) -> list[dict[str, Any]]:
        if not self.decisions_path.exists():
            return []
        try:
            return json.loads(self.decisions_path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def save_decisions(self, decisions: list[dict[str, Any]]) -> Path:
        self.ensure_preflight_dir()
        self.decisions_path.write_text(json.dumps(decisions, indent=2) + "\n", encoding="utf-8")
        return self.decisions_path

    def load_prior_art(self) -> dict[str, Any] | None:
        if not self.prior_art_path.exists():
            return None
        try:
            return json.loads(self.prior_art_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def reset(
        self,
        purge_cache: bool = False,
        clear_adrs: bool = True,
        keep_adrs: bool | None = None,
    ) -> list[str]:
        if keep_adrs is not None:
            clear_adrs = not keep_adrs
        removed: list[str] = []
        recorded_adr_files: list[str] = []
        if clear_adrs and self.decisions_path.exists():
            try:
                decisions_data = json.loads(self.decisions_path.read_text(encoding="utf-8"))
                if isinstance(decisions_data, list):
                    for entry in decisions_data:
                        if isinstance(entry, dict) and entry.get("file"):
                            recorded_adr_files.append(str(entry["file"]))
            except Exception:
                pass

        targets = [
            self.state_path,
            self.decisions_path,
            self.prior_art_path,
            self.spec_path,
            self.stack_path,
            self.blueprint_html_path,
        ]
        if purge_cache:
            targets.append(self.cache_path)

        for t in targets:
            if t.exists():
                t.unlink()
                removed.append(str(t.relative_to(self.workspace)))

        if clear_adrs and recorded_adr_files:
            for rel_file in recorded_adr_files:
                adr_file = (self.workspace / rel_file).resolve()
                if adr_file.exists() and adr_file.is_relative_to(self.workspace.resolve()):
                    adr_file.unlink()
                    removed.append(str(adr_file.relative_to(self.workspace.resolve())))

        if self.issues_dir.exists():
            for issue_file in sorted(self.issues_dir.glob("*.md")):
                issue_file.unlink()
                removed.append(str(issue_file.relative_to(self.workspace)))

        return removed


def get_preflight_dir(workspace: Path) -> Path:
    return WorkspaceStore(workspace).ensure_preflight_dir()


def default_state(name: str = "", summary: str = "") -> dict[str, Any]:
    return {
        "project_name": name or "Untitled Project",
        "project_summary": summary,
        "target_runtime": "",
        "tech_stack": [],
        "bottlenecks": [],
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "dimensions": {
            dim: {
                "label": DIMENSION_LABELS[dim],
                "score": 0,  # 0, 10, or 20
                "status": "untouched",  # untouched | surface | stress-tested
                "summary": "",
                "edge_cases": [],
            }
            for dim in DIMENSIONS
        },
        "tooling_recommendations": [],
        "memory_architecture": {
            "strategy": "",
            "secondary_strategies": [],
            "agent_communication_pattern": "",
            "workflow_memory_flow": "",
            "rationale": "",
            "alternatives_considered": "",
            "failure_modes": [],
        },
        "red_team_critiques": [],
        "system_design": {
            "topology_mermaid": "",
            "sequence_mermaid": "",
            "options_matrix": [],
            "implementation_steps": [],
        },
        "readiness_score": 0,
        "readiness_unlocked": False,
        "missing_gate_requirements": [],
    }


def reset_workspace_state(
    workspace: Path,
    purge_cache: bool = False,
    clear_adrs: bool = True,
    keep_adrs: bool | None = None,
) -> list[str]:
    """
    Delete all pre-performed scores, states, decisions, prior-art snapshots, and generated specs
    so the user can run a new idea or re-run the same idea cleanly from zero.
    Only deletes ADR markdown files explicitly listed in `.preflight/decisions.json` when `clear_adrs=True`,
    preserving any pre-existing repository ADRs in `docs/adr/`.
    """
    return WorkspaceStore(workspace).reset(
        purge_cache=purge_cache, clear_adrs=clear_adrs, keep_adrs=keep_adrs
    )


def load_prior_art(workspace: Path) -> dict[str, Any] | None:
    return WorkspaceStore(workspace).load_prior_art()


def load_decisions(workspace: Path) -> list[dict[str, Any]]:
    return WorkspaceStore(workspace).load_decisions()


def save_decisions(workspace: Path, decisions: list[dict[str, Any]]) -> Path:
    return WorkspaceStore(workspace).save_decisions(decisions)


# Specific associations between known project maintenance/build tools and their canonical config signatures
KNOWN_TOOL_CONFIG_ASSOCIATIONS: dict[str, set[str]] = {
    "uv": {"uv.lock", "pyproject.toml"},
    "poetry": {"poetry.lock", "pyproject.toml"},
    "pip": {"requirements.txt", "requirements.in", "setup.py", "pyproject.toml"},
    "pip-tools": {"requirements.txt", "requirements.in"},
    "docker": {"dockerfile", "containerfile", "docker-compose.yml", "docker-compose.yaml", ".dockerignore"},
    "compose": {"docker-compose.yml", "docker-compose.yaml"},
    "kubernetes": {"k8s", "chart.yaml", "deployment.yaml", "helm"},
    "k8s": {"k8s", "chart.yaml", "deployment.yaml", "helm"},
    "helm": {"chart.yaml", "helm"},
    "github actions": {".github/workflows", "workflows"},
    "pre-commit": {".pre-commit-config.yaml"},
    "ruff": {"ruff.toml", ".ruff.toml", "pyproject.toml"},
    "mypy": {"mypy.ini", ".mypy.ini", "pyproject.toml", "setup.cfg"},
    "pytest": {"pytest.ini", "pyproject.toml", "setup.cfg"},
    "pnpm": {"pnpm-lock.yaml", "package.json"},
    "npm": {"package-lock.json", "package.json"},
    "yarn": {"yarn.lock", "package.json"},
    "cargo": {"cargo.lock", "cargo.toml"},
    "rust": {"cargo.lock", "cargo.toml"},
    "go": {"go.sum", "go.mod"},
    "make": {"makefile"},
}


def _tool_matches_config_signature(recommended: str, config_name: str) -> bool:
    rec_lower = recommended.lower()
    cfg_base = Path(config_name).name.lower()
    cfg_path = config_name.lower().replace("\\", "/")

    # Check known tool associations
    for tool_key, allowed_cfgs in KNOWN_TOOL_CONFIG_ASSOCIATIONS.items():
        if tool_key in rec_lower:
            for ac in allowed_cfgs:
                if ac in (cfg_base, cfg_path) or cfg_path.endswith(ac):
                    return True
            return False

    rec_tokens = [tok for tok in re.findall(r"[a-z0-9]+", rec_lower) if len(tok) >= 3]
    return any(tok in cfg_base for tok in rec_tokens)


def verify_config_proof(workspace: Path, config_proof: str, recommended: str = "") -> tuple[str, str]:
    """
    Check whether a tool's `config_proof` is backed by empirical evidence in either:
    1. `.preflight/prior-art.json` (`observed_stack_configs` or `detected_configs`), or
    2. An existing file/directory in `workspace`.
    Requires that the cited config file actually corresponds to the recommended tool
    (tool-to-config pairing), preventing unrelated files (e.g. a generic `Dockerfile`)
    from verifying an arbitrary tool (e.g. `Redis`).
    Returns `(proof_status, proof_source)` where `proof_status` is `"verified"` or `"claimed-unverified"`.
    """
    raw = config_proof.strip()
    if not raw or raw == "—":
        return "claimed-unverified", "none"

    # Extract candidate file/path tokens (e.g., "pyproject.toml ([tool.uv]) + uv.lock" -> ["pyproject.toml", "uv.lock"])
    candidates: list[str] = []
    for part in re.split(r"[\s+,;|]+", raw):
        cleaned = part.strip("()[]`'\"")
        if not cleaned or cleaned.startswith("["):
            continue
        if "." in cleaned or "/" in cleaned or cleaned in ("Dockerfile", "Containerfile", "Makefile", "justfile", "k8s", "helm"):
            candidates.append(cleaned.rstrip("/"))

    rec_lower = recommended.lower()

    # 1. Check workspace files
    for cand in candidates:
        cand_path = (workspace / cand).resolve()
        if cand_path.exists() and cand_path.is_relative_to(workspace.resolve()):
            # If candidate directly matches known tool association signature:
            if _tool_matches_config_signature(recommended, cand):
                return "verified", f"workspace:{cand}"
            # For general multi-tool manifests (pyproject.toml, requirements.txt, docker-compose.yml, package.json):
            # Inspect the file content on disk to check if the tool is actually configured/referenced
            if cand_path.is_file() and cand in ("pyproject.toml", "requirements.txt", "requirements.in", "docker-compose.yml", "docker-compose.yaml", "package.json", "Makefile"):
                try:
                    file_text = cand_path.read_text(encoding="utf-8", errors="ignore")[:32768].lower()
                    rec_tokens = [tok for tok in re.findall(r"[a-z0-9_-]+", rec_lower) if len(tok) >= 3]
                    if any(tok in file_text for tok in rec_tokens):
                        return "verified", f"workspace:{cand}"
                except Exception:
                    pass

    # 2. Check .preflight/prior-art.json observed_stack_configs & incumbent detected_configs
    prior_art = load_prior_art(workspace)
    if prior_art:
        observed = list(prior_art.get("observed_stack_configs") or [])
        for inc in prior_art.get("active_incumbents") or []:
            observed.extend(inc.get("detected_configs") or [])
        raw_lower = raw.lower()
        for oc in observed:
            oc_cfg = str(oc.get("config_file") or "").lower()
            oc_tool = str(oc.get("tool") or "").lower()

            # Ensure tool pairing: recommended tool must match observed tool
            rec_matches_tool = (
                (oc_tool and (oc_tool in rec_lower or rec_lower in oc_tool))
                or _tool_matches_config_signature(recommended, oc_cfg)
            )
            if not rec_matches_tool:
                continue

            # Check config match
            if oc_cfg and (oc_cfg in raw_lower or raw_lower in oc_cfg):
                return "verified", f"scout:{oc.get('config_file')}"
            for cand in candidates:
                cand_base = Path(cand).name.lower()
                if cand_base and (cand_base == oc_cfg or cand_base in oc_cfg or oc_cfg in cand_base):
                    return "verified", f"scout:{oc.get('config_file')}"
            # Tool-name fallback only applies when the proof names no concrete file
            if not candidates and rec_matches_tool:
                return "verified", f"scout:{oc.get('config_file')}"

    return "claimed-unverified", "unverified-claim"


def cites_repo(text: str, full_name: str) -> bool:
    """Return True when `text` cites `full_name` (`owner/repo`) as a whole token, not a substring."""
    if not full_name:
        return False
    pattern = r"(?<![\w./-])" + re.escape(full_name) + r"(?![\w/-])"
    return re.search(pattern, text) is not None


def evaluate_gate(state: dict[str, Any], workspace: Path | None = None) -> GateVerdict:
    dims = state.get("dimensions", {})
    scores = [int(dims.get(d, {}).get("score", 0)) for d in DIMENSIONS]
    total = max(0, min(100, sum(scores)))
    missing: list[str] = []

    if total < 80:
        missing.append(f"Total score is {total}% (requires >= 80%)")

    zero_dims = [d for d in DIMENSIONS if int(dims.get(d, {}).get("score", 0)) == 0]
    if zero_dims:
        missing.append(f"Untouched (0%) dimensions: {', '.join(zero_dims)}")

    mem = state.get("memory_architecture") or {}
    strat = (mem.get("strategy") or "").strip().lower()
    if not strat:
        missing.append("Memory strategy (`set-memory-arch --strategy ...`) is required")
    elif strat == "stateless":
        rat = (mem.get("rationale") or "").strip()
        if len(rat) < 15:
            missing.append(
                "Stateless architecture requires an explicit rationale (`--rationale`, >= 15 chars) "
                "explaining why persistent memory and agent communication do not apply"
            )
    else:
        if not (mem.get("agent_communication_pattern") or "").strip():
            missing.append("Agent/component communication pattern (`set-memory-arch --communication ...`) is required")
        if not (mem.get("failure_modes") or []):
            missing.append("At least 1 Memory Failure Mode (`set-memory-arch --failure-mode ...`) is required")

    if not (state.get("tooling_recommendations") or []):
        missing.append("At least 1 Stack Explained tool entry (`add-tool`) is required")

    if not (state.get("red_team_critiques") or []):
        missing.append("At least 1 Red-Team Critique (`add-critique`) is required")

    sys_design = state.get("system_design") or {}
    if not (sys_design.get("topology_mermaid") or "").strip() or not (sys_design.get("sequence_mermaid") or "").strip():
        missing.append(
            "Both `topology_mermaid` and `sequence_mermaid` must be populated (`set-design --topology ... --sequence ...`)"
        )

    if workspace is not None:
        prior_art = load_prior_art(workspace)
        has_repos = bool(
            prior_art
            and ((prior_art.get("active_incumbents") or []) or (prior_art.get("graveyard_repos") or []))
        )
        if not has_repos:
            missing.append("Prior-Art Scout (`scout.py`) has not been run (.preflight/prior-art.json missing or empty)")

        decisions = load_decisions(workspace)
        if not decisions:
            missing.append("At least 1 Architecture Decision Record (`add-decision`) is required")

    unlocked = len(missing) == 0
    state["readiness_score"] = total
    state["readiness_unlocked"] = unlocked
    state["missing_gate_requirements"] = missing
    return GateVerdict(score=total, unlocked=unlocked, missing=missing, is_draft=not unlocked)


def compute_readiness(state: dict[str, Any], workspace: Path | None = None) -> tuple[int, bool]:
    verdict = evaluate_gate(state, workspace)
    return verdict.score, verdict.unlocked


def load_state(workspace: Path) -> dict[str, Any]:
    return WorkspaceStore(workspace).load_state()


def strip_step_prefix(raw_step: str) -> str:
    """Strip leading 'Step 1:', '1.', or '01 -' numbering without corrupting leading numbers like '100ms'."""
    return re.sub(r"^\s*(?:step\s+\d+\s*[:.\-]\s*|\d+\s*[.)]\s+)", "", raw_step, flags=re.IGNORECASE).strip()


def format_memory_strategy_display(mem: dict[str, Any]) -> str:
    primary = (mem.get("strategy") or "").strip()
    if not primary:
        return "Unspecified"
    secondaries = [s.strip() for s in (mem.get("secondary_strategies") or []) if s.strip() and s.strip() != primary]
    if secondaries:
        return f"{primary} (primary) + {', '.join(secondaries)} (secondary)"
    return primary


def format_stack_explained_table(tools: list[dict[str, Any]]) -> list[str]:
    """Return Markdown table lines for the 'Stack Explained' tooling list, separating Verified vs Claimed proof."""
    lines = [
        "| Tool | Stage (`Now` / `Later`) | What Job It Does | Why Needed | Alternative Considered | Config Proof & Verification |",
        "| :--- | :---: | :--- | :--- | :--- | :--- |",
    ]
    for t in tools:
        stage = (t.get("stage") or "now").upper()
        proof = t.get("config_proof") or "—"
        status = t.get("proof_status") or "claimed-unverified"
        source = t.get("proof_source") or ""
        if status == "verified":
            badge = f"✅ Verified (`{source}`): `{proof}`" if source else f"✅ Verified: `{proof}`"
        else:
            badge = f"⚠️ Claimed / Unverified: `{proof}`"
        lines.append(
            f"| **{t.get('recommended', '—')}** (`{t.get('category', 'core-oss')}`) | **{stage}** | "
            f"{t.get('purpose', '—')} | {t.get('why', '—')} | {t.get('alternatives', '—')} | {badge} |"
        )
    return lines


def build_stack_markdown(state: dict[str, Any], is_draft: bool | None = None) -> str:
    project_name = state.get("project_name") or "Untitled Project"
    tools = state.get("tooling_recommendations") or []
    mem = state.get("memory_architecture") or {}
    draft = (not bool(state.get("readiness_unlocked", False))) if is_draft is None else is_draft
    title = ArtifactWatermarker.title(f"Stack Explained & Memory Architecture: {project_name}", draft)

    lines = [
        f"# {title}",
        "",
    ]
    lines.extend(ArtifactWatermarker.banner_markdown(draft, doc_name="stack document"))

    lines.extend(
        [
            "## 1. Stack Explained (Tooling, Alternatives, Now vs. Later & Proof Status)",
            "",
        ]
    )
    if not tools:
        lines.append("_No tooling recommendations recorded yet._")
        lines.append("")
    else:
        verified_tools = [t for t in tools if t.get("proof_status") == "verified"]
        claimed_tools = [t for t in tools if t.get("proof_status") != "verified"]
        lines.extend(format_stack_explained_table(tools))
        lines.append("")
        lines.append(
            f"- **Verification Summary:** {len(verified_tools)} Verified (backed by `scout.py` or workspace files) "
            f"| {len(claimed_tools)} Claimed / Unverified (recommended for target architecture, not yet present on disk)."
        )
        lines.append("")

    lines.extend(["## 2. Memory, State & Agent Communication Architecture", ""])
    lines.extend(format_memory_architecture_lines(mem, failure_heading="### Anticipated Memory Failure Modes & Mitigations"))

    return "\n".join(lines)


def format_memory_architecture_lines(mem: dict[str, Any], failure_heading: str | None = None) -> list[str]:
    """Shared Markdown bullets for a Memory Architecture (used by STACK.md and SPEC.md)."""
    secondaries = [s for s in (mem.get("secondary_strategies") or []) if s]
    lines = [
        f"- **Primary Memory Strategy:** `{mem.get('strategy') or 'Unspecified'}`",
        f"- **Secondary / Combined Strategies:** {', '.join(f'`{s}`' for s in secondaries) if secondaries else 'None (single-strategy)'}",
        f"- **Combined Memory Profile:** `{format_memory_strategy_display(mem)}`",
        f"- **Agent / Component Communication Pattern:** {mem.get('agent_communication_pattern') or '—'}",
        f"- **Workflow Memory Lifecycle:** {mem.get('workflow_memory_flow') or '—'}",
        f"- **Why This Strategy (vs. RAG / Vector DB / Alternatives):** {mem.get('rationale') or '—'}",
        f"- **Alternatives Considered:** {mem.get('alternatives_considered') or '—'}",
        "",
    ]
    fms = mem.get("failure_modes") or []
    if fms:
        if failure_heading:
            lines.extend([failure_heading, ""])
        lines.extend(f"- ⚠️ {fm}" for fm in fms)
        lines.append("")
    return lines


def save_state(workspace: Path, state: dict[str, Any]) -> Path:
    return WorkspaceStore(workspace).save_state(state)


def status_clean(state: dict[str, Any], workspace: Path | None = None) -> dict[str, Any]:
    for dim in DIMENSIONS:
        d = state.setdefault("dimensions", {}).setdefault(
            dim,
            {
                "label": DIMENSION_LABELS[dim],
                "score": 0,
                "status": "untouched",
                "summary": "",
                "edge_cases": [],
            },
        )
        d["label"] = DIMENSION_LABELS[dim]
        score = int(d.get("score", 0))
        if score >= 20:
            d["score"] = 20
            d["status"] = "stress-tested"
        elif score >= 10:
            d["score"] = 10
            d["status"] = "surface"
        else:
            d["score"] = 0
            d["status"] = "untouched"
    evaluate_gate(state, workspace)
    return state


def validate_dimension_evidence(
    workspace: Path,
    dimension: str,
    score: int,
    summary: str,
    edge_cases: list[str],
    state: dict[str, Any] | None = None,
) -> str | None:
    """Return an error string if the requested score violates evidence rules, or None if valid."""
    clean_summary = summary.strip()
    if score > 0 and len(clean_summary) < 15:
        return f"Rejected: summary for '{dimension}' is too short ({len(clean_summary)} chars). Provide a real architectural explanation."

    if score == 20:
        if len(clean_summary) < MIN_SUMMARY_LEN_FOR_20:
            return (
                f"Rejected: score 20/20 on '{dimension}' requires a substantive summary "
                f"(>= {MIN_SUMMARY_LEN_FOR_20} chars; got {len(clean_summary)})."
            )
        if len(edge_cases) < MIN_EDGE_CASES_FOR_20:
            return (
                f"Rejected: score 20/20 on '{dimension}' requires at least {MIN_EDGE_CASES_FOR_20} "
                f"stress-tested edge cases (`--edge-case`); got {len(edge_cases)}."
            )

    if dimension == "memory" and score == 20:
        cur_state = state if state is not None else load_state(workspace)
        mem = cur_state.get("memory_architecture") or {}
        strat = (mem.get("strategy") or "").strip().lower()
        if not strat:
            return (
                "Rejected: score 20/20 on 'memory' requires `set-memory-arch` to be configured first."
            )
        if strat == "stateless":
            rat = (mem.get("rationale") or "").strip()
            if len(rat) < 15:
                return (
                    "Rejected: score 20/20 on 'memory' with `strategy: stateless` requires an explicit rationale "
                    "(`set-memory-arch --rationale ...`, >= 15 chars) explaining why persistent memory and agent communication do not apply."
                )
        else:
            if not (mem.get("agent_communication_pattern") or "").strip():
                return (
                    "Rejected: score 20/20 on 'memory' requires a non-empty agent/component communication pattern "
                    "(`set-memory-arch --communication ...`)."
                )
            if not (mem.get("failure_modes") or []):
                return (
                    "Rejected: score 20/20 on 'memory' requires at least 1 memory failure mode "
                    "(`set-memory-arch --failure-mode ...`)."
                )

    if dimension == "differentiation" and score > 0:
        prior_art = load_prior_art(workspace)
        if not prior_art:
            return (
                "Rejected: cannot score 'differentiation' > 0 before running `scout.py` "
                "(.preflight/prior-art.json does not exist)."
            )
        repos = (prior_art.get("active_incumbents") or []) + (prior_art.get("graveyard_repos") or [])
        if not repos:
            return (
                "Rejected: `.preflight/prior-art.json` contains 0 discovered repositories. "
                "Run `scout.py` with valid search queries first."
            )
        if score == 20:
            combined_text = (clean_summary + " " + " ".join(edge_cases)).lower()
            repo_names = [(r.get("full_name") or "").lower() for r in repos]
            if not any(cites_repo(combined_text, fn) for fn in repo_names if "/" in fn):
                sample_names = ", ".join(r.get("full_name", "") for r in repos[:4])
                return (
                    "Rejected: score 20/20 on 'differentiation' must explicitly cite at least one "
                    f"discovered repository from `.preflight/prior-art.json` (e.g., {sample_names})."
                )
    return None


def next_adr_number(adr_dir: Path) -> int:
    if not adr_dir.exists():
        return 1
    highest = 0
    for f in adr_dir.glob("*.md"):
        m = re.match(r"^(\d{4})-", f.name)
        if m:
            highest = max(highest, int(m.group(1)))
    return highest + 1


def record_adr(
    workspace: Path,
    title: str,
    decision: str,
    rejected: str = "",
    rationale: str = "",
    dimension: str = "",
    write_markdown: bool = True,
) -> dict[str, Any]:
    decisions = load_decisions(workspace)
    adr_dir = workspace / "docs" / "adr"
    adr_num = max(next_adr_number(adr_dir), len(decisions) + 1)
    slug = slugify(title)
    adr_filename = f"{adr_num:04d}-{slug}.md"
    adr_rel_path = f"docs/adr/{adr_filename}"
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if write_markdown:
        adr_dir.mkdir(parents=True, exist_ok=True)
        lines = [
            f"# ADR-{adr_num:04d}: {title}",
            "",
            "- **Status:** Accepted",
            f"- **Date:** {date_str}",
        ]
        if dimension:
            lines.append(f"- **Dimension:** `{dimension}`")
        lines.extend(
            [
                "",
                "## Decision",
                "",
                decision.strip(),
            ]
        )
        if rationale.strip():
            lines.extend(["", "## Context & Rationale", "", rationale.strip()])
        if rejected.strip():
            lines.extend(["", "## Considered & Rejected Alternatives", "", rejected.strip()])
        (adr_dir / adr_filename).write_text("\n".join(lines) + "\n", encoding="utf-8")

    entry = {
        "id": f"ADR-{adr_num:04d}",
        "number": adr_num,
        "title": title,
        "decision": decision,
        "rejected": rejected,
        "rationale": rationale,
        "dimension": dimension,
        "file": adr_rel_path if write_markdown else "",
        "created_at": now_iso(),
    }
    decisions.append(entry)
    save_decisions(workspace, decisions)
    return entry


def _tokenize_keywords(text: str) -> set[str]:
    stop = {
        "the", "and", "for", "with", "from", "into", "that", "this", "over", "under", "step",
        "implement", "build", "add", "create", "use", "using", "via", "per", "all", "only",
        "database", "sqlite", "python", "file", "system", "data", "code", "model", "test",
        "state", "step", "slice", "task", "tool", "work", "spec", "run", "runtime", "project",
        "architecture", "component", "will", "when", "then", "have", "each", "both", "must",
    }
    return {
        tok
        for tok in re.findall(r"[a-z0-9]{3,}", text.lower())
        if tok not in stop
    }


def build_ticket_acceptance_criteria(
    title: str,
    what_to_build: str,
    decisions: list[dict[str, Any]],
    critiques: list[dict[str, Any]],
    now_tools: list[dict[str, Any]],
    mem: dict[str, Any],
) -> list[str]:
    """
    Generate concrete, ticket-specific acceptance criteria derived from the ticket's deliverable,
    matching ADRs, matching red-team critiques, and matching Day-1 tools.
    Never blindly attaches fallback ADRs or critiques to unrelated vertical slices.
    """
    criteria: list[str] = []
    step_tokens = _tokenize_keywords(f"{title} {what_to_build}")

    # 1. Concrete deliverable clauses from what_to_build / title (never split inside parentheses)
    sub_clauses = [
        c.strip(" .;,")
        for c in re.split(r"(?:;|\band\b)(?![^(]*\))", what_to_build)
        if len(c.strip(" .;,")) >= 12
    ]
    if len(sub_clauses) >= 2:
        for clause in sub_clauses[:2]:
            criteria.append(f"- [ ] Deliverable verified: **{clause}**.")
    else:
        criteria.append(f"- [ ] Vertical slice implemented and verified: **{what_to_build.strip(' .')}**.")

    # 2. Match specific ADRs by substantive keyword overlap (>= 2 tokens or distinctive token >= 6 chars)
    # Never blindly fall back to decisions[0] when no substantive match exists.
    matched_adrs: list[tuple[int, dict[str, Any]]] = []
    for a in decisions:
        adr_tokens = _tokenize_keywords(f"{a.get('title', '')} {a.get('decision', '')} {a.get('dimension', '')}")
        overlap = step_tokens & adr_tokens
        if len(overlap) >= 2 or any(len(tok) >= 6 for tok in overlap):
            matched_adrs.append((len(overlap), a))
    matched_adrs.sort(key=lambda pair: pair[0], reverse=True)
    for _, a in matched_adrs[:2]:
        criteria.append(
            f"- [ ] Enforces **{a['id']} ({a['title']})**: {a['decision'].strip(' .')}."
        )

    # 3. Match specific Red-Team Critiques by substantive keyword overlap
    # Never blindly fall back to critiques[0] when no substantive match exists.
    matched_crits: list[tuple[int, dict[str, Any]]] = []
    for c in critiques:
        crit_tokens = _tokenize_keywords(f"{c.get('title', '')} {c.get('attack', '')} {c.get('mitigation', '')}")
        overlap = step_tokens & crit_tokens
        if len(overlap) >= 2 or any(len(tok) >= 6 for tok in overlap):
            matched_crits.append((len(overlap), c))
    matched_crits.sort(key=lambda pair: pair[0], reverse=True)
    for _, c in matched_crits[:2]:
        criteria.append(
            f"- [ ] Stress-tested against **[{c.get('severity', 'high').upper()}] {c.get('title')}**: {c.get('mitigation').strip(' .')}."
        )

    # 4. If memory failure modes relate to this slice, include matching guards
    mem_fms = mem.get("failure_modes") or []
    for fm in mem_fms:
        fm_tokens = _tokenize_keywords(fm)
        overlap = step_tokens & fm_tokens
        if len(overlap) >= 2 or any(len(tok) >= 6 for tok in overlap):
            criteria.append(f"- [ ] Verifies memory failure guard: {fm.strip(' .')}.")
            break

    matched_tools = [
        t for t in now_tools
        if len(step_tokens & _tokenize_keywords(f"{t.get('recommended', '')} {t.get('purpose', '')}")) >= 1
    ]
    if matched_tools:
        t0 = matched_tools[0]
        criteria.append(
            f"- [ ] Integrates Day-1 tool **{t0.get('recommended')}** (`{t0.get('config_proof') or t0.get('category')}`) for {t0.get('purpose').lower()}."
        )

    criteria.append(
        f"- [ ] Automated unit/integration tests for `{slugify(title, max_len=36)}` pass with zero regressions."
    )
    return criteria


def export_tickets_to_dir(
    workspace: Path,
    state: dict[str, Any],
    decisions: list[dict[str, Any]],
    issues_dir: Path | None = None,
    is_draft: bool | None = None,
) -> list[Path]:
    """
    Generate individual, ordered vertical-slice issue files under `.preflight/issues/NN-<slug>.md`
    (plus an `INDEX.md` ordered list) from the locked implementation steps, Stack Explained `NOW` tools,
    Memory Architecture, and Decision Ledger (ADRs).
    When `is_draft` is True (e.g. exported via `--force` while Readiness Gate is locked), every ticket
    and `INDEX.md` is explicitly watermarked as `DRAFT` with status `draft`.
    """
    target_dir = issues_dir or WorkspaceStore(workspace).issues_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    for old_f in target_dir.glob("*.md"):
        old_f.unlink()

    verdict = evaluate_gate(state, workspace)
    draft = verdict.is_draft if is_draft is None else is_draft
    status_label = ArtifactWatermarker.ticket_status(draft)
    title_prefix = "[DRAFT] " if draft else ""

    project_name = state.get("project_name") or "Untitled Project"
    sys_design = state.get("system_design") or {}
    raw_steps = list(sys_design.get("implementation_steps") or [])
    now_tools = [t for t in (state.get("tooling_recommendations") or []) if (t.get("stage") or "now") == "now"]
    mem = state.get("memory_architecture") or {}
    critiques = state.get("red_team_critiques") or []

    # If no explicit steps were passed, synthesize tracer-bullet slices from stack, memory, and dimensions
    if not raw_steps:
        raw_steps = [
            f"Bootstrap {project_name} Day-1 stack, lockfiles, and project skeleton",
            f"Implement core state & memory layer ({format_memory_strategy_display(mem)}) with failure-mode guards",
            f"Implement core domain workflow and prior-art differentiation features for {project_name}",
            "Add adversarial stress tests, rate-limit/bottleneck mitigations, and end-to-end verification",
        ]

    created_files: list[Path] = []
    prev_ticket_ref = "None (can start immediately)"
    index_lines = [
        f"# {title_prefix}Ordered Implementation Tickets: {project_name}",
        "",
    ]
    if draft:
        index_lines.extend(
            [
                "> ⚠️ **DRAFT TICKETS — READINESS GATE LOCKED:** These tickets were exported with `--force` before the PreFlight Readiness Gate passed. Complete architecture validation before coding.",
                "",
            ]
        )
    index_lines.extend(
        [
            "Work these tickets in order (one vertical slice per session/commit). Use `Title :: Details :: BlockedBy` in `set-design --step` to declare custom or parallel dependency edges:",
            "",
            "| # | Ticket File | Title | Blocked By | Status |",
            "| :---: | :--- | :--- | :--- | :---: |",
        ]
    )

    for idx, raw_step in enumerate(raw_steps, start=1):
        clean_step = strip_step_prefix(raw_step)
        # Allow optional "Title :: Details :: BlockedBy" syntax or plain text
        if "::" in clean_step:
            parts = [p.strip() for p in clean_step.split("::")]
            title = parts[0]
            what_to_build = parts[1] if len(parts) > 1 and parts[1] else parts[0]
            raw_blocked = parts[2] if len(parts) > 2 and parts[2] else ""
            if raw_blocked.lower() in ("none", "independent", "root"):
                blocked_by = "None (Independent slice)" if idx > 1 else "None (can start immediately)"
            elif raw_blocked:
                blocked_by = raw_blocked
            else:
                blocked_by = prev_ticket_ref if idx > 1 else "None (can start immediately)"
        else:
            title = clean_step
            what_to_build = clean_step
            if idx == 1:
                blocked_by = "None (can start immediately)"
            else:
                blocked_by = prev_ticket_ref

        slug = slugify(title)
        filename = f"{idx:02d}-{slug}.md"
        file_path = target_dir / filename
        ticket_id = f"{title_prefix}{idx:02d}: {title}"

        adr_refs = [f"- **{a['id']} ({a['title']})**: {a['decision']}" for a in decisions]
        tool_refs = [
            f"- **{t.get('recommended')}** (`{t.get('config_proof') or t.get('category')}` — `{t.get('proof_status', 'claimed-unverified')}`): {t.get('purpose')} — _{t.get('why')}_"
            for t in now_tools
        ]
        crit_refs = [
            f"- **[{c.get('severity', 'high').upper()}] {c.get('title')}**: {c.get('mitigation')}"
            for c in critiques
        ]

        ticket_lines = [
            f"# {ticket_id}",
            "",
        ]
        ticket_lines.extend(ArtifactWatermarker.ticket_banner_markdown(draft))
        ticket_lines.extend(
            [
                f"**What to build:** {what_to_build}",
                "",
                f"**Blocked by:** {blocked_by}",
                "",
                f"**Status:** {status_label}",
                "",
                "## Locked Architecture & Stack Constraints",
                "",
                "- **Spec Reference:** `.preflight/SPEC.md` & `.preflight/STACK.md`",
            ]
        )
        if mem.get("strategy"):
            ticket_lines.append(
                f"- **Memory & Agent Communication (`{format_memory_strategy_display(mem)}`):** {mem.get('agent_communication_pattern') or '—'}"
            )
        if tool_refs:
            ticket_lines.extend(["", "### Day-1 Stack (`NOW` Tools to Use)", *tool_refs])
        if adr_refs:
            ticket_lines.extend(["", "### Locked ADRs to Respect", *adr_refs])
        if crit_refs:
            ticket_lines.extend(["", "### Red-Team Mitigations to Enforce", *crit_refs])

        specific_criteria = build_ticket_acceptance_criteria(
            title=title,
            what_to_build=what_to_build,
            decisions=decisions,
            critiques=critiques,
            now_tools=now_tools,
            mem=mem,
        )
        ticket_lines.extend(
            [
                "",
                "## Acceptance Criteria",
                "",
                *specific_criteria,
                "",
            ]
        )

        file_path.write_text("\n".join(ticket_lines), encoding="utf-8")
        created_files.append(file_path)
        index_lines.append(
            f"| `{idx:02d}` | [{filename}](./{filename}) | {title_prefix}{title} | {blocked_by} | `{status_label}` |"
        )
        prev_ticket_ref = f"`{idx:02d}` ({filename})"

    index_path = target_dir / "INDEX.md"
    index_path.write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    return created_files


class CommandRunner:
    """Standard-library command execution wrapper for subprocess commands."""

    def run(
        self,
        cmd: list[str],
        check: bool = False,
        text: bool = True,
        capture_output: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(cmd, check=check, text=text, capture_output=capture_output)


def build_github_issue_references_header(repo: str, branch: str = "main") -> str:
    """
    Format standard PreFlight architecture references linking to SPEC.md, STACK.md,
    docs/adr/, and GLOSSARY.md in the target GitHub repository.
    """
    clean_repo = repo.strip().strip("/")
    clean_branch = branch.strip() or "main"
    base_blob = f"https://github.com/{clean_repo}/blob/{clean_branch}"
    return (
        f"> 🔗 **PreFlight Architecture References:**\n"
        f"> - **Specification:** [{clean_repo}/.preflight/SPEC.md]({base_blob}/.preflight/SPEC.md)\n"
        f"> - **Stack Explained:** [{clean_repo}/.preflight/STACK.md]({base_blob}/.preflight/STACK.md)\n"
        f"> - **Decision Ledger (ADRs):** [{clean_repo}/docs/adr/]({base_blob}/docs/adr/)\n"
        f"> - **Domain Glossary:** [{clean_repo}/GLOSSARY.md]({base_blob}/GLOSSARY.md)\n"
        f"\n"
        f"---"
    )


def resolve_blocked_by_in_ticket(body_text: str, created_map: dict[int, int]) -> str:
    """
    Replace ticket index references in `**Blocked by:** ...` with live `#<issue_num>`.
    Example: `**Blocked by:** `01` (01-foo.md)` -> `**Blocked by:** #1 (01-foo.md)`.
    """
    if not created_map:
        return body_text

    updated_lines: list[str] = []
    for line in body_text.splitlines():
        if line.startswith("**Blocked by:**"):
            prefix, sep, rest = line.partition(":")
            for t_idx, issue_num in sorted(created_map.items(), reverse=True):
                rest = re.sub(rf"`0?{t_idx}`", f"#{issue_num}", rest)
                rest = re.sub(rf"\b0?{t_idx}\b(?![-\w]*\.md)", f"#{issue_num}", rest)
            updated_lines.append(f"{prefix}:{rest}")
        else:
            updated_lines.append(line)
    return "\n".join(updated_lines)


def export_tickets_to_github(
    workspace: Path,
    repo: str,
    branch: str = "main",
    issues_dir: Path | None = None,
    force: bool = False,
    dry_run: bool = False,
    labels: list[str] | None = None,
    runner: Any | None = None,
) -> dict[str, Any]:
    """
    Export all ordered PreFlight vertical-slice implementation tickets directly to GitHub Issues.
    - Prepend clickable links to SPEC.md, STACK.md, docs/adr/, and GLOSSARY.md.
    - Applies labels `ready-for-agent` and `needs-triage`.
    - Creates issues sequentially (01 to NN) and resolves `Blocked by` issue numbers dynamically.
    - Returns structured summary and updates local INDEX.md with live GitHub issue links.
    """
    clean_repo = repo.strip().strip("/")
    if not clean_repo or "/" not in clean_repo:
        raise ValueError(
            f"Invalid GitHub repository '{repo}'. Expected format: 'owner/repo' (e.g. 'thilak15/ClawBridge')."
        )

    cmd_runner = runner or CommandRunner()
    workspace = Path(workspace).resolve()
    store = WorkspaceStore(workspace)
    state = store.load_state()

    verdict = evaluate_gate(state, workspace)
    if not verdict.unlocked and not force:
        raise PermissionError(
            f"Readiness Gate is LOCKED ({verdict.score}% / 80% required). Pass `--force` to export draft issues anyway.\n"
            + "\n".join(f"  - {m}" for m in verdict.missing)
        )
    is_draft = not verdict.unlocked

    if not dry_run:
        if runner is None and not shutil.which("gh"):
            raise RuntimeError(
                "GitHub CLI (`gh`) is not installed or not found in PATH. Install `gh` to export GitHub issues."
            )
        auth_check = cmd_runner.run(["gh", "auth", "token"])
        if auth_check.returncode != 0:
            raise RuntimeError(
                "GitHub CLI (`gh`) is not authenticated. Run `gh auth login` before exporting GitHub issues."
            )

    target_dir = issues_dir or store.issues_dir
    existing_tickets = (
        sorted([f for f in target_dir.glob("*.md") if f.name != "INDEX.md"])
        if target_dir.exists()
        else []
    )
    if not existing_tickets:
        decisions = store.load_decisions()
        existing_tickets = export_tickets_to_dir(workspace, state, decisions, issues_dir=target_dir, is_draft=is_draft)

    active_labels = labels or ["ready-for-agent", "needs-triage"]
    label_meta = {
        "ready-for-agent": ("0E8A16", "Ready for agent implementation"),
        "needs-triage": ("FBCA04", "Needs triage before starting"),
    }
    if not dry_run:
        for lbl in active_labels:
            color, desc = label_meta.get(lbl, ("0E8A16", "PreFlight label"))
            cmd_runner.run(
                ["gh", "label", "create", lbl, "--repo", clean_repo, "--color", color, "--description", desc, "--force"]
            )

    ref_header = build_github_issue_references_header(clean_repo, branch=branch)
    created_map: dict[int, int] = {}
    created_issues: list[dict[str, Any]] = []

    for f in existing_tickets:
        raw_text = f.read_text(encoding="utf-8")
        lines = raw_text.splitlines()
        first_line = lines[0] if lines else f.stem
        issue_title = re.sub(r"^#+\s*", "", first_line).strip()

        m = re.match(r"^(\d+)", f.stem)
        ticket_idx = int(m.group(1)) if m else len(created_issues) + 1

        resolved_content = resolve_blocked_by_in_ticket(raw_text, created_map)
        full_body = f"{ref_header}\n\n{resolved_content}"

        if dry_run:
            simulated_issue_num = ticket_idx
            simulated_url = f"https://github.com/{clean_repo}/issues/{simulated_issue_num}"
            issue_num = simulated_issue_num
            issue_url = simulated_url
        else:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".md") as tmp:
                tmp.write(full_body)
                tmp_path = Path(tmp.name)
            try:
                cmd = [
                    "gh",
                    "issue",
                    "create",
                    "--repo",
                    clean_repo,
                    "--title",
                    issue_title,
                    "--body-file",
                    str(tmp_path),
                ]
                for lbl in active_labels:
                    cmd.extend(["--label", lbl])
                proc = cmd_runner.run(cmd)
                if proc.returncode != 0:
                    raise RuntimeError(
                        f"Failed creating GitHub issue for '{issue_title}' on {clean_repo}: {proc.stderr or proc.stdout}"
                    )
                issue_url = proc.stdout.strip()
                match = re.search(r"/issues/(\d+)$", issue_url)
                if match:
                    issue_num = int(match.group(1))
                else:
                    issue_num = ticket_idx
            finally:
                tmp_path.unlink(missing_ok=True)

        created_map[ticket_idx] = issue_num
        created_issues.append(
            {
                "index": ticket_idx,
                "title": issue_title,
                "number": issue_num,
                "url": issue_url,
                "file": f.name,
                "body": full_body,
            }
        )

    index_file = target_dir / "INDEX.md"
    if index_file.exists():
        index_content = index_file.read_text(encoding="utf-8")
        for item in created_issues:
            t_idx = item["index"]
            num = item["number"]
            url = item["url"]
            index_content = re.sub(
                rf"(\|\s*`{t_idx:02d}`\s*\|\s*)(\[[^\]]+\]\(\./[^)]+\))",
                rf"\1[#{num}]({url})",
                index_content,
            )
        index_file.write_text(index_content, encoding="utf-8")

    return {
        "repo": clean_repo,
        "branch": branch,
        "total": len(created_issues),
        "issues": created_issues,
        "is_draft": is_draft,
    }


def format_github_issues_summary(result: dict[str, Any]) -> str:
    lines = [
        f"Exported {result['total']} issue(s) to GitHub repository '{result['repo']}' (branch: {result['branch']}):",
    ]
    for issue in result["issues"]:
        lines.append(f"  - Issue #{issue['number']}: {issue['title']} ({issue['url']})")

    if result["issues"]:
        first_issue = result["issues"][0]
        lines.extend(
            [
                "",
                "=" * 80,
                f"Issue #{first_issue['number']} Details (Verify Acceptance Criteria & References):",
                "=" * 80,
                first_issue["body"],
                "=" * 80,
            ]
        )
    return "\n".join(lines)


def format_scorecard(state: dict[str, Any], workspace: Path | None = None) -> str:
    total, unlocked, missing = evaluate_gate(state, workspace)
    gate_str = "UNLOCKED (Ready for Blueprint)" if unlocked else "LOCKED"
    tools_count = len(state.get("tooling_recommendations") or [])
    mem_strat = (state.get("memory_architecture") or {}).get("strategy") or "unset"
    lines = [
        f"# PreFlight Readiness Scorecard: {state.get('project_name', 'Untitled')}",
        f"**Overall Readiness:** {total}% — **{gate_str}** | **Tooling Entries:** {tools_count} | **Memory Strategy:** `{mem_strat}`",
        "",
        "| Dimension | Score | Status | Edge Cases | Summary |",
        "| :--- | :---: | :---: | :---: | :--- |",
    ]
    for dim in DIMENSIONS:
        d = state["dimensions"][dim]
        summary = (d.get("summary") or "—").replace("\n", " ")
        ec_count = len(d.get("edge_cases") or [])
        lines.append(
            f"| **{d['label']}** (`{dim}`) | {d['score']}/20 | `{d['status']}` | {ec_count} | {summary} |"
        )
    if missing:
        lines.append("")
        lines.append("## Remaining Gate Requirements")
        for m in missing:
            lines.append(f"- 🔒 {m}")
    return "\n".join(lines)


class PreFlightOps:
    """
    Testable domain operations for PreFlight working state and architecture ledger.
    Leaves CLI adapters thin and provides clean programmatic interfaces for tests.
    Can be called as static methods or instantiated with a `WorkspaceStore` or workspace `Path`.
    """

    def __init__(self, workspace_or_store: Path | WorkspaceStore | str = ".") -> None:
        if isinstance(workspace_or_store, WorkspaceStore):
            self.store = workspace_or_store
            self.workspace = self.store.workspace
        else:
            self.workspace = Path(workspace_or_store).resolve()
            self.store = WorkspaceStore(self.workspace)

    def get_scorecard(self) -> GateVerdict:
        return evaluate_gate(self.store.load_state(), self.workspace)

    @classmethod
    def _resolve_workspace(cls, target: Any) -> tuple[Path, WorkspaceStore]:
        if isinstance(target, PreFlightOps):
            return target.workspace, target.store
        if isinstance(target, WorkspaceStore):
            return target.workspace, target
        p = Path(target).resolve()
        return p, WorkspaceStore(p)

    def init_project(
        workspace: Any,
        name: str,
        summary: str = "",
        runtime: str = "",
        stack: str = "",
        reset: bool = False,
        purge_cache: bool = False,
        keep_adrs: bool = False,
    ) -> tuple[dict[str, Any], GateVerdict, list[str]]:
        workspace_path, store = PreFlightOps._resolve_workspace(workspace)
        removed: list[str] = []
        if reset:
            removed = store.reset(purge_cache=purge_cache, clear_adrs=not keep_adrs)
            state = default_state(name=name, summary=summary)
        else:
            if store.state_path.exists():
                existing = store.load_state()
                old_name = (existing.get("project_name") or "").strip()
                if old_name and old_name != "Untitled Project" and old_name.lower() != name.strip().lower():
                    print(
                        f"NOTE: Existing state found for '{old_name}'. Use `init --reset` or `state.py reset` "
                        "to wipe previous scores and decisions when starting a new idea.",
                        file=sys.stderr,
                    )
                state = existing
            else:
                state = default_state(name=name, summary=summary)

        state["project_name"] = name
        if summary:
            state["project_summary"] = summary
        if runtime:
            state["target_runtime"] = runtime
        if stack:
            state["tech_stack"] = [s.strip() for s in stack.split(",") if s.strip()]

        store.save_state(state)
        verdict = evaluate_gate(state, workspace_path)
        return state, verdict, removed

    def update_dimension(
        workspace: Any,
        dimension: str,
        score: int,
        summary: str,
        edge_cases: list[str],
    ) -> tuple[dict[str, Any], GateVerdict]:
        workspace_path, store = PreFlightOps._resolve_workspace(workspace)
        state = store.load_state()
        d = state["dimensions"][dimension]
        existing_ecs = list(d.get("edge_cases") or [])
        for ec in edge_cases:
            if ec.strip() and ec.strip() not in existing_ecs:
                existing_ecs.append(ec.strip())

        err = validate_dimension_evidence(
            workspace=workspace_path,
            dimension=dimension,
            score=score,
            summary=summary,
            edge_cases=existing_ecs,
            state=state,
        )
        if err:
            raise ValueError(err)

        d["score"] = score
        d["summary"] = summary.strip()
        d["edge_cases"] = existing_ecs
        store.save_state(state)
        verdict = evaluate_gate(state, workspace_path)
        return state, verdict

    def add_tool(
        workspace: Any,
        category: str,
        purpose: str,
        recommended: str,
        why: str,
        alternatives: str,
        stage: str = "now",
        config_proof: str = "",
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        workspace_path, store = PreFlightOps._resolve_workspace(workspace)
        state = store.load_state()
        tools = state.setdefault("tooling_recommendations", [])
        proof_status, proof_source = verify_config_proof(
            workspace=workspace_path,
            config_proof=config_proof,
            recommended=recommended,
        )
        entry = {
            "category": category,
            "purpose": purpose.strip(),
            "recommended": recommended.strip(),
            "why": why.strip(),
            "alternatives": alternatives.strip(),
            "stage": stage,
            "config_proof": config_proof.strip(),
            "proof_status": proof_status,
            "proof_source": proof_source,
        }
        replaced = False
        for idx, existing in enumerate(tools):
            if (
                existing.get("category") == entry["category"]
                and existing.get("purpose", "").lower() == entry["purpose"].lower()
            ):
                tools[idx] = entry
                replaced = True
                break
        if not replaced:
            tools.append(entry)

        store.save_state(state)
        return state, entry

    def set_memory_architecture(
        workspace: Any,
        strategy: str,
        communication: str = "",
        rationale: str = "",
        alternatives: str = "",
        failure_modes: list[str] | None = None,
        secondary_strategies: list[str] | None = None,
        workflow: str = "",
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        workspace_path, store = PreFlightOps._resolve_workspace(workspace)
        state = store.load_state()
        mem = state.setdefault("memory_architecture", {})
        existing_fms = list(mem.get("failure_modes") or [])
        for fm in failure_modes or []:
            if fm.strip() and fm.strip() not in existing_fms:
                existing_fms.append(fm.strip())
        is_stateless = (strategy or "").strip().lower() == "stateless"
        if is_stateless:
            if len(rationale.strip()) < 15:
                raise ValueError(
                    "`strategy: stateless` requires an explicit `--rationale` (>= 15 chars) "
                    "explaining why agent communication and memory failure modes do not apply."
                )
            if not communication.strip():
                communication = "Stateless (single-process / request-scoped; no persistent agent communication)"
        else:
            if not existing_fms:
                raise ValueError(
                    "`set-memory-arch` requires at least 1 `--failure-mode` describing an anticipated memory failure and mitigation."
                )

        existing_secs = list(mem.get("secondary_strategies") or [])
        for sec in secondary_strategies or []:
            if sec.strip() and sec.strip() != strategy and sec.strip() not in existing_secs:
                existing_secs.append(sec.strip())

        mem["strategy"] = strategy
        mem["secondary_strategies"] = existing_secs
        mem["agent_communication_pattern"] = communication.strip()
        if workflow:
            mem["workflow_memory_flow"] = workflow.strip()
        mem["rationale"] = rationale.strip()
        if alternatives:
            mem["alternatives_considered"] = alternatives.strip()
        mem["failure_modes"] = existing_fms
        store.save_state(state)
        return state, mem

    def add_critique(
        workspace: Any,
        title: str,
        severity: str,
        attack: str,
        mitigation: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        workspace_path, store = PreFlightOps._resolve_workspace(workspace)
        state = store.load_state()
        entry = {
            "title": title.strip(),
            "severity": severity.strip(),
            "attack": attack.strip(),
            "mitigation": mitigation.strip(),
        }
        state.setdefault("red_team_critiques", []).append(entry)
        store.save_state(state)
        return state, entry

    def add_decision(
        workspace: Any,
        title: str,
        decision: str,
        rejected: str = "",
        rationale: str = "",
        dimension: str = "",
        write_markdown: bool = True,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        workspace_path, store = PreFlightOps._resolve_workspace(workspace)
        entry = record_adr(
            workspace=workspace_path,
            title=title,
            decision=decision,
            rejected=rejected,
            rationale=rationale,
            dimension=dimension,
            write_markdown=write_markdown,
        )
        state = store.load_state()
        store.save_state(state)
        return state, entry

    def set_system_design(
        workspace: Any,
        topology: str = "",
        topology_file: str = "",
        sequence: str = "",
        sequence_file: str = "",
        options: list[str] | None = None,
        steps: list[str] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        workspace_path, store = PreFlightOps._resolve_workspace(workspace)
        state = store.load_state()
        sys_design = state.setdefault(
            "system_design",
            {
                "topology_mermaid": "",
                "sequence_mermaid": "",
                "options_matrix": [],
                "implementation_steps": [],
            },
        )
        if topology_file:
            sys_design["topology_mermaid"] = Path(topology_file).read_text(encoding="utf-8").strip()
        elif topology:
            sys_design["topology_mermaid"] = topology.strip()

        if sequence_file:
            sys_design["sequence_mermaid"] = Path(sequence_file).read_text(encoding="utf-8").strip()
        elif sequence:
            sys_design["sequence_mermaid"] = sequence.strip()

        if options:
            parsed_options = []
            for raw_opt in options:
                parts = [p.strip() for p in raw_opt.split("|")]
                if len(parts) != 4:
                    raise ValueError(
                        f"--option must have 4 pipe-separated fields 'Option|Pros|Cons|Verdict'; got: {raw_opt}"
                    )
                parsed_options.append(
                    {
                        "option": parts[0],
                        "pros": parts[1],
                        "cons": parts[2],
                        "verdict": parts[3],
                    }
                )
            sys_design["options_matrix"] = parsed_options

        if steps:
            sys_design["implementation_steps"] = [s.strip() for s in steps if s.strip()]

        store.save_state(state)
        return state, sys_design

    @classmethod
    def export_tickets(
        cls,
        workspace: Any,
        issues_dir: Path | None = None,
        force: bool = False,
    ) -> tuple[dict[str, Any], list[Path], bool]:
        workspace_path, store = cls._resolve_workspace(workspace)
        state = store.load_state()
        verdict = evaluate_gate(state, workspace_path)
        if not verdict.unlocked and not force:
            raise PermissionError(
                f"Readiness Gate is LOCKED ({verdict.score}% / 80% required). Pass `--force` to export draft tickets anyway.\n"
                + "\n".join(f"  - {m}" for m in verdict.missing)
            )
        is_draft = not verdict.unlocked
        decisions = store.load_decisions()
        out_dir = issues_dir or store.issues_dir
        created = export_tickets_to_dir(workspace_path, state, decisions, issues_dir=out_dir, is_draft=is_draft)
        return state, created, is_draft

    @classmethod
    def export_github_issues(
        cls,
        workspace: Any,
        repo: str,
        branch: str = "main",
        issues_dir: Path | None = None,
        force: bool = False,
        dry_run: bool = False,
        labels: list[str] | None = None,
        runner: Any | None = None,
    ) -> dict[str, Any]:
        workspace_path, _ = cls._resolve_workspace(workspace)
        return export_tickets_to_github(
            workspace=workspace_path,
            repo=repo,
            branch=branch,
            issues_dir=issues_dir,
            force=force,
            dry_run=dry_run,
            labels=labels,
            runner=runner,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PreFlight state, tooling, memory & decision ledger manager")
    parser.add_argument("--workspace", default=".", help="Workspace root directory")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="Initialize or update project metadata (use --reset for a clean slate)")
    p_init.add_argument("--name", required=True, help="Project name")
    p_init.add_argument("--summary", default="", help="Project summary")
    p_init.add_argument("--runtime", default="", help="Target runtime")
    p_init.add_argument("--stack", default="", help="Comma-separated tech stack items")
    p_init.add_argument(
        "--reset",
        action="store_true",
        help="Wipe existing scores, state, decisions, prior-art, and blueprints before initializing",
    )
    p_init.add_argument(
        "--purge-cache",
        action="store_true",
        help="When used with --reset, also delete .preflight/cache.db",
    )
    p_init.add_argument(
        "--keep-adrs",
        action="store_true",
        help="When used with --reset, keep ADR markdown files recorded in .preflight/decisions.json on disk",
    )

    p_reset = sub.add_parser(
        "reset",
        help="Clear all pre-performed scores, states, decisions, and prior-art so you can run a fresh idea",
    )
    p_reset.add_argument(
        "--purge-cache",
        action="store_true",
        help="Also delete the SQLite GitHub cache (.preflight/cache.db)",
    )
    p_reset.add_argument(
        "--keep-adrs",
        action="store_true",
        help="Keep ADR markdown files recorded in .preflight/decisions.json on disk (pre-existing ADRs are always preserved)",
    )

    p_score = sub.add_parser("update-dimension", help="Update a dimension score & notes (enforces evidence rules)")
    p_score.add_argument("--dimension", choices=DIMENSIONS, required=True)
    p_score.add_argument("--score", type=int, choices=[0, 10, 20], required=True)
    p_score.add_argument("--summary", required=True, help="Substantive summary of locked understanding")
    p_score.add_argument("--edge-case", action="append", default=[], help="Stress-tested edge case (>=2 required for score 20)")

    p_tool = sub.add_parser(
        "add-tool",
        help="Record a 'Stack Explained' entry: what job it does, why needed, the alternative, 'now' vs 'later', and config proof",
    )
    p_tool.add_argument(
        "--category",
        choices=TOOL_CATEGORIES,
        default="core-oss",
        help="Tool category (e.g. dependency-lock, container-runtime, orchestration-deploy, ci-cd-quality, core-oss)",
    )
    p_tool.add_argument("--purpose", required=True, help="What job this tool does")
    p_tool.add_argument("--recommended", required=True, help="Tool name (e.g. uv / uv.lock, Docker, GitHub Actions, pre-commit)")
    p_tool.add_argument("--why", required=True, help="Why this project needs it now (or why deferred to later)")
    p_tool.add_argument("--alternatives", required=True, help="What the alternative was and why it wasn't chosen")
    p_tool.add_argument(
        "--stage",
        choices=["now", "later"],
        default="now",
        help="Whether this tool is needed 'now' (Day 1 / V1) or 'later' (deferred until scale/trigger)",
    )
    p_tool.add_argument(
        "--config-proof",
        default="",
        help="Config file proving usage in prior art or this project (e.g. 'pyproject.toml ([tool.uv])', 'Dockerfile', '.github/workflows', '.pre-commit-config.yaml')",
    )

    p_mem = sub.add_parser(
        "set-memory-arch",
        help="Configure agent communication pattern, primary + secondary memory strategies (stateless, SQLite, FTS, RAG, Vector DB), and memory failure modes",
    )
    p_mem.add_argument(
        "--strategy",
        choices=MEMORY_STRATEGIES,
        required=True,
        help="Primary memory architecture (stateless, transactional-db, lexical-fts, rag-vector-db, hybrid-search, episodic-agent-state)",
    )
    p_mem.add_argument(
        "--secondary-strategy",
        action="append",
        choices=MEMORY_STRATEGIES,
        default=[],
        help="Optional secondary/combined memory strategy (can be passed multiple times, e.g. transactional-db + lexical-fts + episodic-agent-state)",
    )
    p_mem.add_argument(
        "--communication",
        required=True,
        help="How agents or components communicate & pass context/state across workflow steps",
    )
    p_mem.add_argument(
        "--workflow",
        default="",
        help="How memory is read/written/invalidated during the execution workflow",
    )
    p_mem.add_argument(
        "--rationale",
        required=True,
        help="Why this memory model fits better than alternatives (e.g., why SQLite FTS over Vector DB, or why RAG is needed)",
    )
    p_mem.add_argument(
        "--alternatives",
        default="",
        help="Other memory architectures considered (e.g., RAG, Vector DB, Redis, plain files) and why rejected",
    )
    p_mem.add_argument(
        "--failure-mode",
        action="append",
        default=[],
        help="Specific memory failure mode we might face and its mitigation (can be passed multiple times; >= 1 required)",
    )

    p_crit = sub.add_parser("add-critique", help="Add an adversarial red-team critique finding")
    p_crit.add_argument("--title", required=True)
    p_crit.add_argument("--severity", choices=["critical", "high", "medium"], default="high")
    p_crit.add_argument("--attack", required=True, help="How this architectural assumption fails under stress")
    p_crit.add_argument("--mitigation", required=True, help="How the design resolves or mitigates it")

    p_adr = sub.add_parser("add-decision", help="Append an architectural decision (and write docs/adr/NNNN.md)")
    p_adr.add_argument("--title", required=True)
    p_adr.add_argument("--decision", required=True)
    p_adr.add_argument("--rejected", default="")
    p_adr.add_argument("--rationale", default="")
    p_adr.add_argument("--dimension", choices=list(DIMENSIONS) + [""], default="")
    p_adr.add_argument("--no-markdown", action="store_true", help="Skip writing docs/adr/NNNN.md")

    p_design = sub.add_parser("set-design", help="Set Mermaid diagrams, trade-off options, and implementation steps")
    p_design.add_argument("--topology", default="", help="Mermaid flowchart string for system topology")
    p_design.add_argument("--topology-file", default="", help="Path to file containing Mermaid topology diagram")
    p_design.add_argument("--sequence", default="", help="Mermaid sequenceDiagram string")
    p_design.add_argument("--sequence-file", default="", help="Path to file containing Mermaid sequence diagram")
    p_design.add_argument(
        "--option",
        action="append",
        default=[],
        help="Trade-off option formatted as 'Option Name|Pros|Cons|Verdict'",
    )
    p_design.add_argument(
        "--step",
        action="append",
        default=[],
        help="Ordered implementation step (can be passed multiple times)",
    )

    p_status = sub.add_parser("status", help="Print current Readiness Scorecard")
    p_status.add_argument("--json", action="store_true")

    p_tickets = sub.add_parser(
        "export-tickets",
        help="Generate individual, dependency-ordered issue files (.preflight/issues/NN-<slug>.md) ready to code one-by-one",
    )
    p_tickets.add_argument(
        "--output-dir",
        default="",
        help="Optional custom directory for ticket files (defaults to .preflight/issues)",
    )
    p_tickets.add_argument(
        "--force",
        action="store_true",
        help="Export tickets even if Readiness Gate is <80%%",
    )

    p_gh_issues = sub.add_parser(
        "export-github-issues",
        help="Export all ordered implementation tickets to GitHub Issues via gh CLI",
    )
    p_gh_issues.add_argument(
        "--repo",
        required=True,
        help="GitHub repository in 'owner/repo' format (e.g. thilak15/ClawBridge)",
    )
    p_gh_issues.add_argument(
        "--branch",
        default="main",
        help="GitHub branch to link for architecture documents (defaults to main)",
    )
    p_gh_issues.add_argument(
        "--output-dir",
        default="",
        help="Custom directory for local ticket files (defaults to .preflight/issues)",
    )
    p_gh_issues.add_argument(
        "--force",
        action="store_true",
        help="Export draft issues even if Readiness Gate is <80%%",
    )
    p_gh_issues.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate issue creation without calling GitHub API",
    )

    args = parser.parse_args(argv)
    workspace = Path(args.workspace).resolve()

    if args.cmd == "reset":
        removed = WorkspaceStore(workspace).reset(
            purge_cache=args.purge_cache,
            clear_adrs=not args.keep_adrs,
        )
        if removed:
            print(f"Reset complete. Removed {len(removed)} file(s): {', '.join(removed)}")
        else:
            print("Reset complete. Workspace was already clean.")
        return 0

    if args.cmd == "init":
        state, _, _ = PreFlightOps.init_project(
            workspace=workspace,
            name=args.name,
            summary=args.summary,
            runtime=args.runtime,
            stack=args.stack,
            reset=args.reset,
            purge_cache=args.purge_cache,
            keep_adrs=args.keep_adrs,
        )
        print(format_scorecard(state, workspace))
        return 0

    if args.cmd == "update-dimension":
        try:
            state, _ = PreFlightOps.update_dimension(
                workspace=workspace,
                dimension=args.dimension,
                score=args.score,
                summary=args.summary,
                edge_cases=args.edge_case,
            )
        except ValueError as err:
            print(f"ERROR: {err}", file=sys.stderr)
            return 2
        print(format_scorecard(state, workspace))
        return 0

    if args.cmd == "add-tool":
        state, entry = PreFlightOps.add_tool(
            workspace=workspace,
            category=args.category,
            purpose=args.purpose,
            recommended=args.recommended,
            why=args.why,
            alternatives=args.alternatives,
            stage=args.stage,
            config_proof=args.config_proof,
        )
        if entry["proof_status"] != "verified" and args.config_proof.strip():
            print(
                f"WARNING: Config proof '{args.config_proof.strip()}' for '{args.recommended.strip()}' was not found "
                "in `.preflight/prior-art.json` (`observed_stack_configs`) or workspace files; marked as `claimed-unverified`.",
                file=sys.stderr,
            )
        print(
            f"Recorded Stack Explained [{entry['stage'].upper()}] [{entry['category']}] ({entry['proof_status']}): "
            f"{entry['recommended']} ({entry['purpose']})"
        )
        return 0

    if args.cmd == "set-memory-arch":
        try:
            state, mem = PreFlightOps.set_memory_architecture(
                workspace=workspace,
                strategy=args.strategy,
                communication=args.communication,
                rationale=args.rationale,
                alternatives=args.alternatives,
                failure_modes=args.failure_mode,
                secondary_strategies=args.secondary_strategy,
                workflow=args.workflow,
            )
        except ValueError as err:
            print(f"ERROR: {err}", file=sys.stderr)
            return 2
        print(
            f"Updated memory_architecture: strategy={format_memory_strategy_display(mem)} "
            f"({len(mem.get('failure_modes', []))} failure modes tracked)"
        )
        return 0

    if args.cmd == "add-critique":
        state, entry = PreFlightOps.add_critique(
            workspace=workspace,
            title=args.title,
            severity=args.severity,
            attack=args.attack,
            mitigation=args.mitigation,
        )
        print(f"Added critique: {entry['title']} ({entry['severity']})")
        return 0

    if args.cmd == "add-decision":
        state, entry = PreFlightOps.add_decision(
            workspace=workspace,
            title=args.title,
            decision=args.decision,
            rejected=args.rejected,
            rationale=args.rationale,
            dimension=args.dimension,
            write_markdown=not args.no_markdown,
        )
        print(json.dumps(entry, indent=2))
        return 0

    if args.cmd == "set-design":
        try:
            state, _ = PreFlightOps.set_system_design(
                workspace=workspace,
                topology=args.topology,
                topology_file=args.topology_file,
                sequence=args.sequence,
                sequence_file=args.sequence_file,
                options=args.option,
                steps=args.step,
            )
        except ValueError as err:
            print(f"ERROR: {err}", file=sys.stderr)
            return 2
        print("Updated system_design in .preflight/state.json")
        return 0

    if args.cmd == "status":
        state = WorkspaceStore(workspace).load_state()
        if args.json:
            print(json.dumps(state, indent=2))
        else:
            print(format_scorecard(state, workspace))
        return 0

    if args.cmd == "export-tickets":
        state = WorkspaceStore(workspace).load_state()
        verdict = evaluate_gate(state, workspace)
        if not verdict.unlocked and not args.force:
            print(
                f"ERROR: Readiness Gate is LOCKED ({verdict.score}% / 80% required). Pass `--force` to export draft tickets anyway.\n"
                + "\n".join(f"  - {m}" for m in verdict.missing),
                file=sys.stderr,
            )
            return 2
        is_draft = not verdict.unlocked
        decisions = WorkspaceStore(workspace).load_decisions()
        out_dir = Path(args.output_dir).resolve() if args.output_dir else WorkspaceStore(workspace).issues_dir
        created = export_tickets_to_dir(workspace, state, decisions, issues_dir=out_dir, is_draft=is_draft)
        draft_note = " [DRAFT — Readiness Gate Locked]" if is_draft else ""
        print(f"Exported {len(created)} ordered ticket file(s){draft_note} to {out_dir}:")
        for f in created:
            print(f"  - {f.relative_to(workspace) if f.is_relative_to(workspace) else f}")
        return 0

    if args.cmd == "export-github-issues":
        try:
            res = PreFlightOps.export_github_issues(
                workspace=workspace,
                repo=args.repo,
                branch=args.branch,
                issues_dir=Path(args.output_dir).resolve() if args.output_dir else None,
                force=args.force,
                dry_run=args.dry_run,
            )
            print(format_github_issues_summary(res))
            return 0
        except (ValueError, PermissionError, RuntimeError) as err:
            print(f"ERROR: {err}", file=sys.stderr)
            return 2

    return 1


if __name__ == "__main__":
    sys.exit(main())
