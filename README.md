# pg_build

A script for automating local PostgreSQL development environment setup — cloning, building, initializing, and starting one or more PostgreSQL instances from source using Git worktrees.

## Features

- Clones the PostgreSQL source repository and manages Git worktrees
- Builds PostgreSQL from source using **Meson** (default) or **Make**
- Optionally applies patches via `git am`
- Initializes and starts a primary PostgreSQL cluster, with optional postgres_fdw and replica instances
- Generates a shell activation script per instance with environment variables and helper functions
- Provides an opinionated `build` wrapper for common dev, release, and CI-flavor workflows
- Can reproduce several PostgreSQL Linux CI flavors locally in Docker
- Includes helper scripts for Commitfest patch downloads and installing built test modules

## Requirements

- Python 3.7+
- Git
- `meson` + `ninja` (or `make` / `autoconf` toolchain)
- Standard PostgreSQL build dependencies (e.g. `libreadline-dev`, `zlib1g-dev`, etc.)
- `lsof` (used to find processes listening on the target PostgreSQL port)
- `ctags` (the `build` wrapper refreshes tags after successful builds)
- Docker (optional; required for `~/build --ci-flavor ...`)

## Usage

For the opinionated local wrapper:

```bash
~/build --worktree-name dev
```

The `build` wrapper is a thin layer over `pg_build.py`. It supplies Sami's
default repository URLs, prefix, `master` branch, Meson developer flags, and
captured build output, then forwards the remaining arguments to `pg_build.py`.

For the lower-level script directly:

```bash
python pg_build.py [OPTIONS]
```

### `build` Wrapper Modes

The wrapper has a few high-level modes and toggles that are consumed by the
wrapper before it invokes `pg_build.py`.

| Option | Description |
|---|---|
| default | Development build: Meson `buildtype=debug`, debug symbols, assertions, injection points, TAP tests, and docs |
| `--release` | Performance-oriented build: optimized, assertions off, debug symbols off, docs off |
| `--assert`, `--no-assert` | Override assertion defaults |
| `--debug`, `--no-debug` | Override debug-symbol defaults |
| `--injection`, `--no-injection` | Override injection-point defaults |
| `--exec-backend`, `--no-exec-backend` | Enable or disable PostgreSQL's `EXEC_BACKEND` process model |
| `BUILD_DRY_RUN=1` | Print the command that would run instead of executing it |

Examples:

```bash
# Default dev build of master into ~/pgdev/installations/worktrees/dev
~/build --worktree-name dev

# Optimized build with symbols, useful for profiling
~/build --release --debug --worktree-name perf

# Autoconf/make build instead of Meson
~/build --build-system make --worktree-name make-dev
```

### Local CI Flavor Tests

The wrapper can also reproduce a supported GitHub Actions CI flavor locally.
Currently supported:

| Flavor | What it runs |
|---|---|
| `sanity-check` | Dockerized equivalent of the PostgreSQL CI `SanityCheck` job |
| `linux-autoconf` | Dockerized equivalent of the PostgreSQL CI `Linux - Autoconf` job |
| `linux-meson-32` | Dockerized equivalent of the PostgreSQL CI `Linux - Meson (32-bit)` job |
| `linux-meson-64` | Dockerized equivalent of the PostgreSQL CI `Linux - Meson (64-bit)` job |
| `compilerwarnings` | Dockerized equivalent of the PostgreSQL CI `CompilerWarnings` job |

By default this tests the selected worktree's committed `HEAD` via `git archive`
inside the PostgreSQL CI image, so uncommitted local edits are not included.
Use `--ci-use-current` when you intentionally want to test the working tree
contents directly. The macOS and Windows jobs in PostgreSQL CI are not covered
by this Docker helper; they need their native GitHub runners or equivalent VMs.

```bash
# Test the committed HEAD of a managed worktree
~/build --ci-flavor linux-autoconf --worktree-name dev

# Run the 64-bit Meson Linux flavor
~/build --ci-flavor linux-meson-64 --worktree-name dev

# Run compiler warnings and documentation checks
~/build --ci-flavor compilerwarnings --worktree-name dev

# Test the checkout you are currently in
~/build --ci-flavor linux-autoconf

# Test uncommitted working-tree contents directly
~/build --ci-flavor linux-autoconf --ci-use-current

# Open a shell in the prepared CI container
~/build --ci-flavor linux-autoconf --worktree-name dev --ci-shell
```

CI-specific flags:

| Option | Description |
|---|---|
| `--ci-ref REF` | Test an explicit committed ref instead of `HEAD` |
| `--ci-use-current` | Bind-mount and test the working tree contents directly |
| `--ci-shell` | Open a shell in the prepared container instead of running the job |
| `--ci-keep` | Keep the temporary exported source directory after success |
| `--ci-image IMAGE` | Override the Docker image |
| `--ci-build-jobs N` | Override build parallelism |
| `--ci-test-jobs N` | Override test parallelism |
| `--ci-check TARGET` | Override the make check target |
| `--ci-checkflags FLAGS` | Override make check flags |
| `--ci-docker-arg ARG` | Pass an extra argument to `docker run`; repeat as needed |

