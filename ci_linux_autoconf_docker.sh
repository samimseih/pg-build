#!/usr/bin/env bash
#
# Compatibility wrapper for the old single-flavor helper name.

set -euo pipefail

script_dir="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
exec "$script_dir/ci_linux_docker.sh" --flavor linux-autoconf "$@"
