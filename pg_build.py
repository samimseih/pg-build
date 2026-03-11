#!/usr/bin/env python3

import os
import sys
import shutil
import subprocess
import argparse
import logging
import glob
import shlex
from pathlib import Path
from typing import Optional, Union

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

# -----------------------------
# Utility runner
# -----------------------------
def run(command: Union[str, list], **kwargs) -> subprocess.CompletedProcess:
    if isinstance(command, list):
        log.info(f"🔀 {' '.join(shlex.quote(str(c)) for c in command)}")
    else:
        log.info(f"🔀 {command}")

    return subprocess.run(
        command,
        shell=isinstance(command, str),
        check=kwargs.get("check", True),
        cwd=kwargs.get("cwd"),
        env=kwargs.get("env"),
        stdout=subprocess.PIPE if kwargs.get("capture_output") else None,
        stderr=subprocess.PIPE if kwargs.get("capture_output") else None,
        text=True,
    )

# -----------------------------
# Stop any running PostgreSQL instance
# -----------------------------
def stop_postgres(pg_home: Path, pgdata: Path, port: int):
    if not pgdata.exists():
        return

    log.info(f"🛑 Stopping PostgreSQL cluster at {pgdata} (port {port}) if running...")
    pg_ctl_path = pg_home / "bin/pg_ctl"
    env = os.environ.copy()
    env["PGDATA"] = str(pgdata)

    try:
        if pg_ctl_path.exists():
            run([str(pg_ctl_path), "-D", str(pgdata), "stop", "-m", "fast"], env=env, check=False)
    except Exception:
        pass

    # Kill any remaining processes on the port (macOS compatible)
    try:
        result = subprocess.run(
            f"lsof -ti tcp:{port}",
            shell=True,
            capture_output=True,
            text=True,
            check=False
        )
        if result.stdout.strip():
            pids = result.stdout.strip().split('\n')
            for pid in pids:
                subprocess.run(f"kill -9 {pid}", shell=True, check=False)
    except Exception:
        pass

    # Remove stale PID file if it exists
    pid_file = pgdata / "postmaster.pid"
    if pid_file.exists():
        try:
            pid_file.unlink()
            log.info(f"🧹 Removed stale PID file: {pid_file}")
        except Exception:
            pass

# -----------------------------
# Worktree setup
# -----------------------------
def setup_worktree(repo_root: Path,
                   worktree_dir: Path,
                   branch: Optional[str],
                   tag: Optional[str],
                   commit: Optional[str],
                   repo_url: str) -> Path:
    repo_root = repo_root.resolve()
    worktree_dir = worktree_dir.resolve()
    repo_root.parent.mkdir(parents=True, exist_ok=True)

    # Clone repo if missing
    if not repo_root.exists() or not (repo_root / ".git").exists():
        if repo_root.exists():
            shutil.rmtree(repo_root)
        log.info(f"⬇️ Cloning repository into {repo_root}")
        run(["git", "clone", repo_url, str(repo_root)])

    # Ensure upstream remote exists
    existing_remotes = subprocess.run(
        ["git", "remote"], cwd=repo_root, capture_output=True, text=True
    ).stdout.splitlines()
    if "upstream" not in existing_remotes:
        log.info("🔗 Adding upstream remote")
        run(["git", "remote", "add", "upstream", repo_url], cwd=repo_root)
        run(["git", "fetch", "upstream"], cwd=repo_root)

    checkout_ref = branch or tag or commit
    if not checkout_ref:
        log.error("❌ Must supply branch, tag, or commit.")
        sys.exit(1)

    # Ensure repo is ready
    run(["git", "status"], cwd=repo_root)
    run(["git", "fetch", "--all"], cwd=repo_root)
    run(["git", "worktree", "prune"], cwd=repo_root)

    # Remove existing worktree if present
    if worktree_dir.exists():
        run(["git", "worktree", "remove", "--force", str(worktree_dir)], cwd=repo_root, check=False)
        shutil.rmtree(worktree_dir, ignore_errors=True)

    # -----------------------------
    # Check if branch is already used in another worktree
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=repo_root,
        capture_output=True,
        text=True
    ).stdout.splitlines()

    branches_in_use = set()
    for line in result:
        if line.startswith("branch refs/heads/"):
            branches_in_use.add(line.split("/")[-1])

    # For commits, create detached HEAD worktree
    if commit:
        run(["git", "worktree", "add", "--detach", str(worktree_dir), checkout_ref], cwd=repo_root)
    elif checkout_ref in branches_in_use:
        unique_branch = f"{checkout_ref}_{worktree_dir.name}"
        log.info(f"⚠️ Branch {checkout_ref} is already used in another worktree, creating unique branch: {unique_branch}")

        # ---- FIX: delete existing local branch before recreating ----
        existing_branches = subprocess.run(
            ["git", "branch", "--format", "%(refname:short)"],
            cwd=repo_root,
            capture_output=True,
            text=True
        ).stdout.splitlines()

        if unique_branch in existing_branches:
            log.info(f"🧹 Deleting existing local branch {unique_branch}")
            run(["git", "branch", "-D", unique_branch], cwd=repo_root)
        # -------------------------------------------------------------

        run(["git", "worktree", "add", "-b", unique_branch,
             str(worktree_dir), f"origin/{checkout_ref}"], cwd=repo_root)
    else:
        run(["git", "worktree", "add", str(worktree_dir), checkout_ref], cwd=repo_root)

    log.info(f"🔀 Worktree ready at {worktree_dir}")
    return worktree_dir

