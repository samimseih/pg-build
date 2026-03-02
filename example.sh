#!/bin/bash

# Resolve the real path of the script (follows symlinks)
SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ "$SOURCE" != /* ]] && SOURCE="$DIR/$SOURCE"
done
SCRIPT_DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"

# If -l or --list-worktrees is passed, run it directly without other args
if [[ "$*" == *"-l"* ]] || [[ "$*" == *"--list-worktrees"* ]]; then
  python3 $SCRIPT_DIR/pg_build.py "$@"
else
  python3 $SCRIPT_DIR/pg_build.py \
    --prefix ~/Documents/pgdev/installations \
    --branch master \
    --capture-output \
    --meson-flags "-Ddocs=enabled --debug -Dcassert=true -Dtap_tests=enabled -Dinjection_points=true '-Dc_args=-Wall'" \
    "$@"
fi
