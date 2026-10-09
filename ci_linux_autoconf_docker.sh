#!/usr/bin/env bash
#
# Run PostgreSQL's GitHub Actions "Linux - Autoconf" job locally in Docker.

set -euo pipefail

image="ghcr.io/anarazel/pg-vm-images/main/linux_debian_trixie_ci:latest"
source_mode="archive"
ref="HEAD"
use_current=0
keep=0
shell_only=0
build_jobs="${BUILD_JOBS:-4}"
test_jobs="${TEST_JOBS:-4}"
check="${CHECK:-check-world PROVE_FLAGS=--timer}"
checkflags="${CHECKFLAGS:--Otarget}"
tmpdir=""
docker_args=()

usage()
{
	cat <<EOF
Usage: $0 [options] [source-dir]

Options:
  --image IMAGE        Docker image to use
  --ref REF            Test a committed ref via git archive, default: HEAD
  --use-current        Run directly in source-dir instead of its HEAD commit
  --build-jobs N       Build parallelism, default: ${build_jobs}
  --test-jobs N        Test parallelism, default: ${test_jobs}
  --check TARGET       make target, default: ${check}
  --checkflags FLAGS   make flags, default: ${checkflags}
  --shell              Open a shell in the prepared container
  --keep               Keep the temporary source directory after success
  --docker-arg ARG     Pass an extra argument to docker run; repeat as needed
  -h, --help           Show this help

source-dir defaults to the current directory.
EOF
}

source_dir=""
while [ "$#" -gt 0 ]; do
	case "$1" in
		--image)
			image="$2"
			shift 2
			;;
		--ref)
			ref="$2"
			source_mode="archive"
			shift 2
			;;
		--use-current)
			source_mode="current"
			use_current=1
			shift
			;;
		--build-jobs)
			build_jobs="$2"
			shift 2
			;;
		--test-jobs)
			test_jobs="$2"
			shift 2
			;;
		--check)
			check="$2"
			shift 2
			;;
		--checkflags)
			checkflags="$2"
			shift 2
			;;
		--shell)
			shell_only=1
			shift
			;;
		--keep)
			keep=1
			shift
			;;
		--docker-arg)
			docker_args+=("$2")
			shift 2
			;;
		-h|--help)
			usage
			exit 0
			;;
		-*)
			echo "unknown option: $1" >&2
			usage >&2
			exit 2
			;;
		*)
			if [ -n "$source_dir" ]; then
				echo "only one source-dir may be specified" >&2
				exit 2
			fi
			source_dir="$1"
			shift
			;;
	esac
done

if [ -n "$ref" ] && [ "$use_current" -eq 1 ]; then
	echo "--ref and --use-current cannot be combined" >&2
	exit 2
fi

if ! command -v docker >/dev/null 2>&1; then
	echo "docker not found in PATH" >&2
	exit 1
fi

if [ -n "$source_dir" ]; then
	cd "$source_dir"
fi

repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"

cleanup()
{
	if [ -n "$tmpdir" ] && [ "$keep" -eq 0 ]; then
		rm -rf "$tmpdir"
	fi
}
trap cleanup EXIT

if [ "$source_mode" = "current" ]; then
	work_src=$repo_root
	echo "Using current checkout: $work_src"
else
	tmpdir=$(mktemp -d "${TMPDIR:-/tmp}/pg-linux-autoconf-docker.XXXXXX")
	work_src="$tmpdir/src"
	mkdir "$work_src"

	if [ "$source_mode" = "archive" ]; then
		commit=$(git rev-parse --verify "${ref}^{commit}")
		echo "Exporting ${commit} to $work_src"
		git archive --format=tar "$commit" | tar -xf - -C "$work_src"
	else
		echo "Copying tracked and unignored files to $work_src"
		git ls-files -z --cached --others --exclude-standard |
			tar --null --ignore-failed-read -T - -cf - |
			tar -xf - -C "$work_src"
	fi
fi

tty_args=()
if [ -t 0 ] && [ -t 1 ]; then
	tty_args=(-it)
fi

set +e
docker run --rm "${tty_args[@]}" \
	--privileged --pid=host --ipc=host --ulimit memlock=-1:-1 \
	-e "HOST_UID=$(id -u)" \
	-e "HOST_GID=$(id -g)" \
	-e "BUILD_JOBS=$build_jobs" \
	-e "TEST_JOBS=$test_jobs" \
	-e "CHECK=$check" \
	-e "CHECKFLAGS=$checkflags" \
	-e "PG_CI_SHELL_ONLY=$shell_only" \
	-e "PG_CI_EXTRA_CONFIGURE_ARGS=${PG_CI_EXTRA_CONFIGURE_ARGS:-}" \
	-v "$work_src:/src" \
	-w /src \
	"${docker_args[@]}" \
	"$image" \
	bash -lc "$(cat <<'CONTAINER_SCRIPT'