# -----------------------------
# Activation script
# -----------------------------
def activate_script(pg_home: Path,
                    pgdata: Path,
                    port: int,
                    script_name: Path,
                    pg_bsd_indent_path: Path,
                    worktree_name: Optional[str] = None) -> Path:
    if worktree_name:
        script_name = script_name.with_name(f"{script_name.stem}_{worktree_name}{script_name.suffix}")

    exports = [
        f"export PGHOME={pg_home}",
        f"export PATH={pg_home}/bin:{pg_bsd_indent_path}:$PATH",
        f"export LD_LIBRARY_PATH={pg_home}/lib",
        f"export PGDATA={pgdata}",
        f"export PGUSER=postgres",
        f"export PGDATABASE=postgres",
        f"export PGPORT={port}",
        f"alias PG_START=\"pg_ctl -D {pgdata} start\"",
        f"alias PG_STOP=\"pg_ctl -D {pgdata} stop\"",
        "",
        "# Build/Test helper functions",
        "function pg_check_extension() {",
        "    meson test -q --print-errorlogs --suite setup --suite $1",
        "}",
        "",
        "function pg_check_world() {",
        "    meson test -q --print-errorlogs",
        "}",
        "",
        "function pg_build_docs() {",
        "    ninja docs",
        "}",
        "",
        "function pg_list_tests() {",
        "    meson test --list",
        "}",
        "",
        "function pg_run_suite() {",
        "    meson test -v -C . --suite setup",
        "    meson test -v -C . --suite \"$1\"",
        "}",
    ]

    script_name.write_text("\n".join(exports) + "\n")
    log.info(f"✅ Wrote activation script: {script_name}")

    os.environ["PGHOME"] = str(pg_home)
    os.environ["PATH"] = f"{pg_home}/bin:{pg_bsd_indent_path}:" + os.environ.get("PATH", "")
    os.environ["LD_LIBRARY_PATH"] = f"{pg_home}/lib"
    os.environ["PGDATA"] = str(pgdata)
    os.environ["PGUSER"] = "postgres"
    os.environ["PGDATABASE"] = "postgres"
    os.environ["PGPORT"] = str(port)

    return script_name

# -----------------------------
# Init & start DB
# -----------------------------
def init_db(pg_home: Path, pgdata: Path, port: int, env: dict):
    if pgdata.exists():
        shutil.rmtree(pgdata)
    pgdata.mkdir(parents=True, exist_ok=True)
    run([str(pg_home / "bin/initdb"), "-D", str(pgdata), "-U", "postgres"], env=env)
    conf_file = pgdata / "postgresql.conf"
    conf_file.write_text(conf_file.read_text() + f"\nport = {port}\nlogging_collector = 'on'\n")

def start_db(pg_home: Path, pgdata: Path, env: dict):
    run([str(pg_home / "bin/pg_ctl"), "-D", str(pgdata), "-l", str(pgdata / "logfile"), "start"], env=env)

