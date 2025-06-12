#!/usr/bin/env python3
"""
Author: Sami Imseih
Purpose: Automate building PostgreSQL from source (tar.gz or latest GitHub),
         apply patches, build with meson/ninja, and set up primary, FDW, and replica clusters.
         All resources are stored under a common --prefix directory.
"""

import os
import sys
import shutil
import subprocess
import tarfile
import argparse
import logging
import platform
import tempfile
import glob
from pathlib import Path
from typing import Optional, Union, List

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger()


def run(command: Union[str, List[str]], **kwargs) -> subprocess.CompletedProcess:
    log.info(f"🔀 Running: {' '.join(command) if isinstance(command, list) else command}")

    capture_output = kwargs.get("capture_output", False)

    if capture_output:
        stdout = subprocess.PIPE
        stderr = subprocess.PIPE
    else:
        stdout = subprocess.DEVNULL
        stderr = subprocess.DEVNULL

    result = subprocess.run(
        command,
        shell=kwargs.get("shell", False),
        check=kwargs.get("check", True),
        env=kwargs.get("env"),
        stdout=stdout,
        stderr=stderr,
        cwd=str(kwargs.get("cwd")) if kwargs.get("cwd") else None,
        text=True,
    )

    if capture_output:
        if result.stdout:
            log.info(result.stdout.strip())
        if result.stderr:
            log.error(result.stderr.strip())

    return result


def stop_cluster(pgdata: Path, pg_home: Path, env: dict) -> None:
    if pgdata.exists():
        log.info(f"🛑 Stopping PostgreSQL cluster at {pgdata} if running...")
        try:
            path = shutil.which(f"{pg_home}/bin/pg_ctl")
            if path is not None:
                run([f"{pg_home}/bin/pg_ctl", "-D", str(pgdata), "stop", "-m", "fast"], env=env)
        except subprocess.CalledProcessError:
            log.warning(f"⚠️ Could not stop cluster at {pgdata} or it was not running.")


def delete_files_in_folder(folder_path: Path) -> None:
    log.info(f"🗑️ Recreating folder: {folder_path}")
    if folder_path.exists():
        shutil.rmtree(folder_path)
    folder_path.mkdir(parents=True, exist_ok=True)


def activate_script(pg_home: Path, pgdata: Path, port: int, script_name: Path, pg_bsd_indent_path: Path) -> None:
    # Compose the lines to write and set
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
        "#Build/Test helper functions",
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
        "    meson test -v -C . --suite \"$1\"",
        "}",
    ]

    # Write to the activation script file
    script_name.write_text("\n".join(exports) + "\n")
    log.info(f"✅ Wrote activation script: {script_name}")

    # Set environment variables in the current Python process
    os.environ["PGHOME"] = str(pg_home)
    # Prepend pg_home/bin to PATH
    os.environ["PATH"] = f"{pg_home}/bin:{pg_bsd_indent_path}:" + os.environ.get("PATH", "")
    os.environ["LD_LIBRARY_PATH"] = f"{pg_home}/lib"
    os.environ["PGDATA"] = str(pgdata)
    os.environ["PGUSER"] = "postgres"
    os.environ["PGDATABASE"] = "postgres"
    os.environ["PGPORT"] = str(port)

def find_pg_bsd_indent(build_root: Path) -> Path:
    """
    Recursively locate the pg_bsd_indent binary starting from the build root.
    Returns the parent directory containing the binary.
    """
    for path in build_root.rglob("pg_bsd_indent"):
        if path.is_file() and os.access(path, os.X_OK):
            return path.parent  # Return the directory, not the full path
    raise FileNotFoundError(f"pg_bsd_indent not found under {build_root}")

def extract_postgres(tarball: Path, target: Path) -> Path:
    log.info(f"📦 Extracting PostgreSQL tarball {tarball} to {target}")
    with tarfile.open(tarball) as tar:
        tar.extractall(path=target)
    dirs = [d for d in target.iterdir() if d.is_dir()]
    if not dirs:
        log.error("❌ Extraction failed, no source directory found.")
        sys.exit(1)
    return dirs[0]


def git_checkout_and_pull(source_dir: Path, branch: Optional[str], tag: Optional[str]) -> None:
    if branch:
        run(["git", "checkout", branch], cwd=source_dir)
    elif tag:
        run(["git", "checkout", f"tags/{tag}"], cwd=source_dir)
    run(["git", "pull"], cwd=source_dir)