set -euo pipefail

if ! getent group "$HOST_GID" >/dev/null; then
	groupadd -g "$HOST_GID" pgci
fi

if getent passwd "$HOST_UID" >/dev/null; then
	run_user=$(getent passwd "$HOST_UID" | cut -d: -f1)
else
	useradd -m -u "$HOST_UID" -g "$HOST_GID" postgres
	run_user=postgres
fi

mkdir -p /tmp/cores
chown root:"$HOST_GID" /tmp/cores || true
chmod 770 /tmp/cores || true
sysctl kernel.core_pattern='/tmp/cores/%e-%s-%p.core'
sysctl -w kernel.io_uring_disabled=0

cat >> /etc/hosts <<'HOSTS'
127.0.0.1 pg-loadbalancetest
127.0.0.2 pg-loadbalancetest
127.0.0.3 pg-loadbalancetest
HOSTS

cat > /tmp/pg-linux-autoconf-run.sh <<'RUN_SCRIPT'
set -euo pipefail

export DEBUGINFOD_URLS="https://debuginfod.debian.net https://debuginfod.ubuntu.com"
export CCACHE_DIR="${CCACHE_DIR:-/src/ccache_dir}"
export CC="ccache gcc"
export CXX="ccache g++"
export CLANG="ccache clang"
export CPPFLAGS="-DRELCACHE_FORCE_RELEASE -DENFORCE_REGRESSION_TEST_NAME_RESTRICTIONS"
export CFLAGS="-O2 -ggdb -fno-sanitize-recover=all -fsanitize=alignment,undefined"
export CXXFLAGS="-O2 -ggdb -fno-sanitize-recover=all -fsanitize=alignment,undefined"
export LDFLAGS="-fsanitize=alignment,undefined"
export UBSAN_OPTIONS="print_stacktrace=1:disable_coredump=0:abort_on_error=1:verbosity=2"
export ASAN_OPTIONS="print_stacktrace=1:disable_coredump=0:abort_on_error=1:detect_leaks=0"
export PGCTLTIMEOUT=120
export TEMP_CONFIG="/src/src/tools/ci/pg_ci_base.conf"
export PG_TEST_EXTRA="kerberos ldap ssl libpq_encryption load_balance oauth"
export PG_TEST_PG_COMBINEBACKUP_MODE="--copy-file-range"
export PG_TEST_PG_UPGRADE_MODE="--link"

configure_args=(
	--enable-cassert
	--enable-injection-points
	--enable-debug
	--enable-tap-tests
	--enable-nls
	--with-segsize-blocks=6
	--with-libnuma
	--with-liburing
	--with-gssapi
	--with-icu
	--with-ldap
	--with-libcurl
	--with-libxml
	--with-libxslt
	--with-llvm
	--with-lz4
	--with-pam
	--with-perl
	--with-python
	--with-selinux
	--with-ssl=openssl
	--with-systemd
	--with-tcl
	--with-tclconfig=/usr/lib/tcl8.6/
	--with-uuid=ossp
	--with-zstd
)

if [ -n "${PG_CI_EXTRA_CONFIGURE_ARGS:-}" ]; then
	# Intentionally split like a shell command line for local experimentation.
	extra_configure_args=( ${PG_CI_EXTRA_CONFIGURE_ARGS} )
	configure_args+=( "${extra_configure_args[@]}" )
fi

./configure "${configure_args[@]}"
make -s -j"${BUILD_JOBS}" world-bin
make -s ${CHECK} ${CHECKFLAGS} -j"${TEST_JOBS}"
RUN_SCRIPT

chown "$run_user":"$HOST_GID" /tmp/pg-linux-autoconf-run.sh
chmod 755 /tmp/pg-linux-autoconf-run.sh

if [ "$PG_CI_SHELL_ONLY" = "1" ]; then
	exec su "$run_user" -c "cd /src && bash --noprofile --norc"
fi

exec su "$run_user" -c "cd /src && bash --noprofile --norc -eo pipefail /tmp/pg-linux-autoconf-run.sh"
CONTAINER_SCRIPT
)"
status=$?
set -e

if [ "$status" -ne 0 ] && [ -n "$tmpdir" ]; then
	keep=1
	echo "Docker CI run failed; preserved copied source and logs in $work_src" >&2
fi

exit "$status"
