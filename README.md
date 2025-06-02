# pg_build

A script for automating local PostgreSQL development environment setup — cloning, building, initializing, and starting one or more PostgreSQL instances from source using Git worktrees.

## Features

- Clones the PostgreSQL source repository and manages Git worktrees
- Builds PostgreSQL from source using **Meson** (default) or **Make**
- Optionally applies patches via `git am`
- Initializes and starts a primary PostgreSQL cluster, with optional FDW and replica instances
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
| `--branch NAME` | — | Branch to check out (required if `--tag` not set) |
| `--tag NAME` | — | Tag to check out (required if `--branch` not set) |
| `--patch GLOB` | — | Glob pattern of `.patch` files to apply via `git am` |
| `--meson-flags FLAGS` | — | Extra flags passed to `meson setup` |
| `--build-system` | `meson` | Build system to use: `meson` or `make` |
| `--worktree-name NAME` | — | Optional prefix for naming worktree directories |
| `--create-fdw` | off | Also build and start an FDW instance (port + 10) |
| `--create-replica` | off | Also build and start a replica instance (port + 20) |
| `--skip-build` | off | Skip the build step (re-init DB only) |
| `--capture-output` | off | Suppress stdout/stderr from build commands |
| `--port PORT` | `5432` | Port for the primary instance |

## Examples

Build from the `master` branch:
```bash
python pg_build.py --branch master
```

Build a specific release tag with a custom prefix:
```bash
python pg_build.py --tag REL_16_0 --prefix ~/pg/16
```

Build with Meson flags and apply a patch:
```bash
python pg_build.py --branch master \
  --meson-flags "-Dcassert=true -Dtap_tests=enabled" \
  --patch ~/patches/my-feature.patch
```

Build primary + FDW + replica instances:
```bash
python pg_build.py --branch master --create-fdw --create-replica
```

Re-initialize the database without rebuilding:
```bash
python pg_build.py --branch master --skip-build
```

## Directory Layout

After running, the `--prefix` directory will contain:

```
<prefix>/
├── source/                  # Cloned repository
├── worktrees/
│   └── src_primary/         # Git worktree for the primary build
├── pghome_primary/          # Installed PostgreSQL binaries
├── pgdata/
│   └── primary/             # Initialized data directory
└── activate_primary.sh      # Shell activation script
```

With `--create-fdw` or `--create-replica`, additional `pghome_fdw/`, `pghome_replica/`, `pgdata/fdw/`, `pgdata/replica/`, and corresponding activation scripts are created.

## Activation Scripts

Each instance gets a generated activation script (e.g. `activate_primary.sh`) that sets up your shell environment:

```bash
source ~/pgdev/installations/activate_primary.sh
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

## Notes

- Each run **destroys and recreates** the worktree, build, and data directory for the affected instances. It is not intended for production use.
- The script stops any existing PostgreSQL process on the target port before reinitializing.
- `--patch` accepts a glob pattern; patches are applied in sorted order.
- Both `--branch` and `--tag` are mapped to `origin/<ref>` when creating the worktree.
