#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG="$SCRIPT_DIR/test_config"
[[ -f "$CONFIG" ]] || { echo "Error: $CONFIG not found"; exit 1; }
REMOTE="$(head -n1 "$CONFIG" | tr -d '[:space:]')"
[[ -n "$REMOTE" ]] || { echo "Error: no hostname in $CONFIG"; exit 1; }
WORKTREE_NAME="dev"
LOCAL_SRC="$HOME/Development/pgdev/installations/worktrees/$WORKTREE_NAME/"
REMOTE_PREFIX="$HOME/Development/pgdev/installations"
REMOTE_WORKTREE="$REMOTE_PREFIX/worktrees/$WORKTREE_NAME"
TEST_CMD="${1:-pg_check_world}"

# Sync pg-build tooling to remote
rsync -az --exclude='.git/' --exclude='__pycache__/' \
  "$HOME/Development/pg-build/" "$REMOTE:Development/pg-build/"

# Sync local postgres worktree source to remote (skip build artifacts)
rsync -az --exclude='build/' --exclude='.git/' \
  "$LOCAL_SRC" "$REMOTE:$REMOTE_WORKTREE/"

# Build on remote using the build script, then run tests via activate script helpers
ssh "$REMOTE" bash -lc "'
  cd ~/Development/pg-build
  ./build --worktree-name $WORKTREE_NAME --branch master
  source $REMOTE_PREFIX/activate_${WORKTREE_NAME}.sh
  cd $REMOTE_WORKTREE/build
  $TEST_CMD
'"