def build_postgres(source_dir: Path, install_dir: Path, patch: Optional[str], meson_args: Optional[List[str]], capture_output: bool) -> None:
    if patch:
        patch_files = sorted(Path(p) for p in glob.glob(patch))
        if not patch_files:
            log.error(f"❌ No patch files matched: {patch}")
            sys.exit(1)
        for patch_file in patch_files:
            log.info(f"📄 Applying patch: {patch_file}")
            run(["git", "am", str(patch_file)], cwd=source_dir, capture_output=capture_output)

    meson_args_combined = [
        f"--prefix={install_dir}"
    ]

    meson_args_combined.extend(meson_args)

    run(["meson", "setup", "build"] + meson_args_combined, cwd=source_dir, capture_output=capture_output)
    build_dir = source_dir / "build"
    run(["ninja"], cwd=build_dir, capture_output=capture_output)
    run(["ninja", "install"], cwd=build_dir, capture_output=capture_output)


def append_postgresql_conf_parameter(pgdata: Path, parameter: str, value: str) -> None:
    conf_path = pgdata / "postgresql.conf"
    lines = conf_path.read_text().splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith(parameter):
            lines[i] = f"{parameter} = {value}"
            found = True
            break
    if not found:
        lines.append(f"{parameter} = {value}")
    conf_path.write_text("\n".join(lines) + "\n")


def init_db(pgdata: Path, pg_home: Path, port: int, env: dict) -> None:
    run([f"{pg_home}/bin/initdb", "-D", str(pgdata), "-U", "postgres"], env=env)
    append_postgresql_conf_parameter(pgdata, "logging_collector", "'on'")
    append_postgresql_conf_parameter(pgdata, "port", str(port))


def start_db(pgdata: Path, pg_home: Path, env: dict) -> None:
    run([f"{pg_home}/bin/pg_ctl", "-D", str(pgdata), "-l", str(pgdata / "logfile"), "start"], env=env)


def setup_fdw(pg_home: Path, port: int, env: dict, pgdata_fdw: Path, script_path: Path, prefix: Path) -> None:
    pg_bsd_indent_path = find_pg_bsd_indent(prefix / "source" / "src_fdw")
    init_db(pgdata_fdw, pg_home, port, env)
    activate_script(pg_home, pgdata_fdw, port, script_path, pg_bsd_indent_path)
    start_db(pgdata_fdw, pg_home, env)


def setup_replica(pg_home: Path, pgdata_primary: Path, pgdata_replica: Path, replica_port: int, primary_port: int, env: dict, script_path: Path, prefix: Path) -> None:
    pg_bsd_indent_path = find_pg_bsd_indent(prefix / "source" / "src_replica")
    delete_files_in_folder(pgdata_replica)
    run([
        f"{pg_home}/bin/pg_basebackup", "-D", str(pgdata_replica), "-R", "-P", "-X", "stream",
        "-cfast", "-U", "postgres", "-h", "localhost", "-p", str(primary_port)
    ], env=env)
    # Fix directory permissions after base backup
    pgdata_replica.chmod(0o700)
    activate_script(pg_home, pgdata_replica, replica_port, script_path, pg_bsd_indent_path)
    append_postgresql_conf_parameter(pgdata_replica, "port", str(replica_port))
    start_db(pgdata_replica, pg_home, env)


def download_and_tar_postgres(tarball_path: Path):
    log.info("⬇️ Cloning latest PostgreSQL...")
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir) / "postgres"
        run(["git", "clone", "https://github.com/postgres/postgres.git", str(repo_path)])
        with tarfile.open(tarball_path, "w:gz") as tar:
            tar.add(repo_path, arcname="postgres")
    log.info(f"🎁 Tarball written to {tarball_path}")