### Options

| Option | Default | Description |
|---|---|---|
| `--prefix PATH` | `~/pgdev/installations` | Root directory for all build artifacts, data, and scripts |
| `--repo-url URL` | PostgreSQL GitHub mirror | Git URL to clone from (origin remote) |
| `--upstream-url URL` | same as `--repo-url` | Upstream repository URL (for the upstream remote). If omitted, `--repo-url` is used for both origin and upstream. Only needed when working with a fork. |
| `--sync-fork` | off | Sync fork's master with upstream/master (fetch, ff-merge, push) and exit. Requires `--upstream-url` to differ from `--repo-url`. |
| `--branch NAME` | — | Branch to check out (mutually exclusive with --tag and --commit) |
| `--tag NAME` | — | Tag to check out (mutually exclusive with --branch and --commit) |
| `--commit HASH` | — | Commit hash to check out (mutually exclusive with --branch and --tag) |
| `--patch FILES` | — | Patch file(s) or glob pattern to apply via `git am --3way` |
| `--meson-flags FLAGS` | — | Extra flags passed to `meson setup` |
| `--configure-flags FLAGS` | — | Extra flags passed to `./configure` when using `--build-system make` |
| `--build-system` | `meson` | Build system to use: `meson` or `make` |
| `--worktree-name NAME` | — | **Required.** Name for the worktree, installation, data directory, and activation script |
| `--create-pg-fdw` | off | Set up postgres_fdw with a loopback foreign server on the primary instance |
| `--create-replica NAME` | — | Also build and start a replica instance with the given NAME (port + 20) |
| `--skip-build` | off | Skip the build step (re-init DB only) |
| `--worktree-only` | off | Only create worktree, skip build and DB initialization |
| `--build-only` | off | Build the source but skip DB initialization and startup (no cluster) |
| `--force-worktree` | off | Force recreation of worktree even if it exists |
| `--capture-output` | off | Suppress stdout/stderr from build commands |
| `--port PORT` | `5432` | Port for the primary instance |
| `-l, --list-worktrees` | — | List existing worktrees and exit |
| `--clean-worktrees` | — | Delete all worktrees and exit |
| `--remove-worktree NAME` | — | Remove a single worktree by name (as shown by `--list-worktrees`) and exit |
| `--update-source` | — | Fetch latest changes from all remotes in source directory and exit |
| `--recreate-activate-script` | off | Only recreate the activation script (cannot be used with other options) |
| `--verify-series` | off | Build and test every commit in `base..HEAD` standalone, then exit. Requires `--worktree-name`. See below. |
| `--base REF` | merge-base with `origin/master` | Base ref for `--verify-series` |
| `--coverage` | off | Enable Meson coverage instrumentation |
| `--indent MODE` | — | Run pgindent on changed files. Mode: `head`, `staged`, `unstaged`, a commit hash, or a number N to run on the last N commits individually (amending each) |
| `--continue` | off | Continue a previously failed `git am` and proceed with the build |

## Examples

Build from the `master` branch:
```bash
python pg_build.py --worktree-name master --branch master
```

Build a specific release tag with a custom prefix:
```bash
python pg_build.py --worktree-name rel16 --tag REL_16_0 --prefix ~/pg/16
```

Build from a specific commit hash:
```bash
python pg_build.py --worktree-name mycommit --commit abc123def456
```

Build with Meson flags and apply a patch:
```bash
python pg_build.py --worktree-name my-feature --branch master \
  --meson-flags "-Dcassert=true -Dtap_tests=enabled" \
  --patch ~/patches/my-feature.patch
```

Apply multiple patches (shell glob expansion):
```bash
python pg_build.py --worktree-name patchwork --branch master --patch ~/Downloads/*.patch
```

If a patch conflict occurs during `--patch`, resolve it manually in the worktree, then resume:
```bash
# 1. Fix conflicts in the worktree, then:
#    git add <resolved files>
# 2. Continue the build:
python pg_build.py --worktree-name patchwork --continue
```

Build primary + postgres_fdw + replica instances:
```bash
python pg_build.py --worktree-name dev --branch master \
  --create-pg-fdw --create-replica dev-replica
```

Re-initialize the database without rebuilding:
```bash
python pg_build.py --worktree-name dev --branch master --skip-build
```

List all existing worktrees:
```bash
python pg_build.py -l
# or
python pg_build.py --list-worktrees
```

Delete all worktrees:
```bash
python pg_build.py --clean-worktrees
```

