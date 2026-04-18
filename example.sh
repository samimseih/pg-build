#!/bin/bash

# Resolve the real path of the script (follows symlinks)
SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ "$SOURCE" != /* ]] && SOURCE="$DIR/$SOURCE"
done
SCRIPT_DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"

#export LSAN_OPTIONS=exitcode=0
export CC="ccache cc"
export CXX="ccache c++"
# --meson-flags "-Db_sanitize=address -Ddocs=enabled --debug -Dcassert=true -Dtap_tests=enabled -Dinjection_points=true '-Dc_args=-Wall'" \

# If -l, --list-worktrees, --clean-worktrees, or --commit is passed, run it directly without other args
if [[ "$*" == *"-l"* ]] || [[ "$*" == *"--list-worktrees"* ]] || [[ "$*" == *"--clean-worktrees"* ]] || [[ "$*" == *"--remove-worktree"* ]] || [[ "$*" == *"--commit"* ]] || [[ "$*" == *"--tag"* ]]; then
  python3 $SCRIPT_DIR/pg_build.py "$@"
elif [[ "$*" == *"--release"* ]]; then
  # Remove --release from args before passing to pg_build.py
  ARGS=()
  for arg in "$@"; do
    [[ "$arg" != "--release" ]] && ARGS+=("$arg")
  done
  if [[ "$*" == *"--build-system make"* ]]; then
    python3 $SCRIPT_DIR/pg_build.py \
      --prefix ~/Development/pgdev/installations \
      --branch master \
      --capture-output \
      --configure-flags "--enable-tap-tests CFLAGS='-O2 -DNDEBUG'" \
      "${ARGS[@]}"
  else
    python3 $SCRIPT_DIR/pg_build.py \
      --prefix ~/Development/pgdev/installations \
      --branch master \
      --capture-output \
      --meson-flags "-Dbuildtype=release -Dcassert=false -Dtap_tests=disabled -Dinjection_points=false -Ddocs=disabled '-Dc_args=-O2 -DNDEBUG'" \
      "${ARGS[@]}"
  fi
elif [[ "$*" == *"--build-system make"* ]]; then
  python3 $SCRIPT_DIR/pg_build.py \
    --prefix ~/Development/pgdev/installations \
    --branch master \
    --capture-output \
    --configure-flags "--enable-debug --enable-cassert --enable-tap-tests --enable-injection-points --enable-docs CFLAGS='-Wall'" \
    "$@"
else
  python3 $SCRIPT_DIR/pg_build.py \
    --prefix ~/Development/pgdev/installations \
    --branch master \
    --capture-output \
    --meson-flags "-Ddocs=enabled --debug -Dcassert=true -Dtap_tests=enabled -Dinjection_points=true '-Dc_args=-Wall'" \
    "$@"
fi

# Run ctags on the source worktree (skip for list/clean/remove operations)
if [[ "$*" != *"-l"* ]] && [[ "$*" != *"--list-worktrees"* ]] && [[ "$*" != *"--clean-worktrees"* ]] && [[ "$*" != *"--remove-worktree"* ]]; then
  for arg in "$@"; do
    if [[ "$prev" == "--worktree-name" ]]; then
      WORKTREE_NAME="$arg"
      break
    fi
    prev="$arg"
  done
  if [[ -n "$WORKTREE_NAME" ]]; then
    WORKTREE_DIR=~/Development/pgdev/installations/worktrees/$WORKTREE_NAME
    if [[ -d "$WORKTREE_DIR" ]]; then
      ctags -R "$WORKTREE_DIR"
    fi
  fi
fi