def main():
    # Determine default prefix based on platform
    system_name = platform.system().lower()
    if system_name == "darwin":
        default_prefix = Path.home() / "Documents" / "pgdev" / "installations"
    elif system_name.startswith("linux"):
        default_prefix = Path.home() / "pgdev" / "installations"
    else:
        log.error("❌ Unsupported OS. This script supports only macOS and Linux.")
        sys.exit(1)

    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", type=Path, default=default_prefix, help="Top-level directory for everything.")
    parser.add_argument("--source", type=Path, default=Path("postgres.tar.gz"), help=".tar.gz PostgreSQL source file")
    parser.add_argument("--patch", type=str, help="Glob pattern for patch files (e.g., 'patches/*.patch')")
    parser.add_argument("--meson-flags", type=str, help='--meson-flags="-Ddocs=enabled"')
    parser.add_argument("--branch", type=str)
    parser.add_argument("--tag", type=str)
    # Multi-ref support arguments
    parser.add_argument("--primary-branch", type=str)
    parser.add_argument("--primary-tag", type=str)
    parser.add_argument("--fdw-branch", type=str)
    parser.add_argument("--fdw-tag", type=str)
    parser.add_argument("--replica-branch", type=str)
    parser.add_argument("--replica-tag", type=str)

    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--create-fdw", action="store_true")
    parser.add_argument("--create-replica", action="store_true")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--capture-output", action="store_true")
    parser.add_argument("--update-tarball", type=Path, help="Download and tar latest PostgreSQL source to specified path")

    args = parser.parse_args()

    # --update-tarball mode
    if args.update_tarball:
        if len(sys.argv) > 3:
            log.error("❌ --update-tarball cannot be used with other options")
            sys.exit(1)
        download_and_tar_postgres(args.update_tarball)
        sys.exit(0)

    if args.tag and args.branch:
        log.error("❌ Cannot specify both --tag and --branch.")
        sys.exit(1)

    prefix = args.prefix.resolve()
    # Changed: separate pghome dirs per instance
    pg_home_primary = prefix / "pghome_primary"
    pg_home_fdw = prefix / "pghome_fdw"
    pg_home_replica = prefix / "pghome_replica"

    source_dir = prefix / "source"
    data_dir = prefix / "pgdata"
    act_primary = prefix / "activate_primary.sh"
    act_fdw = prefix / "activate_fdw.sh"
    act_replica = prefix / "activate_replica.sh"

    pgdata_primary = data_dir / "primary"
    pgdata_fdw = data_dir / "fdw"
    pgdata_replica = data_dir / "replica"

    def build_instance(pg_home, tag, branch, name):
        if not args.source.exists():
            log.error("❌ Source tarball not found.")
            sys.exit(1)
        tmp_src = source_dir / f"src_{name}"
        delete_files_in_folder(tmp_src)
        extracted = extract_postgres(args.source, tmp_src)
        git_checkout_and_pull(extracted, branch, tag)
        build_postgres(extracted, pg_home, args.patch, args.meson_flags.split() if args.meson_flags else None, args.capture_output)

    if not args.skip_build:
        delete_files_in_folder(prefix)
        build_instance(pg_home_primary, args.primary_tag or args.tag, args.primary_branch or args.branch, "primary")
        if args.create_fdw:
            build_instance(pg_home_fdw, args.fdw_tag or args.tag, args.fdw_branch or args.branch, "fdw")
        if args.create_replica:
            build_instance(pg_home_replica, args.replica_tag or args.tag, args.replica_branch or args.branch, "replica")

    if not pg_home_primary.exists():
        log.error(f"❌ Primary installation not found at {pg_home_primary}")
        sys.exit(1)

    def build_env(pg_home):
        e = os.environ.copy()
        e["PATH"] = f"{pg_home}/bin:" + e.get("PATH", "")
        e["LD_LIBRARY_PATH"] = f"{pg_home}/lib:" + e.get("LD_LIBRARY_PATH", "")
        return e

    env_primary = build_env(pg_home_primary)
    env_fdw = build_env(pg_home_fdw)
    env_replica = build_env(pg_home_replica)

    if args.skip_build:
        for d, home, env in [
            (pgdata_primary, pg_home_primary, env_primary),
            (pgdata_fdw, pg_home_fdw, env_fdw),
            (pgdata_replica, pg_home_replica, env_replica),
        ]:
            stop_cluster(d, home, env)
            delete_files_in_folder(d)

    init_db(pgdata_primary, pg_home_primary, args.port, env_primary)
    pg_bsd_indent_path = find_pg_bsd_indent(prefix / "source" / "src_primary")
    activate_script(pg_home_primary, pgdata_primary, args.port, act_primary, pg_bsd_indent_path)
    start_db(pgdata_primary, pg_home_primary, env_primary)

    if args.create_fdw:
        setup_fdw(pg_home_fdw, args.port + 10, env_fdw, pgdata_fdw, act_fdw, prefix)

    if args.create_replica:
        setup_replica(pg_home_replica, pgdata_primary, pgdata_replica, args.port + 20, args.port, env_replica, act_replica, prefix)


if __name__ == "__main__":
    main()