Remove a single worktree (and its pghome, pgdata, and activation scripts):
```bash
python pg_build.py --remove-worktree my-feature
```

Create worktree only (no build or DB init):
```bash
python pg_build.py --worktree-name my-feature --branch master --worktree-only
```

Build only (compile the source but do not init/start a cluster):
```bash
python pg_build.py --worktree-name my-feature --branch master --build-only
```

Build with coverage instrumentation, then use the generated activation helper:
```bash
python pg_build.py --worktree-name coverage --branch master --coverage
source ~/pgdev/installations/activate_coverage.sh
pg_test regress/regress
pg_coverage_report
```

Update source repository (fetch latest from all remotes):
```bash
python pg_build.py --update-source
```

Sync fork's master with upstream (fetch upstream, fast-forward merge, push to origin):
```bash
python pg_build.py --sync-fork
```

Force recreation of worktree (useful when switching branches or after manual changes):
```bash
python pg_build.py --worktree-name dev --branch master --skip-build --force-worktree
```

Run pgindent on the last 4 commits individually (amending formatting fixes into each):
```bash
python pg_build.py --worktree-name dev --indent 4
```

Run pgindent on files changed in the HEAD commit:
```bash
python pg_build.py --worktree-name dev --indent head
```

Recreate activation script only (useful after changing ports or paths):
```bash
python pg_build.py --worktree-name dev --recreate-activate-script --port 5432
```

Verify every commit in a patch series builds and tests cleanly on its own
(what a reviewer checks with `git rebase <base> --exec`):
```bash
# Base defaults to the merge-base with origin/master:
python pg_build.py --worktree-name dev --verify-series

# Or specify an explicit base:
python pg_build.py --worktree-name dev --verify-series --base origin/master
```

## Directory Layout

After running, the `--prefix` directory will contain:

```
<prefix>/
├── source/                  # Cloned repository
├── worktrees/
│   └── dev/                 # Git worktree (named by --worktree-name)
├── pghome/
│   └── dev/                 # Installed PostgreSQL binaries
├── pgdata/
│   └── dev/                 # Initialized data directory
└── activate_dev.sh          # Shell activation script
```

With `--create-pg-fdw` and `--create-replica dev-replica`, additional directories and scripts are created:
```
<prefix>/
├── worktrees/
│   ├── dev/
│   └── dev-replica/
├── pghome/
│   ├── dev/
│   └── dev-replica/
├── pgdata/
│   ├── dev/
│   └── dev-replica/
├── activate_dev.sh
└── activate_dev-replica.sh
```

## Activation Scripts

Each instance gets a generated activation script (e.g. `activate_dev.sh`) that sets up your shell environment:

```bash
source ~/pgdev/installations/activate_dev.sh
```

This exports `PGHOME`, `PGDATA`, `PGPORT`, `PATH`, `LD_LIBRARY_PATH`, and
several convenience aliases and functions. Meson activation scripts also export
`PGBUILD_BUILD_DIR`, so the helper functions work from any current directory.

| Alias / Function | Description |
|---|---|
| `PG_START` | Start the cluster |
| `PG_STOP` | Stop the cluster |
| `pg_check_extension <name>` | Run setup + extension test suite |
| `pg_check_world` | Run all tests |
| `pg_build_docs` | Build documentation via `ninja docs` |
| `pg_build [target ...]` | Build/install the current tree; Meson defaults to `ninja install install-test-files` |
| `pg_list_tests` | List all available Meson test targets |
| `pg_test [meson-test-name ...]` | Meson: run all tests, or specific entries such as `regress/regress`, `recovery/049_wait_for_lsn`, or `subscription/036_sequences` |
| `pg_run_suite <name>` | Remove `tmp_install` (force initdb-template regen), then run the setup suite followed by a named test suite |
| `pg_run_pg_regress_one <meson-test-name> <test> [test ...]` | Meson: regenerate `tmp_install`, run setup, then run specific cases from a `pg_regress`-backed entry |
| `pg_run_regress_one <test> [test ...]` | Meson: convenience wrapper for `pg_run_pg_regress_one regress/regress ...` |
| `pg_run_isolation_one <test> [test ...]` | Meson: convenience wrapper for `pg_run_pg_regress_one isolation/isolation ...` |
| `pg_coverage_report` | Meson: build HTML coverage output and print the report path |
| `pg_coverage_reset` | Meson: delete coverage counter files |

## Commit Hooks

The `git_hooks/` directory ships two hooks that enforce PostgreSQL commit
conventions:

| Hook | Enforces |
|---|---|
| `pre-commit` | No non-ASCII bytes in staged additions (PostgreSQL is ASCII-only) |
| `commit-msg` | Subject line ≤ 72 chars, ASCII-only message, no agent-attribution / co-author trailers |