# -----------------------------
# Setup streaming replication
# -----------------------------
def setup_replication(primary_home: Path, primary_data: Path, primary_port: int,
                      replica_home: Path, replica_data: Path, replica_port: int):
    import time

    log.info("🔧 Setting up streaming replication...")

    # 1. Configure primary for replication
    log.info("📝 Configuring primary server for replication...")
    primary_conf = primary_data / "postgresql.conf"
    with open(primary_conf, "a") as f:
        f.write("\n# Replication settings\n")
        f.write("wal_level = replica\n")
        f.write("max_wal_senders = 3\n")
        f.write("wal_keep_size = 64MB\n")

    # Add replication entry to pg_hba.conf
    primary_hba = primary_data / "pg_hba.conf"
    hba_content = primary_hba.read_text()
    if "replication" not in hba_content:
        with open(primary_hba, "a") as f:
            f.write("host    replication     all             127.0.0.1/32            trust\n")

    # Restart primary to apply changes
    log.info("🔄 Restarting primary to apply replication settings...")
    env = os.environ.copy()
    env["PATH"] = f"{primary_home}/bin:" + env.get("PATH", "")
    run([str(primary_home / "bin/pg_ctl"), "-D", str(primary_data), "restart",
         "-l", str(primary_data / "logfile")], env=env)

    time.sleep(2)

    # 2. Stop replica and remove its data
    log.info("🛑 Stopping replica...")
    stop_postgres(replica_home, replica_data, replica_port)

    log.info("🧹 Cleaning replica data directory...")
    if replica_data.exists():
        shutil.rmtree(replica_data)
    replica_data.mkdir(parents=True, exist_ok=True)
    # Set proper permissions for PostgreSQL
    os.chmod(replica_data, 0o700)

    # 3. Create base backup from primary
    log.info("📦 Creating base backup from primary...")
    run([str(primary_home / "bin/pg_basebackup"),
         "-h", "localhost",
         "-p", str(primary_port),
         "-U", "postgres",
         "-D", str(replica_data),
         "-Fp", "-Xs", "-P", "-R"], env=env)

    # 4. Configure replica
    log.info("📝 Configuring replica server...")
    replica_conf = replica_data / "postgresql.conf"
    with open(replica_conf, "a") as f:
        f.write(f"\n# Replica-specific settings\n")
        f.write(f"port = {replica_port}\n")
        f.write("hot_standby = on\n")

    # 5. Start replica
    log.info("🚀 Starting replica...")
    env["PATH"] = f"{replica_home}/bin:" + env.get("PATH", "")
    try:
        run([str(replica_home / "bin/pg_ctl"), "-D", str(replica_data), "start",
             "-l", str(replica_data / "logfile")], env=env)
        time.sleep(2)
    except subprocess.CalledProcessError as e:
        log.error(f"❌ Failed to start replica. Check logfile at {replica_data / 'logfile'}")
        # Try to show the last few lines of the logfile
        logfile = replica_data / "logfile"
        if logfile.exists():
            log.error("Last 20 lines of replica logfile:")
            with open(logfile) as f:
                lines = f.readlines()
                for line in lines[-20:]:
                    log.error(f"  {line.rstrip()}")
        raise

    # 6. Verify replication
    log.info("")
    log.info("✅ Replication setup complete!")
    log.info("")
    log.info("Verification:")
    log.info("-------------")

    try:
        result = run([str(primary_home / "bin/psql"),
                     "-h", "localhost", "-p", str(primary_port),
                     "-U", "postgres", "-d", "postgres",
                     "-tAc", "SELECT CASE WHEN pg_is_in_recovery() THEN 'REPLICA' ELSE 'PRIMARY' END;"],
                    env=env, capture_output=True)
        log.info(f"Primary status: {result.stdout.strip()}")

        result = run([str(replica_home / "bin/psql"),
                     "-h", "localhost", "-p", str(replica_port),
                     "-U", "postgres", "-d", "postgres",
                     "-tAc", "SELECT CASE WHEN pg_is_in_recovery() THEN 'REPLICA' ELSE 'PRIMARY' END;"],
                    env=env, capture_output=True)
        log.info(f"Replica status: {result.stdout.strip()}")
    except Exception as e:
        log.warning(f"⚠️  Could not verify replication status: {e}")

