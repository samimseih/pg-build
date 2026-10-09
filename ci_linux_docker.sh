#!/usr/bin/env bash
#
# Run selected PostgreSQL GitHub Actions Linux jobs locally in Docker.

set -euo pipefail

container_repo="ghcr.io/anarazel/pg-vm-images/main"
linux_image="${container_repo}/linux_debian_trixie_ci:latest"
docs_image="${container_repo}/linux_debian_trixie_ci_docs:latest"
flavor="linux-autoconf"
image=""
source_mode="archive"
ref="HEAD"
ref_set=0
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
  --flavor NAME       CI flavor to run, default: linux-autoconf
                      supported: sanity-check, linux-autoconf,
                      linux-meson-32, linux-meson-64, compilerwarnings
  --image IMAGE       Docker image to use
  --ref REF           Test a committed ref via git archive, default: HEAD
  --use-current       Run directly in source-dir instead of its HEAD commit
  --build-jobs N      Build parallelism, default: ${build_jobs}
  --test-jobs N       Test parallelism, default: ${test_jobs}
  --check TARGET      make target for linux-autoconf, default: ${check}
  --checkflags FLAGS  make check flags, default: ${checkflags}
  --shell             Open a shell in the prepared container
  --keep              Keep the temporary source directory after success
  --docker-arg ARG    Pass an extra argument to docker run; repeat as needed
  -h, --help          Show this help

source-dir defaults to the current directory.
EOF
}

source_dir=""
while [ "$#" -gt 0 ]; do
	case "$1" in
		--flavor)
			flavor="$2"
			shift 2
			;;
		--image)
			image="$2"
			shift 2
			;;
		--ref)
			ref="$2"
			ref_set=1
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

case "$flavor" in
	sanity)
		flavor="sanity-check"
		;;
	sanity-check|linux-autoconf|linux-meson-32|linux-meson-64|compilerwarnings)
		;;
	*)
		echo "unknown --flavor '$flavor'" >&2
		usage >&2
		exit 2
		;;
esac

if [ -z "$image" ]; then
	case "$flavor" in
		compilerwarnings)
			image="$docs_image"
			;;
		*)
			image="$linux_image"
			;;
	esac
fi

if [ "$ref_set" -eq 1 ] && [ "$use_current" -eq 1 ]; then
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
	tmpdir=$(mktemp -d "${TMPDIR:-/tmp}/pg-${flavor}-docker.XXXXXX")
	work_src="$tmpdir/src"
	mkdir "$work_src"

	commit=$(git rev-parse --verify "${ref}^{commit}")
	echo "Exporting ${commit} to $work_src"
	git archive --format=tar "$commit" | tar -xf - -C "$work_src"
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
	-e "PG_CI_FLAVOR=$flavor" \
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

cat > /tmp/pg-linux-ci-run.sh <<'RUN_SCRIPT'
set -euo pipefail