They are installed by pointing a repo's `core.hooksPath` at the hooks
directory. Run `install-hooks.sh` once against the source repo; the hooks then
apply to that repo **and every worktree under it — and to nothing else on the
machine** (worktrees share the parent repo's config):

```bash
./install-hooks.sh HOOKS_DIR SOURCE_REPO
# e.g.
./install-hooks.sh ~/Development/pg-build/git_hooks ~/pgdev/installations/source
```

Re-run it whenever you create a new source repo, or to repoint an existing one
(e.g. on a different machine where the paths differ).

Bypass a hook for a single commit with `git commit --no-verify` (e.g. a
legitimate `Co-authored-by:` when code is genuinely derived from another
contributor). To remove entirely:
```bash
git -C <source-repo> config --unset core.hooksPath
```

## Port Assignments

| Instance | Port |
|---|---|
| Primary | `--port` (default 5432) |
| FDW | Same as primary (loopback) |
| Replica | `--port + 20` (default 5452) |

## install_test_module.sh

`install_test_module.sh` installs a built PostgreSQL test module from
`src/test/modules/<module>` into the PostgreSQL installation selected by
`pg_config`. It is useful when a test module was built in-tree and you want it
available in an installed development instance.

### Usage

```bash
./install_test_module.sh [options] <module>
```

| Option | Default | Description |
|---|---|---|
| `--repo-root PATH` | `$PGSRC` or nearest parent containing `src/test/modules` | PostgreSQL source tree root |
| `--pg-config PATH` | Matching managed worktree install, `$PG_CONFIG`, or `pg_config` on `PATH` | Target installation |
| `--build-dir PATH` | First matching build dir under the repo containing the module artifact | Meson build directory |
| `-n, --dry-run` | off | Print install commands without executing them |
| `-h, --help` | — | Show help |

Examples:

```bash
# From inside a PostgreSQL source tree
./install_test_module.sh injection_points

# Point at a managed worktree and install into the matching pghome
./install_test_module.sh \
  --repo-root ~/pgdev/installations/worktrees/dev \
  injection_points

# Choose the target installation explicitly
./install_test_module.sh \
  --pg-config ~/pgdev/installations/pghome/dev/bin/pg_config \
  injection_points
```

## patch_download.py

A helper script to download patch files from the [PostgreSQL Commitfest](https://commitfest.postgresql.org/) by entry ID (or full URL) and filename prefix.

### Usage

```bash
python patch_download.py <cfentry_or_url> <prefix> [download_dir]
```

| Argument | Required | Default | Description |
|---|---|---|---|
| `cfentry_or_url` | yes | — | Commitfest patch entry ID or full commitfest URL |
| `prefix` | yes | — | Filename prefix to match (only links whose filename starts with this are downloaded) |
| `download_dir` | no | `~/Downloads` | Directory to save downloaded patches |

### Examples

Download patches from commitfest entry 5338 matching prefix `v3-`:
```bash
python patch_download.py 5338 v3-
```

Download using a full commitfest URL:
```bash
python patch_download.py https://commitfest.postgresql.org/patch/5338 v3-
```

Download to a custom directory:
```bash
python patch_download.py 5338 v3- ~/patches
```

Combine with `pg_build.py` to download and apply in one go:
```bash
python patch_download.py 5338 v3- ~/patches
python pg_build.py --worktree-name my-patch --branch master --patch ~/patches/v3-*.patch
```

## Notes

- Each run **destroys and recreates** the build directory and data directory for the affected instances. It is not intended for production use.
- Worktrees are preserved by default for efficiency. Use `--force-worktree` to recreate them (useful when switching branches or after manual changes).
- The script stops any existing PostgreSQL process on the target port before reinitializing.
- `--patch` accepts multiple files or a glob pattern; patches are applied in sorted order via `git am --3way`. If a conflict occurs, resolve it in the worktree and run `--continue` to finish applying remaining patches and proceed with the build.
- `--verify-series` checks out each commit in `base..HEAD` in a **detached HEAD** (it never rewrites history), builds and tests it, and restores your original branch when done. It reuses the existing `build/` directory, refuses to run with uncommitted **tracked** changes (untracked files are fine), removes `tmp_install` before each commit's setup suite to force initdb-template regeneration, and stops at the first failing commit.
- Both `--branch` and `--tag` are mapped to `origin/<ref>` when creating the worktree.
- All instance names (`--worktree-name`, `--create-replica`) must be unique — the script will error if any names collide.
- `--upstream-url` is only needed when working with a fork. If omitted, `--repo-url` is used for both the origin and upstream remotes. When working directly with the official repository (no fork), simply set `--repo-url` and leave `--upstream-url` unset.
- `build` is the tracked opinionated wrapper used on this machine. `example.sh` remains a generic template if you want to create a different local wrapper.