# -----------------------------
# Build logic
# -----------------------------
def build_instance(pg_home: Path,
                   branch: Optional[str],
                   tag: Optional[str],
                   commit: Optional[str],
                   name: str,
                   port: int,
                   skip_build: bool = False,
                   force_worktree: bool = False):

    worktrees_dir = prefix / "worktrees"
    worktrees_dir.mkdir(parents=True, exist_ok=True)
    worktree_name_final = f"{args.worktree_name}_{name}" if args.worktree_name else f"src_{name}"
    worktree_dir = worktrees_dir / worktree_name_final

    # Setup worktree if needed
    if not worktree_dir.exists() or (not skip_build and force_worktree) or args.force_worktree:
        source_path = setup_worktree(source_dir, worktree_dir, branch, tag, args.commit, args.repo_url)
    else:
        source_path = worktree_dir
        log.info(f"⏭️  Using existing worktree at {source_path}")

    # If worktree-only, stop here
    if args.worktree_only:
        log.info(f"✅ Worktree created at {source_path}")
        return

    # Apply patches
    if args.patch and not skip_build:
        for patch in sorted(glob.glob(args.patch)):
            log.info(f"📄 Applying patch {patch}")
            run(["git", "am", patch], cwd=source_path)

    # Build
    if not skip_build:
        build_dir = source_path / "build"
        if build_dir.exists():
            shutil.rmtree(build_dir)
        cmd = ["meson", "setup", "build", f"--prefix={pg_home}"]
        if args.meson_flags:
            cmd.extend(shlex.split(args.meson_flags))
        run(cmd, cwd=source_path, capture_output=args.capture_output)
        run(["ninja"], cwd=build_dir, capture_output=args.capture_output)
        run(["ninja", "install"], cwd=build_dir, capture_output=args.capture_output)

    env = os.environ.copy()
    env["PATH"] = f"{pg_home}/bin:" + env.get("PATH", "")

    # PGDATA & activation script - use worktree_name for unique data directory
    if args.worktree_name:
        pgdata_name = f"{args.worktree_name}_{name}"
    else:
        pgdata_name = name

    pgdata_dir = prefix / "pgdata" / pgdata_name
    script_file = prefix / f"activate_{name}.sh"
    pg_bsd_indent_path = source_path / "src/tools/pg_bsd_indent"
    activate_script(pg_home, pgdata_dir, port, script_file, pg_bsd_indent_path, worktree_name=args.worktree_name)

    # Stop & clean PGDATA
    stop_postgres(pg_home, pgdata_dir, port)
    if pgdata_dir.exists():
        shutil.rmtree(pgdata_dir)
    pgdata_dir.mkdir(parents=True, exist_ok=True)

    # Init & start
    init_db(pg_home, pgdata_dir, port, env)
    start_db(pg_home, pgdata_dir, env)

# -----------------------------
# Update source repository
# -----------------------------
def update_source(prefix: Path):
    source_dir = prefix / "source"

    if not source_dir.exists():
        log.info("📂 No source directory found.")
        return

    if not (source_dir / ".git").exists():
        log.info("❌ Source directory is not a git repository.")
        return

    log.info("🔄 Updating source repository...")

    try:
        # Fetch from all remotes
        run(["git", "fetch", "--all"], cwd=source_dir)

        # Prune stale remote branches
        run(["git", "remote", "prune", "origin"], cwd=source_dir, check=False)
        run(["git", "remote", "prune", "upstream"], cwd=source_dir, check=False)

        log.info("✅ Source repository updated.")
    except Exception as e:
        log.info(f"❌ Failed to update source: {e}")

# -----------------------------
# Clean worktrees
# -----------------------------
def clean_worktrees(prefix: Path):
    worktrees_dir = prefix / "worktrees"
    source_dir = prefix / "source"

    if not worktrees_dir.exists():
        log.info("📂 No worktrees directory found.")
        return

    worktrees = [w for w in worktrees_dir.iterdir() if w.is_dir()]

    if not worktrees:
        log.info("📂 No worktrees to clean.")
        return

    log.info(f"🧹 Cleaning {len(worktrees)} worktree(s)...")

    # Remove worktrees from git
    if source_dir.exists():
        for worktree in worktrees:
            log.info(f"  Removing {worktree.name}")
            try:
                run(["git", "worktree", "remove", "--force", str(worktree)],
                    cwd=source_dir, check=False)
            except Exception as e:
                log.info(f"    Warning: {e}")

        # Prune worktree references
        try:
            run(["git", "worktree", "prune"], cwd=source_dir, check=False)
        except Exception:
            pass

    # Remove worktrees directory
    if worktrees_dir.exists():
        shutil.rmtree(worktrees_dir, ignore_errors=True)

    log.info("✅ Worktrees cleaned.")

