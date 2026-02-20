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
        log.info(f"🔀 {shlex.join(command)}")
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

    try:
        subprocess.run(f"fuser -k {port}/tcp", shell=True, check=False)
    except Exception:
        pass

# -----------------------------
# Worktree setup
# -----------------------------
def setup_worktree(repo_root: Path,
                   worktree_dir: Path,
                   branch: Optional[str],
                   tag: Optional[str],
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

    checkout_ref = branch or tag
    if not checkout_ref:
        log.error("❌ Must supply branch or tag.")
        sys.exit(1)

    # Ensure repo is ready
    run(["git", "status"], cwd=repo_root)
    run(["git", "fetch", "--all"], cwd=repo_root)
    run(["git", "worktree", "prune"], cwd=repo_root)

    # Remove existing worktree if present
    if worktree_dir.exists():
        run(["git", "worktree", "remove", str(worktree_dir)], cwd=repo_root, check=False)
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

    if checkout_ref in branches_in_use:
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
# Build logic
# -----------------------------
def build_instance(pg_home: Path,
                   branch: Optional[str],
                   tag: Optional[str],
                   name: str,
                   port: int,
                   skip_build: bool = False):

    worktrees_dir = prefix / "worktrees"
    worktrees_dir.mkdir(parents=True, exist_ok=True)
    worktree_name_final = f"{args.worktree_name}_{name}" if args.worktree_name else f"src_{name}"
    worktree_dir = worktrees_dir / worktree_name_final

    source_path = setup_worktree(source_dir, worktree_dir, branch, tag, args.repo_url)

    # Apply patches
    if args.patch and not skip_build:
        for patch in sorted(glob.glob(args.patch)):
            log.info(f"📄 Applying patch {patch}")
            run(["git", "am", patch], cwd=source_path)

    # Build
    if not skip_build:
        if args.build_system == "meson":
            build_dir = source_path / "build"
            if build_dir.exists():
                shutil.rmtree(build_dir)
            cmd = ["meson", "setup", "build", f"--prefix={pg_home}"]
            if args.meson_flags:
                cmd.extend(shlex.split(args.meson_flags))
            run(cmd, cwd=source_path, capture_output=args.capture_output)
            run(["ninja"], cwd=build_dir, capture_output=args.capture_output)
            run(["ninja", "install"], cwd=build_dir, capture_output=args.capture_output)
        else:
            env = os.environ.copy()
            env["PREFIX"] = str(pg_home)
            run(["./configure", f"--prefix={pg_home}"], cwd=source_path, env=env)
            run(["make", "-j", str(os.cpu_count())], cwd=source_path, env=env)
            run(["make", "install"], cwd=source_path, env=env)

    env = os.environ.copy()
    env["PATH"] = f"{pg_home}/bin:" + env.get("PATH", "")

    # PGDATA & activation script
    pgdata_dir = prefix / "pgdata" / name
    script_file = prefix / f"activate_{name}.sh"
    activate_script(pg_home, pgdata_dir, port, script_file, source_path, worktree_name=args.worktree_name)

    # Stop & clean PGDATA
    stop_postgres(pg_home, pgdata_dir, port)
    if pgdata_dir.exists():
        shutil.rmtree(pgdata_dir)
    pgdata_dir.mkdir(parents=True, exist_ok=True)

    # Init & start
    init_db(pg_home, pgdata_dir, port, env)
    start_db(pg_home, pgdata_dir, env)

# -----------------------------
# Main
# -----------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", type=Path, default=Path.home() / "pgdev/installations")
    parser.add_argument("--repo-url", type=str, default="https://github.com/postgres/postgres.git")
    parser.add_argument("--branch", type=str)
    parser.add_argument("--tag", type=str)
    parser.add_argument("--patch", type=str)
    parser.add_argument("--meson-flags", type=str)
    parser.add_argument("--build-system", choices=["meson", "make"], default="meson")
    parser.add_argument("--worktree-name", type=str)
    parser.add_argument("--create-fdw", action="store_true")
    parser.add_argument("--create-replica", action="store_true")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--capture-output", action="store_true")
    parser.add_argument("--port", type=int, default=5432)

    global args
    args = parser.parse_args()

    global prefix
    prefix = args.prefix.expanduser().resolve()
    prefix.mkdir(parents=True, exist_ok=True)

    global source_dir
    source_dir = prefix / "source"

    # Primary
    pg_home_primary = prefix / "pghome_primary"
    build_instance(pg_home_primary, args.branch, args.tag, "primary", args.port, skip_build=args.skip_build)

    # FDW
    if args.create_fdw:
        pg_home_fdw = prefix / "pghome_fdw"
        build_instance(pg_home_fdw, args.branch, args.tag, "fdw", args.port + 10, skip_build=args.skip_build)

    # Replica
    if args.create_replica:
        pg_home_replica = prefix / "pghome_replica"
        build_instance(pg_home_replica, args.branch, args.tag, "replica", args.port + 20, skip_build=args.skip_build)

    log.info("✅ Build/init/start completed successfully.")

if __name__ == "__main__":
    main()
