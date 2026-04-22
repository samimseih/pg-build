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

  # Clean up any broken state on remote before syncing
  REMOTE_WORKTREE="~/$PREFIX/worktrees/$WORKTREE_NAME"
  echo "🧹 Resetting remote worktree to clean state..."
  ssh "$REMOTE" "cd $REMOTE_WORKTREE && git am --abort 2>/dev/null; git checkout -- . && git clean -fd" || true

  # Sync remote's git state locally so we diff against the right base
  REMOTE_REPO="$REMOTE:$REMOTE_WORKTREE"
  echo "🔄 Fetching remote git state from $REMOTE..."
  git fetch "$REMOTE_REPO" HEAD:refs/remotes/build-remote/HEAD 2>/dev/null || true
  REMOTE_HEAD=$(ssh "$REMOTE" "cd $REMOTE_WORKTREE && git rev-parse HEAD")

  if git cat-file -e "$REMOTE_HEAD" 2>/dev/null; then
    BASE="$REMOTE_HEAD"
  else
    echo "⚠️  Remote HEAD $REMOTE_HEAD not found locally after fetch, falling back to merge-base"
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

  # Sync unstaged changes (modified/deleted files)
  DIRTY=$(git diff --name-only)
  if [[ -n "$DIRTY" ]]; then
    DELETED=$(git diff --name-only --diff-filter=D)
    MODIFIED=$(git diff --name-only --diff-filter=d)
    if [[ -n "$MODIFIED" ]]; then
      echo "📤 Rsyncing $(echo "$MODIFIED" | wc -l | tr -d ' ') modified file(s) to $REMOTE"
      echo "$MODIFIED" | rsync -az --files-from=- "$LOCAL_SRC/" "$REMOTE:~/$PREFIX/worktrees/$WORKTREE_NAME/"
    fi
    if [[ -n "$DELETED" ]]; then
      echo "🗑️  Deleting $(echo "$DELETED" | wc -l | tr -d ' ') file(s) on $REMOTE"
      echo "$DELETED" | ssh "$REMOTE" "cd ~/$PREFIX/worktrees/$WORKTREE_NAME && xargs rm -f"
    fi
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
