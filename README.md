# pg_build

A script for automating local PostgreSQL development environment setup — cloning, building, initializing, and starting one or more PostgreSQL instances from source using Git worktrees.

## Features

- Clones the PostgreSQL source repository and manages Git worktrees
- Builds PostgreSQL from source using **Meson** (default) or **Make**
- Optionally applies patches via `git am`
- Initializes and starts a primary PostgreSQL cluster, with optional postgres_fdw and replica instances
- Generates a shell activation script per instance with environment variables and helper functions

## Requirements

- Python 3.7+
- Git
- `meson` + `ninja` (or `make` / `autoconf` toolchain)
- Standard PostgreSQL build dependencies (e.g. `libreadline-dev`, `zlib1g-dev`, etc.)
- `fuser` (used as a fallback to kill processes on a port)

## Usage

```bash
python pg_build.py [OPTIONS]
```

### Options

| Option | Default | Description |
|---|---|---|
| `--prefix PATH` | `~/pgdev/installations` | Root directory for all build artifacts, data, and scripts |
| `--repo-url URL` | PostgreSQL GitHub mirror | Git URL to clone from |
| `--branch NAME` | — | Branch to check out (mutually exclusive with --tag and --commit) |
| `--tag NAME` | — | Tag to check out (mutually exclusive with --branch and --commit) |
| `--commit HASH` | — | Commit hash to check out (mutually exclusive with --branch and --tag) |
| `--patch FILES` | — | Patch file(s) or glob pattern to apply via `git am --3way` |
| `--meson-flags FLAGS` | — | Extra flags passed to `meson setup` |
| `--build-system` | `meson` | Build system to use: `meson` or `make` |
| `--worktree-name NAME` | — | **Required.** Name for the worktree, installation, data directory, and activation script |
| `--create-pg-fdw NAME` | — | Also build and start a postgres_fdw instance with the given NAME (port + 10) |
| `--create-replica NAME` | — | Also build and start a replica instance with the given NAME (port + 20) |
| `--skip-build` | off | Skip the build step (re-init DB only) |
| `--worktree-only` | off | Only create worktree, skip build and DB initialization |
| `--force-worktree` | off | Force recreation of worktree even if it exists |
| `--capture-output` | off | Suppress stdout/stderr from build commands |
| `--port PORT` | `5432` | Port for the primary instance |
| `-l, --list-worktrees` | — | List existing worktrees and exit |
| `--clean-worktrees` | — | Delete all worktrees and exit |
| `--remove-worktree NAME` | — | Remove a single worktree by name (as shown by `--list-worktrees`) and exit |
| `--update-source` | — | Fetch latest changes from all remotes in source directory and exit |
| `--recreate-activate-script` | off | Only recreate the activation script (cannot be used with other options) |
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
  --create-pg-fdw dev-fdw --create-replica dev-replica
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

Update source repository (fetch latest from all remotes):
```bash
python pg_build.py --update-source
```

Force recreation of worktree (useful when switching branches or after manual changes):
```bash
python pg_build.py --worktree-name dev --branch master --skip-build --force-worktree
```

Recreate activation script only (useful after changing ports or paths):
```bash
python pg_build.py --worktree-name dev --recreate-activate-script --port 5432
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

With `--create-pg-fdw dev-fdw` and `--create-replica dev-replica`, additional directories and scripts are created:
```
<prefix>/
├── worktrees/
│   ├── dev/
│   ├── dev-fdw/
│   └── dev-replica/
├── pghome/
│   ├── dev/
│   ├── dev-fdw/
│   └── dev-replica/
├── pgdata/
│   ├── dev/
│   ├── dev-fdw/
│   └── dev-replica/
├── activate_dev.sh
├── activate_dev-fdw.sh
└── activate_dev-replica.sh
```

## Activation Scripts

Each instance gets a generated activation script (e.g. `activate_dev.sh`) that sets up your shell environment:

```bash
source ~/pgdev/installations/activate_dev.sh
```

This exports `PGHOME`, `PGDATA`, `PGPORT`, `PATH`, `LD_LIBRARY_PATH`, and several convenience aliases and functions:

| Alias / Function | Description |
|---|---|
| `PG_START` | Start the cluster |
| `PG_STOP` | Stop the cluster |
| `pg_check_extension <name>` | Run setup + extension test suite |
| `pg_check_world` | Run all tests |
| `pg_build_docs` | Build documentation via `ninja docs` |
| `pg_list_tests` | List all available Meson test targets |
| `pg_run_suite <name>` | Run setup suite then a named test suite |

## Port Assignments

| Instance | Port |
|---|---|
| Primary | `--port` (default 5432) |
| FDW | `--port + 10` (default 5442) |
| Replica | `--port + 20` (default 5452) |

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
- Both `--branch` and `--tag` are mapped to `origin/<ref>` when creating the worktree.
- All instance names (`--worktree-name`, `--create-pg-fdw`, `--create-replica`) must be unique — the script will error if any names collide.
