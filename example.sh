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
# --meson-flags "-Db_sanitize=address -Ddocs=enabled --debug -Dcassert=true -Dtap_tests=enabled -Dinjection_points=true '-Dc_args=-Wall'" \

# If -l, --list-worktrees, --clean-worktrees, or --commit is passed, run it directly without other args
if [[ "$*" == *"-l"* ]] || [[ "$*" == *"--list-worktrees"* ]] || [[ "$*" == *"--clean-worktrees"* ]] || [[ "$*" == *"--remove-worktree"* ]] || [[ "$*" == *"--commit"* ]] || [[ "$*" == *"--tag"* ]]; then
  python3 $SCRIPT_DIR/pg_build.py "$@"
else
  python3 $SCRIPT_DIR/pg_build.py \
    --prefix ~/pgdev/installations \
    --branch master \
    --capture-output \
    --meson-flags "-Ddocs=enabled --debug -Dcassert=true -Dtap_tests=enabled -Dinjection_points=true '-Dc_args=-Wall'" \
    "$@"
fi