linux_configure_features=(
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

linux_configure_features_string="${linux_configure_features[*]}"

export DEBUGINFOD_URLS="https://debuginfod.debian.net https://debuginfod.ubuntu.com"
export CCACHE_DIR="${CCACHE_DIR:-/src/ccache_dir}"
export PGCTLTIMEOUT=120
export TEMP_CONFIG="/src/src/tools/ci/pg_ci_base.conf"
export PG_TEST_EXTRA="kerberos ldap ssl libpq_encryption load_balance oauth"
export MBUILD_TARGET="${MBUILD_TARGET:-all testprep}"
export MTEST_ARGS="${MTEST_ARGS:---print-errorlogs --no-rebuild -C build}"

set_default_compilers()
{
	export CC="${CC:-ccache gcc}"
	export CXX="${CXX:-ccache g++}"
	export CLANG="${CLANG:-ccache clang}"
}

set_sanitizer_runtime()
{
	export UBSAN_OPTIONS="print_stacktrace=1:disable_coredump=0:abort_on_error=1:verbosity=2"
	export ASAN_OPTIONS="print_stacktrace=1:disable_coredump=0:abort_on_error=1:detect_leaks=0"
}

ninja_build()
{
	# shellcheck disable=SC2086
	ninja -C build -j"${BUILD_JOBS}" ${MBUILD_TARGET}
	ninja -C build -t missingdeps
}

meson_test_world()
{
	ulimit -c unlimited

	if [ -n "${ADDITIONAL_SETUP:-}" ]; then
		eval "$ADDITIONAL_SETUP"
	fi

	echo "::group::test_setup"
	# shellcheck disable=SC2086
	meson test ${MTEST_ARGS} --suite setup --logbase setup
	echo "::endgroup::"

	# shellcheck disable=SC2086
	meson test ${MTEST_ARGS} --num-processes "${TEST_JOBS}" --no-suite setup ${MTEST_TARGET:-}
}

run_sanity_check()
{
	unset CFLAGS CXXFLAGS LDFLAGS
	set_default_compilers

	meson setup \
		--buildtype=debug \
		--auto-features=disabled \
		-Ddefault_library=shared \
		-Dtap_tests=enabled \
		build

	ninja_build

	MTEST_TARGET="cube/regress pg_ctl/001_start_stop" meson_test_world
}

run_linux_autoconf()
{
	set_default_compilers
	set_sanitizer_runtime
	export CPPFLAGS="-DRELCACHE_FORCE_RELEASE -DENFORCE_REGRESSION_TEST_NAME_RESTRICTIONS"
	export CFLAGS="-O2 -ggdb -fno-sanitize-recover=all -fsanitize=alignment,undefined"
	export CXXFLAGS="-O2 -ggdb -fno-sanitize-recover=all -fsanitize=alignment,undefined"
	export LDFLAGS="-fsanitize=alignment,undefined"
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
		"${linux_configure_features[@]}"
	)

	if [ -n "${PG_CI_EXTRA_CONFIGURE_ARGS:-}" ]; then
		# Intentionally split like a shell command line for local experimentation.
		extra_configure_args=( ${PG_CI_EXTRA_CONFIGURE_ARGS} )
		configure_args+=( "${extra_configure_args[@]}" )
	fi

	./configure "${configure_args[@]}"
	make -s -j"${BUILD_JOBS}" world-bin
	# shellcheck disable=SC2086
	make -s ${CHECK} ${CHECKFLAGS} -j"${TEST_JOBS}"
}

run_linux_meson_32()
{
	set_sanitizer_runtime
	export CC="ccache gcc -m32"
	export CXX="ccache g++ -m32"
	export CLANG="ccache clang"
	export CFLAGS="-O2 -ggdb -fno-sanitize-recover=all -fsanitize=alignment,undefined"
	export CXXFLAGS="-O2 -ggdb -fno-sanitize-recover=all -fsanitize=alignment,undefined"
	export LDFLAGS="-fsanitize=alignment,undefined"
	export PG_TEST_INITDB_EXTRA_OPTS="-c io_method=io_uring"

	meson setup \
		-Dcassert=true \
		-Dinjection_points=true \
		-Duuid=e2fs \
		--buildtype=debug \
		--pkg-config-path /usr/lib/i386-linux-gnu/pkgconfig/ \
		-DPERL=perl5.40-i386-linux-gnu \
		-Dlibnuma=disabled \
		build

	ninja_build
	PYTHONCOERCECLOCALE=0 LANG=C meson_test_world

	ulimit -c unlimited
	meson test ${MTEST_ARGS} --suite setup --logbase setup
	export LD_LIBRARY_PATH="$(pwd)/build/tmp_install/usr/local/pgsql/lib/x86_64-linux-gnu/:${LD_LIBRARY_PATH:-}"
	build/tmp_install/usr/local/pgsql/bin/initdb -N build/runningcheck --no-instructions -A trust
	echo "include '$(pwd)/src/tools/ci/pg_ci_base.conf'" >> build/runningcheck/postgresql.conf
	mkdir -p build/testrun
	build/tmp_install/usr/local/pgsql/bin/pg_ctl -c -o '-c fsync=off' -D build/runningcheck -l build/testrun/runningcheck.log start
	meson test ${MTEST_ARGS} --num-processes "${TEST_JOBS}" --setup running
	build/tmp_install/usr/local/pgsql/bin/pg_ctl -D build/runningcheck stop
}

