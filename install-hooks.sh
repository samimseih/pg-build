#!/usr/bin/env bash
#
# install-hooks.sh — point a git repo at a hooks directory via core.hooksPath.
#
# Sets core.hooksPath on the target repo so the repo and all of its worktrees
# use the hooks in HOOKS_DIR (pre-commit: ASCII-only; commit-msg: subject
# length, ASCII, no agent attribution). Scoped to that repo tree only --
# nothing else on the machine is affected. Idempotent.
#
# Usage:
#   ./install-hooks.sh HOOKS_DIR SOURCE_REPO
#
# Example:
#   ./install-hooks.sh ~/Development/pg-build/git_hooks \
#                      ~/pgdev/installations/source
#
set -euo pipefail

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 HOOKS_DIR SOURCE_REPO" >&2
    echo "  HOOKS_DIR     directory containing the hook scripts" >&2
    echo "  SOURCE_REPO   git repo to apply core.hooksPath to" >&2
    exit 2
fi

hooks_dir="$1"
target="$2"

if [ ! -d "$hooks_dir" ]; then
    echo "❌ hooks directory not found: $hooks_dir" >&2
    exit 1
fi
if [ ! -d "$target/.git" ] && [ ! -f "$target/.git" ]; then
    echo "❌ not a git repository: $target" >&2
    exit 1
fi

# Resolve to an absolute path so core.hooksPath works from any worktree.
hooks_dir="$(cd "$hooks_dir" && pwd)"

# Ensure the hook scripts are executable (git requires this or it skips them).
chmod +x "$hooks_dir"/* 2>/dev/null || true

git -C "$target" config core.hooksPath "$hooks_dir"

echo "✅ core.hooksPath set on $target"
echo "   -> $hooks_dir"
echo "   Active for the repo and all its worktrees:"
for h in "$hooks_dir"/*; do
    [ -f "$h" ] && echo "     - $(basename "$h")"
done
echo
echo "   To remove: git -C \"$target\" config --unset core.hooksPath"