# -----------------------------
# List worktrees
# -----------------------------
def list_worktrees(prefix: Path):
    worktrees_dir = prefix / "worktrees"
    pgdata_dir = prefix / "pgdata"
    pghome_dirs = list(prefix.glob("pghome_*"))

    if not worktrees_dir.exists() or not any(worktrees_dir.iterdir()):
        log.info("📂 No worktrees found.")
        return

    log.info("📂 Existing worktrees:\n")

    for worktree in sorted(worktrees_dir.iterdir()):
        if not worktree.is_dir():
            continue

        name = worktree.name
        instance_name = name.replace("src_", "")

        # Check if corresponding pghome exists
        pghome = prefix / f"pghome_{instance_name}"
        pghome_exists = pghome.exists()

        # Check if pgdata exists
        pgdata = pgdata_dir / instance_name
        pgdata_exists = pgdata.exists()

        # Get git branch info
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=worktree,
                capture_output=True,
                text=True,
                check=False
            )
            branch = result.stdout.strip() or "detached HEAD"
        except Exception:
            branch = "unknown"

        # Get last commit
        try:
            result = subprocess.run(
                ["git", "log", "-1", "--oneline"],
                cwd=worktree,
                capture_output=True,
                text=True,
                check=False
            )
            commit = result.stdout.strip()
        except Exception:
            commit = "unknown"

        log.info(f"  {name}")
        log.info(f"    Path: {worktree}")
        log.info(f"    Branch: {branch}")
        log.info(f"    Commit: {commit}")
        log.info(f"    Built: {'✓' if pghome_exists else '✗'}")
        log.info(f"    DB initialized: {'✓' if pgdata_exists else '✗'}")
        log.info("")

