# PostgreSQL Multi-Instance Build and Setup Script

> ⚠️ **Notice**
>
> This project is provided **for non-production use only**.
> It lacks the guarantees required for secure, stable, or scalable deployment in production systems.

This Python script automates building PostgreSQL from source (either a `.tar.gz` source archive or a GitHub branch/tag), optionally applies patches, and sets up multiple PostgreSQL clusters: a primary, a foreign data wrapper (FDW), and a replica. Each PostgreSQL build and cluster runs isolated in its own installation and data directory.

---

## Features

- Build PostgreSQL from source archive or latest GitHub source.
- Support for specifying branches or tags for each instance independently.
- Apply one or multiple patch files to the source before building.
- Build three separate PostgreSQL installations simultaneously:
  - **Primary** server (main database).
  - **FDW** server (for foreign data wrapper testing).
  - **Replica** server (streaming replication replica).
- Initialize, activate, and start each cluster with proper environment variables.
- Clean up old builds and data directories before rebuild.
- Download and create a PostgreSQL source tarball from the latest GitHub if needed.
- Works on Linux and macOS (Intel/ARM).
- Control ports independently (default 5432 for primary, 5442 for FDW, 5452 for replica).

---

## Requirements

- Python 3.7+
- Git
- Meson build system and Ninja build tool installed and available in your `PATH`.
- A C compiler and dependencies required to build PostgreSQL.
- `pg_ctl`, `initdb`, `pg_basebackup` tools available in built PostgreSQL (automatically included).

---

## Usage

```bash
python3 build_pg.py [OPTIONS]
```

### Main options

| Option                  | Description                                      | Default/Notes                       |
|-------------------------|------------------------------------------------|-----------------------------------|
| `--prefix PATH`         | Base directory for installs and data directories | `~/pgdev/installations` (Linux)<br>`~/Documents/pgdev/installations` (macOS) |
| `--source PATH`         | PostgreSQL source tarball (`.tar.gz`)            | `postgres.tar.gz`                  |
| `--patch GLOB`          | Glob pattern for patch files to apply            | None                             |
| `--meson-flags STR`     | Additional flags to pass to meson setup          | None                             |
| `--branch STR`          | Git branch to checkout for all builds            | None                             |
| `--tag STR`             | Git tag to checkout for all builds               | None                             |
| `--primary-branch STR`  | Git branch for primary build (overrides `--branch`) | None                             |
| `--primary-tag STR`     | Git tag for primary build (overrides `--tag`)   | None                             |
| `--fdw-branch STR`      | Git branch for FDW build                          | None                             |
| `--fdw-tag STR`         | Git tag for FDW build                             | None                             |
| `--replica-branch STR`  | Git branch for replica build                      | None                             |
| `--replica-tag STR`     | Git tag for replica build                         | None                             |
| `--skip-build`          | Skip build, only reset/stop existing clusters    | False                            |
| `--create-fdw`          | Create and start FDW cluster                       | False                            |
| `--create-replica`      | Create and start replica cluster                   | False                            |
| `--port INT`            | Primary cluster port                              | 5432                             |
| `--capture-output`      | Capture and display build output                  | False                            |
| `--update-tarball PATH` | Download latest PostgreSQL source and save as tarball, then exit | None                 |

---

## Examples

### Build and start primary only

```bash
python3 build_pg.py --source postgresql-15.3.tar.gz --create-fdw --create-replica
```

### Build primary from tag `REL_15_3`, FDW and replica from branch `feature-x`

```bash
python3 build_pg.py   --primary-tag REL_15_3   --fdw-branch feature-x --create-fdw   --replica-branch feature-x --create-replica
```

### Skip build, reset data directories, and restart all clusters

```bash
python3 build_pg.py --skip-build --create-fdw --create-replica
```

### Download latest PostgreSQL source tarball

```bash
python3 build_pg.py --update-tarball latest_postgres.tar.gz
```

---

## Installation Layout

The script organizes files under the base prefix directory:

```
${prefix}/
  pghome_primary/       # Primary PostgreSQL installation prefix (bin/, lib/, etc)
  pghome_fdw/           # FDW PostgreSQL installation prefix
  pghome_replica/       # Replica PostgreSQL installation prefix
  source/               # Extracted PostgreSQL sources per build (src_primary, src_fdw, src_replica)
  pgdata/
    primary/            # Data directory for primary cluster
    fdw/                # Data directory for FDW cluster
    replica/            # Data directory for replica cluster
  activate_primary.sh   # Script to activate primary env vars
  activate_fdw.sh       # Script to activate FDW env vars
  activate_replica.sh   # Script to activate replica env vars
```

---

## Notes

- Make sure the PostgreSQL source tarball exists if not using `--update-tarball`.
- Build dependencies must be installed (Meson, Ninja, C compiler, Git).
- You may customize `--meson-flags` to pass additional build options.
- Patching supports multiple patch files matched by a glob pattern.
- The script ensures environment isolation between the three PostgreSQL builds.
- Each cluster runs on a different port (`--port` for primary, `--port+10` for FDW, `--port+20` for replica).

---

## License

This script is provided as-is, with no warranty.

---

## Author

Sami Imseih

---

If you need help or want to extend this script, feel free to open an issue or ask!

