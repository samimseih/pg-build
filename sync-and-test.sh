#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG="$SCRIPT_DIR/test_config"
[[ -f "$CONFIG" ]] || { echo "Error: $CONFIG not found"; exit 1; }
REMOTE="$(head -n1 "$CONFIG" | tr -d '[:space:]')"
[[ -n "$REMOTE" ]] || { echo "Error: no hostname in $CONFIG"; exit 1; }

WORKTREE_NAME="dev"
PREFIX="Development/pgdev/installations"
LOCAL_SRC="$HOME/$PREFIX/worktrees/$WORKTREE_NAME"
TEST_CMD="${1:-pg_check_world}"

# Generate diff if local worktree exists
PATCH_FLAG=""
if [[ -d "$LOCAL_SRC" ]]; then
  cd "$LOCAL_SRC"
  REMOTE_HEAD=$(ssh "$REMOTE" "cd ~/$PREFIX/worktrees/$WORKTREE_NAME && git rev-parse HEAD")
  # Find common ancestor via patch-id matching, fall back to diffing against upstream/master
  if git cat-file -e "$REMOTE_HEAD" 2>/dev/null; then
    BASE="$REMOTE_HEAD"
  else
    BASE=$(git merge-base HEAD upstream/master)
  fi
  rm -rf /tmp/pg-patches && mkdir -p /tmp/pg-patches
  PATCHES=$(git format-patch "$BASE"..HEAD -o /tmp/pg-patches)
  if [[ -n "$PATCHES" ]]; then
    echo "📦 Sending $(echo "$PATCHES" | wc -l | tr -d ' ') patch(es) to $REMOTE"
    echo "$PATCHES"
    rsync -az /tmp/pg-patches/ "$REMOTE:~/tmp/pg-patches/"
    PATCH_FLAG="--patch ~/tmp/pg-patches/*"
  else
    echo "No changes to sync"
  fi
else
  echo "No local worktree yet — will do initial build on remote"
fi

ssh "$REMOTE" bash -lc "'
  killall -9 postgres 2>/dev/null || true
  killall -9 pg_regress 2>/dev/null || true
  killall -9 meson 2>/dev/null || true
  sleep 1
  REMAINING=\$(pgrep -a \"postgres|pg_regress|meson\" || true)
  if [[ -n \"\$REMAINING\" ]]; then
    echo \"⚠️  Processes still running, manual intervention needed:\"
    echo \"\$REMAINING\"
    exit 1
  fi
  ~/build --worktree-name $WORKTREE_NAME $PATCH_FLAG
  source ~/$PREFIX/activate_${WORKTREE_NAME}.sh
  cd ~/$PREFIX/worktrees/$WORKTREE_NAME/build
  $TEST_CMD
'"
