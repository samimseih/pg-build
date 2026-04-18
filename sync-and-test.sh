#!/bin/bash
set -euo pipefail

REMOTE="dev-dsk-simseih-1e-5652b3f8.us-east-1.amazon.com"
SRC="/Users/simseih/pgdev/installations/worktrees/dev/"
REMOTE_DIR="~/postgres-dev"
CMD_LINE="${SRC}build/meson-private/cmd_line.txt"

if [[ ! -f "$CMD_LINE" ]]; then
  echo "Error: $CMD_LINE not found. Run a meson build first." >&2
  exit 1
fi

OPTS=$(python3 -c "
import configparser, sys, shlex
c = configparser.ConfigParser()
c.read(sys.argv[1])
args = []
for k, v in c.items('options'):
    if k == 'prefix':
        continue
    args.append('-D' + k + '=' + shlex.quote(v))
print(' '.join(args))
" "$CMD_LINE")

git -C "$SRC" log --oneline -100 > "${SRC}.git-log.txt"

rsync -az --exclude='build/' --exclude='.git/' --exclude='GNUmakefile' --exclude='src/Makefile.global' --exclude='src/include/pg_config.h' --exclude='src/include/pg_config_ext.h' --exclude='src/include/pg_config_os.h' --exclude='src/interfaces/ecpg/include/ecpg_config.h' "$SRC" "$REMOTE:$REMOTE_DIR/"

JOBS=$(ssh "$REMOTE" "nproc")
ssh "$REMOTE" "cd $REMOTE_DIR && meson setup build $OPTS --reconfigure 2>/dev/null || meson setup build $OPTS; meson compile -C build -j$JOBS && meson test -C build --print-errorlogs --num-processes $JOBS $*"