run_linux_meson_64()
{
	set_default_compilers
	set_sanitizer_runtime
	export CFLAGS="-O2 -ggdb -fno-sanitize-recover=all -fsanitize=address"
	export CXXFLAGS="-O2 -ggdb -fno-sanitize-recover=all -fsanitize=address"
	export LDFLAGS="-fsanitize=address"
	export PG_TEST_INITDB_EXTRA_OPTS="-c io_method=io_uring"

	meson setup \
		-Dcassert=true \
		-Dinjection_points=true \
		-Duuid=e2fs \
		--buildtype=debug \
		-Dllvm=enabled \
		build

	ninja_build
	meson_test_world
}

compiler_warnings_configure_make()
{
	local conf="$1"
	local default_build="${2:-world-bin}"
	shift 2 || true

	echo "::group::configure"
	# shellcheck disable=SC2086
	./configure ${conf} "$@"
	echo "::endgroup::"

	make -s -j"${BUILD_JOBS}" clean
	# shellcheck disable=SC2086
	make -s -j"${BUILD_JOBS}" ${default_build}
}

run_compilerwarnings()
{
	export CCACHE_MAXSIZE="1G"
	echo "COPT=-Werror" > src/Makefile.custom

	CC="ccache gcc" CXX="ccache g++" CLANG="ccache clang" \
		compiler_warnings_configure_make \
		"${linux_configure_features_string} --cache gcc.cache --enable-dtrace" \
		world-bin \
		CLANG="ccache clang"

	CC="ccache gcc" CXX="ccache g++" \
		compiler_warnings_configure_make \
		"${linux_configure_features_string} --cache gcc.cache --enable-cassert" \
		world-bin

	CC="ccache clang" CXX="ccache clang++" \
		compiler_warnings_configure_make \
		"${linux_configure_features_string} --cache clang.cache" \
		world-bin

	CC="ccache clang" CXX="ccache clang++" \
		compiler_warnings_configure_make \
		"${linux_configure_features_string} --cache clang.cache --enable-cassert --enable-dtrace" \
		world-bin

	CC="ccache x86_64-w64-mingw32ucrt-gcc" CXX="ccache x86_64-w64-mingw32ucrt-g++" \
		compiler_warnings_configure_make \
		"--host=x86_64-w64-mingw32ucrt --enable-cassert --without-icu" \
		world-bin

	CC="ccache gcc" CXX="ccache g++" \
		compiler_warnings_configure_make \
		"--cache gcc.cache" \
		"-C doc"

	echo "::group::configure"
	./configure \
		"${linux_configure_features[@]}" \
		--cache gcc.cache \
		--quiet \
		CC="ccache gcc" CXX="ccache g++" CLANG="ccache clang"
	echo "::endgroup::"

	make -s -j"${BUILD_JOBS}" clean
	# shellcheck disable=SC2086
	make -s -j"${BUILD_JOBS}" -k ${CHECKFLAGS} \
		headerscheck cpluspluscheck \
		EXTRAFLAGS='-fmax-errors=10'
}

case "$PG_CI_FLAVOR" in
	sanity-check)
		run_sanity_check
		;;
	linux-autoconf)
		run_linux_autoconf
		;;
	linux-meson-32)
		run_linux_meson_32
		;;
	linux-meson-64)
		run_linux_meson_64
		;;
	compilerwarnings)
		run_compilerwarnings
		;;
	*)
		echo "unknown PG_CI_FLAVOR '$PG_CI_FLAVOR'" >&2
		exit 2
		;;
esac
RUN_SCRIPT

chown "$run_user":"$HOST_GID" /tmp/pg-linux-ci-run.sh
chmod 755 /tmp/pg-linux-ci-run.sh

if [ "$PG_CI_SHELL_ONLY" = "1" ]; then
	exec su "$run_user" -c "cd /src && bash --noprofile --norc"
fi

exec su "$run_user" -c "cd /src && bash --noprofile --norc -eo pipefail /tmp/pg-linux-ci-run.sh"
CONTAINER_SCRIPT
)"
status=$?
set -e

if [ "$status" -ne 0 ] && [ -n "$tmpdir" ]; then
	keep=1
	echo "Docker CI run failed; preserved copied source and logs in $work_src" >&2
fi

exit "$status"
