#!/usr/bin/env bash
set -euo pipefail

# Primary live-symlink installer for the PreFlight skill.
#
# Design Decision: Safety by default on real folders.
# This script will NOT silently `rm -rf` a real, non-symlink folder at any
# destination. If a real directory or file already exists at the target path,
# the script refuses and exits 1 by default. Pass `--force` to explicitly replace
# an existing real folder with a symlink.
#
# Links the `preflight` skill into the local skill directories used by
# each agent harness:
#   - ~/.claude/skills: Claude Code
#   - ~/.agents/skills: Codex and other Agent Skills-compatible harnesses
#   - ~/.gemini/config/skills: Google Gemini Antigravity
#
# Each entry is a symlink pointing directly into this clone, so a `git pull`
# is all that is needed to keep installed skills up to date without re-copying.

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
SKILL_NAME="preflight"
SKILL_SRC="$REPO/skills/$SKILL_NAME"

if [ ! -d "$SKILL_SRC" ] || [ ! -f "$SKILL_SRC/SKILL.md" ]; then
  echo "error: skill source not found at $SKILL_SRC" >&2
  exit 1
fi

FORCE=false
CUSTOM_DESTS=()

for arg in "$@"; do
  case "$arg" in
    --force|-f)
      FORCE=true
      ;;
    --help|-h)
      echo "Usage: $0 [--force] [DEST_DIR...]"
      echo ""
      echo "Links skills/preflight into agent skill directories:"
      echo "  - \$HOME/.claude/skills"
      echo "  - \$HOME/.agents/skills"
      echo "  - \$HOME/.gemini/config/skills"
      echo ""
      echo "Options:"
      echo "  --force   Replace existing real (non-symlink) directories at target"
      exit 0
      ;;
    *)
      CUSTOM_DESTS+=("$arg")
      ;;
  esac
done

if [ "${#CUSTOM_DESTS[@]}" -gt 0 ]; then
  DESTS=("${CUSTOM_DESTS[@]}")
else
  DESTS=(
    "$HOME/.claude/skills"
    "$HOME/.agents/skills"
    "$HOME/.gemini/config/skills"
  )
fi

for DEST in "${DESTS[@]}"; do
  # Guard: If $DEST is a symlink that resolves into this repo, we'd end up
  # writing the symlink back into the repo itself. Detect and bail out.
  if [ -L "$DEST" ]; then
    resolved="$(readlink -f "$DEST" 2>/dev/null || true)"
    case "$resolved" in
      "$REPO"|"$REPO"/*)
        echo "error: $DEST is a symlink into this repo ($resolved)." >&2
        echo "Remove it and re-run; the script will recreate it as a real directory." >&2
        exit 1
        ;;
    esac
  fi

  mkdir -p "$DEST"

  target="$DEST/$SKILL_NAME"

  # Guard: If $target itself is an existing symlink that resolves into this repo,
  # but NOT to our expected skill source, bail out to avoid writing inside repo.
  if [ -L "$target" ]; then
    resolved="$(readlink -f "$target" 2>/dev/null || true)"
    if [ "$resolved" != "$SKILL_SRC" ]; then
      case "$resolved" in
        "$REPO"|"$REPO"/*)
          echo "error: $target is a symlink into this repo ($resolved)." >&2
          exit 1
          ;;
      esac
    fi
  fi

  # Check if a real, non-symlink file or directory already exists at target
  if [ -e "$target" ] && [ ! -L "$target" ]; then
    if [ "$FORCE" = true ]; then
      rm -rf "$target"
    else
      echo "error: $target exists and is a real directory/file (not a symlink)." >&2
      echo "Refusing to overwrite without --force. Re-run with --force to replace it with a symlink." >&2
      exit 1
    fi
  fi

  ln -sfn "$SKILL_SRC" "$target"
  echo "linked $SKILL_NAME -> $SKILL_SRC ($DEST)"
done