# -----------------------------
# Main
# -----------------------------
def main():
    parser = argparse.ArgumentParser(description="Build and manage PostgreSQL development instances")
    parser.add_argument("--prefix", type=Path, default=Path.home() / "pgdev/installations",
                        help="Root directory for build artifacts, data, and scripts (default: ~/pgdev/installations)")
    parser.add_argument("--repo-url", type=str, default="https://github.com/postgres/postgres.git",
                        help="Git repository URL to clone from")
    parser.add_argument("--branch", type=str,
                        help="Branch to check out (mutually exclusive with --tag and --commit)")
    parser.add_argument("--tag", type=str,
                        help="Tag to check out (mutually exclusive with --branch and --commit)")
    parser.add_argument("--commit", type=str,
                        help="Commit hash to check out (mutually exclusive with --branch and --tag)")
    parser.add_argument("--patch", type=str,
                        help="Glob pattern of .patch files to apply via git am")
    parser.add_argument("--meson-flags", type=str,
                        help="Extra flags passed to meson setup")
    parser.add_argument("--build-system", choices=["meson", "make"], default="meson",
                        help="Build system to use (default: meson)")
    parser.add_argument("--worktree-name", type=str,
                        help="Optional prefix for naming worktree directories")
    parser.add_argument("--create-fdw", action="store_true",
                        help="Also build and start an FDW instance (port + 10)")
    parser.add_argument("--create-replica", action="store_true",
                        help="Also build and start a replica instance (port + 20)")
    parser.add_argument("--skip-build", action="store_true",
                        help="Skip the build step (re-init DB only)")
    parser.add_argument("--worktree-only", action="store_true",
                        help="Only create worktree, skip build and DB initialization")
    parser.add_argument("--force-worktree", action="store_true",
                        help="Force recreation of worktree even if it exists")
    parser.add_argument("--capture-output", action="store_true",
                        help="Suppress stdout/stderr from build commands")
    parser.add_argument("--port", type=int, default=5432,
                        help="Port for the primary instance (default: 5432)")
    parser.add_argument("-l", "--list-worktrees", action="store_true",
                        help="List existing worktrees and exit")
    parser.add_argument("--clean-worktrees", action="store_true",
                        help="Delete all worktrees and exit")
    parser.add_argument("--update-source", action="store_true",
                        help="Fetch latest changes from all remotes in source directory and exit")
    parser.add_argument("--recreate-activate-script", action="store_true",
                        help="Only recreate the activation script (cannot be used with other options)")

    global args
    args = parser.parse_args()

    global prefix
    global source_dir

    # Handle list-worktrees flag (must be used alone)
    if args.list_worktrees:
        if (args.create_fdw or args.create_replica or args.skip_build or
            args.force_worktree or args.patch or args.recreate_activate_script or
            args.branch or args.tag or args.clean_worktrees or args.update_source):
            parser.error("-l/--list-worktrees cannot be used with other options")

        prefix = args.prefix.expanduser().resolve()
        list_worktrees(prefix)
        return

    # Handle clean-worktrees flag (must be used alone)
    if args.clean_worktrees:
        if (args.create_fdw or args.create_replica or args.skip_build or
            args.force_worktree or args.patch or args.recreate_activate_script or
            args.branch or args.tag or args.list_worktrees or args.update_source):
            parser.error("--clean-worktrees cannot be used with other options")

        prefix = args.prefix.expanduser().resolve()
        clean_worktrees(prefix)
        return

    # Handle update-source flag (must be used alone)
    if args.update_source:
        if (args.create_fdw or args.create_replica or args.skip_build or
            args.force_worktree or args.patch or args.recreate_activate_script or
            args.branch or args.tag or args.list_worktrees or args.clean_worktrees):
            parser.error("--update-source cannot be used with other options")

        prefix = args.prefix.expanduser().resolve()
        update_source(prefix)
        return

    # Check for mutually exclusive option
    if args.recreate_activate_script:
        if (args.create_fdw or args.create_replica or args.skip_build or
            args.force_worktree or args.patch):
            parser.error("--recreate-activate-script cannot be used with other build options")

        # Recreate activation script only
        prefix = args.prefix.expanduser().resolve()

        if args.worktree_name:
            pg_home = prefix / "pghome" / f"{args.worktree_name}_primary"
            worktree_dir = prefix / "worktrees" / f"{args.worktree_name}_primary"
            pgdata_dir = prefix / "pgdata" / f"{args.worktree_name}_primary"
        else:
            pg_home = prefix / "pghome" / "primary"
            worktree_dir = prefix / "worktrees" / "src_primary"
            pgdata_dir = prefix / "pgdata" / "primary"
        script_file = prefix / f"activate_primary.sh"
        pg_bsd_indent_path = worktree_dir / "src/tools/pg_bsd_indent"

        activate_script(pg_home, pgdata_dir, args.port, script_file, pg_bsd_indent_path,
                        worktree_name=args.worktree_name)
        log.info("✅ Activation script recreated successfully.")
        return

    prefix = args.prefix.expanduser().resolve()
    prefix.mkdir(parents=True, exist_ok=True)

    source_dir = prefix / "source"

    # Validate mutually exclusive options
    ref_count = sum([bool(args.branch), bool(args.tag), bool(args.commit)])
    if ref_count == 0:
        parser.error("One of --branch, --tag, or --commit is required")
    if ref_count > 1:
        parser.error("--branch, --tag, and --commit are mutually exclusive")

    # Primary - use worktree_name if provided
    if args.worktree_name:
        pg_home_primary = prefix / "pghome" / f"{args.worktree_name}_primary"
    else:
        pg_home_primary = prefix / "pghome" / "primary"
    build_instance(pg_home_primary, args.branch, args.tag, args.commit, "primary", args.port, skip_build=args.skip_build)

    # FDW
    if args.create_fdw:
        pg_home_fdw = prefix / "pghome" / "fdw"
        build_instance(pg_home_fdw, args.branch, args.tag, args.commit, "fdw", args.port + 10, skip_build=args.skip_build, force_worktree=True)

    # Replica
    if args.create_replica:
        pg_home_replica = prefix / "pghome" / "replica"
        build_instance(pg_home_replica, args.branch, args.tag, args.commit, "replica", args.port + 20, skip_build=args.skip_build, force_worktree=True)

        # Setup replication between primary and replica
        pgdata_primary = prefix / "pgdata" / "primary"
        pgdata_replica = prefix / "pgdata" / "replica"
        setup_replication(pg_home_primary, pgdata_primary, args.port,
                         pg_home_replica, pgdata_replica, args.port + 20)

    log.info("✅ Build/init/start completed successfully.")

if __name__ == "__main__":
    main()
