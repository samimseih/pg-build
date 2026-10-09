#!/usr/bin/env bash

set -euo pipefail
shopt -s nullglob

usage() {
  cat <<'EOF'
Usage:
  install_test_module.sh [options] <module>

Install a built PostgreSQL test module from src/test/modules/<module> into the
PostgreSQL installation selected by pg_config.

Options:
  --repo-root PATH   PostgreSQL source tree root. Defaults to $PGSRC or the
                     nearest parent of $PWD containing src/test/modules.
  --pg-config PATH   pg_config to install against. Defaults to the matching
                     ~/pgdev/installations/pghome/<worktree>/bin/pg_config when
                     --repo-root points at ~/pgdev/installations/worktrees/<worktree>.
                     Otherwise falls back to $PG_CONFIG or pg_config on PATH.
  --build-dir PATH   Meson build directory. Defaults to the first existing
                     build dir among <repo>/build, <repo>/build-* and
                     <repo>/build_* that contains the module artifact.
  -n, --dry-run      Print the install commands without executing them.
  -h, --help         Show this help text.

Examples:
  install_test_module.sh injection_points
  install_test_module.sh --repo-root ~/pgdev/installations/worktrees/dev injection_points
  install_test_module.sh --pg-config ~/pgdev/installations/pghome/dev/bin/pg_config injection_points
EOF
}

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

run() {
  if [[ "$dry_run" == "1" ]]; then
    printf '%q ' "$@"
    printf '\n'
  else
    "$@"
  fi
}

find_repo_root() {
  local dir="$1"

  while [[ "$dir" != "/" ]]; do
    if [[ -d "$dir/src/test/modules" ]] && [[ -f "$dir/meson.build" || -f "$dir/GNUmakefile" ]]; then
      printf '%s\n' "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done

  return 1
}

infer_pg_config_from_repo_root() {
  local repo_root="$1"
  local prefix="$HOME/pgdev/installations/worktrees/"
  local suffix worktree_name candidate

  case "$repo_root" in
    "$prefix"*)
      suffix="${repo_root#"$prefix"}"
      worktree_name="${suffix%%/*}"
      candidate="$HOME/pgdev/installations/pghome/$worktree_name/bin/pg_config"
      if [[ -x "$candidate" ]]; then
        printf '%s\n' "$candidate"
        return 0
      fi
      ;;
  esac

  return 1
}

find_module_artifact_dir() {
  local repo_root="$1"
  local module="$2"
  local build_dir_candidate artifact_dir

  if [[ -n "${build_dir:-}" ]]; then
    artifact_dir="$build_dir/src/test/modules/$module"
    [[ -d "$artifact_dir" ]] || die "build dir does not contain $artifact_dir"
    compgen -G "$artifact_dir/*.so" >/dev/null || die "no built shared library found under $artifact_dir"
    printf '%s\n' "$artifact_dir"
    return 0
  fi

  for build_dir_candidate in "$repo_root"/build "$repo_root"/build-* "$repo_root"/build_*; do
    [[ -d "$build_dir_candidate" ]] || continue
    artifact_dir="$build_dir_candidate/src/test/modules/$module"
    if [[ -d "$artifact_dir" ]] && compgen -G "$artifact_dir/*.so" >/dev/null; then
      printf '%s\n' "$artifact_dir"
      return 0
    fi
  done

  artifact_dir="$repo_root/src/test/modules/$module"
  if compgen -G "$artifact_dir/*.so" >/dev/null; then
    printf '%s\n' "$artifact_dir"
    return 0
  fi

  return 1
}

repo_root=""
pg_config=""
build_dir=""
module=""
dry_run=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-root)
      [[ $# -ge 2 ]] || die "--repo-root requires a value"
      repo_root="$2"
      shift 2
      ;;
    --pg-config)
      [[ $# -ge 2 ]] || die "--pg-config requires a value"
      pg_config="$2"
      shift 2
      ;;
    --build-dir)
      [[ $# -ge 2 ]] || die "--build-dir requires a value"
      build_dir="$2"
      shift 2
      ;;
    -n|--dry-run)
      dry_run=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    -*)
      die "unknown option: $1"
      ;;
    *)
      if [[ -n "$module" ]]; then
        die "module name already set to '$module'"
      fi
      module="$1"
      shift
      ;;
  esac
done

if [[ -z "$module" && $# -gt 0 ]]; then
  module="$1"
  shift
fi

[[ -n "$module" ]] || die "module name is required"
[[ $# -eq 0 ]] || die "unexpected extra arguments: $*"

if [[ -z "$repo_root" ]]; then
  if [[ -n "${PGSRC:-}" ]]; then
    repo_root="$PGSRC"
  else
    repo_root="$(find_repo_root "$PWD")" || die "could not infer repo root from \$PWD; pass --repo-root"
  fi
fi

repo_root="$(cd "$repo_root" && pwd)"
module_src_dir="$repo_root/src/test/modules/$module"
[[ -d "$module_src_dir" ]] || die "module source directory not found: $module_src_dir"

if [[ -z "$pg_config" ]]; then
  if pg_config="$(infer_pg_config_from_repo_root "$repo_root")"; then
    :
  elif [[ -n "${PG_CONFIG:-}" ]]; then
    pg_config="$PG_CONFIG"
  else
    pg_config="$(command -v pg_config || true)"
  fi
fi

[[ -n "$pg_config" ]] || die "could not find pg_config; pass --pg-config"
[[ -x "$pg_config" ]] || die "pg_config is not executable: $pg_config"

artifact_dir="$(find_module_artifact_dir "$repo_root" "$module")" || die \
  "no built shared library found for '$module'; build the module first"

pkglibdir="$("$pg_config" --pkglibdir)"
sharedir="$("$pg_config" --sharedir)"
extensiondir="$sharedir/extension"

shared_libs=( "$artifact_dir"/*.so )
control_files=( "$module_src_dir"/*.control )
sql_files=( "$module_src_dir"/*.sql )

printf 'Installing module %s\n' "$module"
printf '  repo root:      %s\n' "$repo_root"
printf '  pg_config:      %s\n' "$pg_config"
printf '  artifact dir:   %s\n' "$artifact_dir"
printf '  library dir:    %s\n' "$pkglibdir"
printf '  extension dir:  %s\n' "$extensiondir"

run mkdir -p "$pkglibdir" "$extensiondir"

for shared_lib in "${shared_libs[@]}"; do
  run install -m 755 "$shared_lib" "$pkglibdir/"
done

for control_file in "${control_files[@]}"; do
  run install -m 644 "$control_file" "$extensiondir/"
done

for sql_file in "${sql_files[@]}"; do
  run install -m 644 "$sql_file" "$extensiondir/"
done

if [[ "${#control_files[@]}" -eq 0 ]]; then
  printf 'note: no .control files found under %s\n' "$module_src_dir"
fi

if [[ "${#sql_files[@]}" -eq 0 ]]; then
  printf 'note: no extension SQL files found under %s\n' "$module_src_dir"
fi

printf 'Install complete.\n'
