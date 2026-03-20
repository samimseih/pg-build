#!/usr/bin/env python3
"""Comprehensive tests for pg_build.py"""

import os
import sys
import shutil
import subprocess
import argparse
import tempfile
import textwrap
from pathlib import Path
from unittest import mock
from unittest.mock import patch, MagicMock, call, mock_open

import pytest

# Import the module under test
import pg_build


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def tmp_prefix(tmp_path):
    """Create a temporary prefix directory structure."""
    prefix = tmp_path / "pgdev"
    prefix.mkdir()
    return prefix


@pytest.fixture
def tmp_source(tmp_prefix):
    """Create a fake source directory with .git."""
    source = tmp_prefix / "source"
    source.mkdir()
    (source / ".git").mkdir()
    return source


@pytest.fixture
def tmp_worktrees(tmp_prefix):
    """Create a fake worktrees directory."""
    wt = tmp_prefix / "worktrees"
    wt.mkdir()
    return wt


@pytest.fixture
def fake_pg_home(tmp_prefix):
    """Create a fake pg_home with bin directory."""
    pg_home = tmp_prefix / "pghome" / "primary"
    pg_home.mkdir(parents=True)
    bin_dir = pg_home / "bin"
    bin_dir.mkdir()
    return pg_home


@pytest.fixture
def fake_pgdata(tmp_prefix):
    """Create a fake pgdata directory."""
    pgdata = tmp_prefix / "pgdata" / "primary"
    pgdata.mkdir(parents=True)
    return pgdata


@pytest.fixture
def saved_env():
    """Save and restore environment variables."""
    original = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(original)


# ============================================================
# Tests for run()
# ============================================================

class TestRun:
    """Tests for the run() utility function."""

    @patch("pg_build.subprocess.run")
    def test_run_string_command(self, mock_subproc):
        mock_subproc.return_value = subprocess.CompletedProcess(args="echo hello", returncode=0)
        result = pg_build.run("echo hello")
        mock_subproc.assert_called_once()
        call_kwargs = mock_subproc.call_args
        assert call_kwargs[0][0] == "echo hello"
        assert call_kwargs[1]["shell"] is True

    @patch("pg_build.subprocess.run")
    def test_run_list_command(self, mock_subproc):
        mock_subproc.return_value = subprocess.CompletedProcess(args=["echo", "hello"], returncode=0)
        result = pg_build.run(["echo", "hello"])
        call_kwargs = mock_subproc.call_args
        assert call_kwargs[0][0] == ["echo", "hello"]
        assert call_kwargs[1]["shell"] is False

    @patch("pg_build.subprocess.run")
    def test_run_check_true_by_default(self, mock_subproc):
        mock_subproc.return_value = subprocess.CompletedProcess(args="cmd", returncode=0)
        pg_build.run("cmd")
        assert mock_subproc.call_args[1]["check"] is True

    @patch("pg_build.subprocess.run")
    def test_run_check_false(self, mock_subproc):
        mock_subproc.return_value = subprocess.CompletedProcess(args="cmd", returncode=1)
        pg_build.run("cmd", check=False)
        assert mock_subproc.call_args[1]["check"] is False

    @patch("pg_build.subprocess.run")
    def test_run_with_cwd(self, mock_subproc):
        mock_subproc.return_value = subprocess.CompletedProcess(args="cmd", returncode=0)
        pg_build.run("cmd", cwd="/tmp")
        assert mock_subproc.call_args[1]["cwd"] == "/tmp"

    @patch("pg_build.subprocess.run")
    def test_run_with_env(self, mock_subproc):
        mock_subproc.return_value = subprocess.CompletedProcess(args="cmd", returncode=0)
        env = {"FOO": "bar"}
        pg_build.run("cmd", env=env)
        assert mock_subproc.call_args[1]["env"] == env

    @patch("pg_build.subprocess.run")
    def test_run_capture_output(self, mock_subproc):
        mock_subproc.return_value = subprocess.CompletedProcess(args="cmd", returncode=0)
        pg_build.run("cmd", capture_output=True)
        assert mock_subproc.call_args[1]["stdout"] == subprocess.PIPE
        assert mock_subproc.call_args[1]["stderr"] == subprocess.PIPE

    @patch("pg_build.subprocess.run")
    def test_run_no_capture_output(self, mock_subproc):
        mock_subproc.return_value = subprocess.CompletedProcess(args="cmd", returncode=0)
        pg_build.run("cmd")
        assert mock_subproc.call_args[1]["stdout"] is None
        assert mock_subproc.call_args[1]["stderr"] is None

    @patch("pg_build.subprocess.run")
    def test_run_text_always_true(self, mock_subproc):
        mock_subproc.return_value = subprocess.CompletedProcess(args="cmd", returncode=0)
        pg_build.run("cmd")
        assert mock_subproc.call_args[1]["text"] is True


# ============================================================
# Tests for stop_postgres()
# ============================================================

class TestStopPostgres:
    """Tests for stop_postgres()."""

    def test_stop_nonexistent_pgdata(self, tmp_path):
        """Should return immediately if pgdata doesn't exist."""
        pg_home = tmp_path / "pghome"
        pgdata = tmp_path / "nonexistent"
        # Should not raise
        pg_build.stop_postgres(pg_home, pgdata, 5432)

    @patch("pg_build.subprocess.run")
    @patch("pg_build.run")
    def test_stop_with_existing_pgdata_and_pg_ctl(self, mock_run, mock_subproc, fake_pg_home, fake_pgdata):
        """Should call pg_ctl stop when pg_ctl exists."""
        pg_ctl = fake_pg_home / "bin" / "pg_ctl"
        pg_ctl.touch()

        mock_subproc.return_value = subprocess.CompletedProcess(args="", returncode=0, stdout="", stderr="")

        pg_build.stop_postgres(fake_pg_home, fake_pgdata, 5432)

        # pg_ctl stop should have been called
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "stop" in call_args
        assert "-m" in call_args
        assert "fast" in call_args

    @patch("pg_build.subprocess.run")
    @patch("pg_build.run")
    def test_stop_without_pg_ctl(self, mock_run, mock_subproc, fake_pg_home, fake_pgdata):
        """Should not call pg_ctl if it doesn't exist."""
        mock_subproc.return_value = subprocess.CompletedProcess(args="", returncode=0, stdout="", stderr="")
        pg_build.stop_postgres(fake_pg_home, fake_pgdata, 5432)
        mock_run.assert_not_called()

    @patch("pg_build.subprocess.run")
    @patch("pg_build.run")
    def test_stop_removes_stale_pid_file(self, mock_run, mock_subproc, fake_pg_home, fake_pgdata):
        """Should remove stale PID file."""
        mock_subproc.return_value = subprocess.CompletedProcess(args="", returncode=0, stdout="", stderr="")
        pid_file = fake_pgdata / "postmaster.pid"
        pid_file.write_text("12345")

        pg_build.stop_postgres(fake_pg_home, fake_pgdata, 5432)

        assert not pid_file.exists()

    @patch("pg_build.subprocess.run")
    @patch("pg_build.run")
    def test_stop_kills_processes_on_port(self, mock_run, mock_subproc, fake_pg_home, fake_pgdata):
        """Should attempt to kill processes on the port."""
        mock_subproc.return_value = subprocess.CompletedProcess(args="", returncode=0, stdout="1234\n5678", stderr="")
        pg_build.stop_postgres(fake_pg_home, fake_pgdata, 5432)
        # subprocess.run should be called for lsof and kill commands
        assert mock_subproc.call_count >= 1

    @patch("pg_build.subprocess.run", side_effect=Exception("fail"))
    @patch("pg_build.run", side_effect=Exception("fail"))
    def test_stop_handles_exceptions_gracefully(self, mock_run, mock_subproc, fake_pg_home, fake_pgdata):
        """Should not raise even if everything fails."""
        pg_ctl = fake_pg_home / "bin" / "pg_ctl"
        pg_ctl.touch()
        # Should not raise
        pg_build.stop_postgres(fake_pg_home, fake_pgdata, 5432)


# ============================================================
# Tests for activate_script()
# ============================================================

class TestActivateScript:
    """Tests for activate_script()."""

    def test_creates_script_file(self, tmp_path, saved_env):
        pg_home = tmp_path / "pghome"
        pgdata = tmp_path / "pgdata"
        script = tmp_path / "activate.sh"
        indent_path = tmp_path / "indent"

        result = pg_build.activate_script(pg_home, pgdata, 5432, script, indent_path)

        assert result == script
        assert script.exists()

    def test_script_content(self, tmp_path, saved_env):
        pg_home = tmp_path / "pghome"
        pgdata = tmp_path / "pgdata"
        script = tmp_path / "activate.sh"
        indent_path = tmp_path / "indent"

        pg_build.activate_script(pg_home, pgdata, 5432, script, indent_path)

        content = script.read_text()
        assert f"export PGHOME={pg_home}" in content
        assert f"export PGDATA={pgdata}" in content
        assert "export PGPORT=5432" in content
        assert "export PGUSER=postgres" in content
        assert "export PGDATABASE=postgres" in content
        assert f"export LD_LIBRARY_PATH={pg_home}/lib" in content
        assert "PG_START" in content
        assert "PG_STOP" in content
        assert "pg_check_extension" in content
        assert "pg_check_world" in content
        assert "pg_build_docs" in content
        assert "pg_list_tests" in content
        assert "pg_run_suite" in content

    def test_script_with_worktree_name(self, tmp_path, saved_env):
        pg_home = tmp_path / "pghome"
        pgdata = tmp_path / "pgdata"
        script = tmp_path / "activate.sh"
        indent_path = tmp_path / "indent"

        result = pg_build.activate_script(pg_home, pgdata, 5432, script, indent_path, worktree_name="mytest")

        expected_name = tmp_path / "activate_mytest.sh"
        assert result == expected_name
        assert expected_name.exists()

    def test_sets_environment_variables(self, tmp_path, saved_env):
        pg_home = tmp_path / "pghome"
        pgdata = tmp_path / "pgdata"
        script = tmp_path / "activate.sh"
        indent_path = tmp_path / "indent"

        pg_build.activate_script(pg_home, pgdata, 5432, script, indent_path)

        assert os.environ["PGHOME"] == str(pg_home)
        assert os.environ["PGDATA"] == str(pgdata)
        assert os.environ["PGUSER"] == "postgres"
        assert os.environ["PGDATABASE"] == "postgres"
        assert os.environ["PGPORT"] == "5432"
        assert f"{pg_home}/lib" in os.environ["LD_LIBRARY_PATH"]

    def test_different_port(self, tmp_path, saved_env):
        pg_home = tmp_path / "pghome"
        pgdata = tmp_path / "pgdata"
        script = tmp_path / "activate.sh"
        indent_path = tmp_path / "indent"

        pg_build.activate_script(pg_home, pgdata, 9999, script, indent_path)

        content = script.read_text()
        assert "export PGPORT=9999" in content
        assert os.environ["PGPORT"] == "9999"


# ============================================================
# Tests for init_db()
# ============================================================

class TestInitDb:
    """Tests for init_db()."""

    @patch("pg_build.run")
    def test_init_db_creates_pgdata(self, mock_run, tmp_path):
        pg_home = tmp_path / "pghome"
        pg_home.mkdir()
        pgdata = tmp_path / "pgdata"
        env = {"PATH": "/usr/bin"}

        def fake_initdb(cmd, **kwargs):
            pgdata.mkdir(parents=True, exist_ok=True)
            (pgdata / "postgresql.conf").write_text("# default config\n")
            return subprocess.CompletedProcess(args=cmd, returncode=0)

        mock_run.side_effect = fake_initdb
        pg_build.init_db(pg_home, pgdata, 5432, env)

        assert pgdata.exists()

    @patch("pg_build.run")
    def test_init_db_removes_existing_pgdata(self, mock_run, tmp_path):
        pg_home = tmp_path / "pghome"
        pg_home.mkdir()
        pgdata = tmp_path / "pgdata"
        pgdata.mkdir()
        (pgdata / "old_file").touch()
        env = {"PATH": "/usr/bin"}

        def fake_initdb(cmd, **kwargs):
            pgdata.mkdir(parents=True, exist_ok=True)
            (pgdata / "postgresql.conf").write_text("# default config\n")
            return subprocess.CompletedProcess(args=cmd, returncode=0)

        mock_run.side_effect = fake_initdb
        pg_build.init_db(pg_home, pgdata, 5432, env)

        # old_file should be gone (pgdata was recreated)
        assert pgdata.exists()
        assert not (pgdata / "old_file").exists()

    @patch("pg_build.run")
    def test_init_db_calls_initdb(self, mock_run, tmp_path):
        pg_home = tmp_path / "pghome"
        pg_home.mkdir()
        pgdata = tmp_path / "pgdata"
        env = {"PATH": "/usr/bin"}

        def fake_initdb(cmd, **kwargs):
            pgdata.mkdir(parents=True, exist_ok=True)
            (pgdata / "postgresql.conf").write_text("# default config\n")
            return subprocess.CompletedProcess(args=cmd, returncode=0)

        mock_run.side_effect = fake_initdb
        pg_build.init_db(pg_home, pgdata, 5432, env)

        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert str(pg_home / "bin/initdb") in call_args[0]
        assert "-D" in call_args
        assert "-U" in call_args
        assert "postgres" in call_args

    @patch("pg_build.run")
    def test_init_db_writes_port_to_conf(self, mock_run, tmp_path):
        pg_home = tmp_path / "pghome"
        pg_home.mkdir()
        pgdata = tmp_path / "pgdata"
        env = {"PATH": "/usr/bin"}

        # init_db expects to read postgresql.conf after initdb creates it
        # We need to simulate initdb creating the file
        def fake_run(cmd, **kwargs):
            # Simulate initdb creating postgresql.conf
            pgdata.mkdir(parents=True, exist_ok=True)
            (pgdata / "postgresql.conf").write_text("# default config\n")
            return subprocess.CompletedProcess(args=cmd, returncode=0)

        mock_run.side_effect = fake_run

        pg_build.init_db(pg_home, pgdata, 5432, env)

        conf = (pgdata / "postgresql.conf").read_text()
        assert "port = 5432" in conf
        assert "logging_collector = 'on'" in conf


# ============================================================
# Tests for start_db()
# ============================================================

class TestStartDb:
    """Tests for start_db()."""

    @patch("pg_build.run")
    def test_start_db_calls_pg_ctl(self, mock_run, tmp_path):
        pg_home = tmp_path / "pghome"
        pgdata = tmp_path / "pgdata"
        pgdata.mkdir(parents=True)
        env = {"PATH": "/usr/bin"}

        pg_build.start_db(pg_home, pgdata, env)

        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert str(pg_home / "bin/pg_ctl") in call_args[0]
        assert "start" in call_args
        assert "-D" in call_args
        assert str(pgdata) in call_args


# ============================================================
# Tests for setup_worktree()
# ============================================================

class TestSetupWorktree:
    """Tests for setup_worktree()."""

    @patch("pg_build.subprocess.run")
    @patch("pg_build.run")
    def test_setup_worktree_requires_ref(self, mock_run, mock_subproc, tmp_path):
        """Should exit if no branch, tag, or commit is provided."""
        repo_root = tmp_path / "source"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()
        worktree_dir = tmp_path / "worktree"

        with pytest.raises(SystemExit):
            pg_build.setup_worktree(repo_root, worktree_dir, None, None, None, "https://example.com/repo.git")

    @patch("pg_build.subprocess.run")
    @patch("pg_build.run")
    def test_setup_worktree_clones_if_missing(self, mock_run, mock_subproc, tmp_path):
        """Should clone repo if repo_root doesn't exist."""
        repo_root = tmp_path / "source"
        worktree_dir = tmp_path / "worktree"
        repo_url = "https://example.com/repo.git"

        mock_subproc.return_value = subprocess.CompletedProcess(
            args="", returncode=0, stdout="origin\n", stderr=""
        )

        # Make setup_worktree think the repo exists after clone
        def side_effect(cmd, **kwargs):
            if cmd[0] == "git" and cmd[1] == "clone":
                repo_root.mkdir(parents=True, exist_ok=True)
                (repo_root / ".git").mkdir(exist_ok=True)
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        mock_run.side_effect = side_effect

        pg_build.setup_worktree(repo_root, worktree_dir, "main", None, None, repo_url)

        # Verify clone was called
        clone_calls = [c for c in mock_run.call_args_list if "clone" in str(c)]
        assert len(clone_calls) > 0

    @patch("pg_build.subprocess.run")
    @patch("pg_build.run")
    def test_setup_worktree_adds_upstream_remote(self, mock_run, mock_subproc, tmp_path):
        """Should add upstream remote if not present."""
        repo_root = tmp_path / "source"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()
        worktree_dir = tmp_path / "worktree"
        repo_url = "https://example.com/repo.git"

        # No upstream in remotes
        mock_subproc.return_value = subprocess.CompletedProcess(
            args="", returncode=0, stdout="origin\n", stderr=""
        )
        mock_run.return_value = subprocess.CompletedProcess(args="", returncode=0, stdout="", stderr="")

        pg_build.setup_worktree(repo_root, worktree_dir, "main", None, None, repo_url)

        # Check that "remote add upstream" was called
        remote_add_calls = [c for c in mock_run.call_args_list
                           if "remote" in str(c) and "add" in str(c) and "upstream" in str(c)]
        assert len(remote_add_calls) > 0

    @patch("pg_build.subprocess.run")
    @patch("pg_build.run")
    def test_setup_worktree_commit_creates_detached(self, mock_run, mock_subproc, tmp_path):
        """Should create detached HEAD worktree for commits."""
        repo_root = tmp_path / "source"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()
        worktree_dir = tmp_path / "worktree"

        mock_subproc.return_value = subprocess.CompletedProcess(
            args="", returncode=0, stdout="origin\nupstream\n", stderr=""
        )
        mock_run.return_value = subprocess.CompletedProcess(args="", returncode=0, stdout="", stderr="")

        pg_build.setup_worktree(repo_root, worktree_dir, None, None, "abc123", "https://example.com/repo.git")

        detach_calls = [c for c in mock_run.call_args_list if "--detach" in str(c)]
        assert len(detach_calls) > 0

    @patch("pg_build.subprocess.run")
    @patch("pg_build.run")
    def test_setup_worktree_returns_worktree_dir(self, mock_run, mock_subproc, tmp_path):
        """Should return the worktree directory path."""
        repo_root = tmp_path / "source"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()
        worktree_dir = tmp_path / "worktree"

        mock_subproc.return_value = subprocess.CompletedProcess(
            args="", returncode=0, stdout="origin\nupstream\n", stderr=""
        )
        mock_run.return_value = subprocess.CompletedProcess(args="", returncode=0, stdout="", stderr="")

        result = pg_build.setup_worktree(repo_root, worktree_dir, "main", None, None, "https://example.com/repo.git")
        assert result == worktree_dir.resolve()

    @patch("pg_build.subprocess.run")
    @patch("pg_build.run")
    def test_setup_worktree_creates_unique_branch_when_in_use(self, mock_run, mock_subproc, tmp_path):
        """Should create a unique branch named {branch}_{worktree_dir.name} when branch is already in use."""
        repo_root = tmp_path / "source"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()
        worktree_dir = tmp_path / "worktrees" / "fdw"

        def subproc_side_effect(cmd, **kwargs):
            if cmd == ["git", "remote"]:
                return subprocess.CompletedProcess(args="", returncode=0, stdout="origin\nupstream\n", stderr="")
            if cmd == ["git", "worktree", "list", "--porcelain"]:
                # master is already checked out in another worktree
                return subprocess.CompletedProcess(
                    args="", returncode=0,
                    stdout="worktree /some/path\nbranch refs/heads/master\n\n", stderr=""
                )
            if cmd == ["git", "branch", "--format", "%(refname:short)"]:
                return subprocess.CompletedProcess(args="", returncode=0, stdout="master\n", stderr="")
            return subprocess.CompletedProcess(args="", returncode=0, stdout="", stderr="")

        mock_subproc.side_effect = subproc_side_effect
        mock_run.return_value = subprocess.CompletedProcess(args="", returncode=0, stdout="", stderr="")

        pg_build.setup_worktree(repo_root, worktree_dir, "master", None, None, "https://example.com/repo.git")

        # Should have called worktree add with -b master_fdw
        add_calls = [c for c in mock_run.call_args_list
                     if "worktree" in str(c) and "add" in str(c) and "-b" in str(c)]
        assert len(add_calls) == 1
        call_args = add_calls[0][0][0]
        assert "master_fdw" in call_args

    @patch("pg_build.subprocess.run")
    @patch("pg_build.run")
    def test_setup_worktree_deletes_stale_unique_branch(self, mock_run, mock_subproc, tmp_path):
        """Should delete an existing local branch with the unique name before recreating it."""
        repo_root = tmp_path / "source"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()
        worktree_dir = tmp_path / "worktrees" / "fdw"

        def subproc_side_effect(cmd, **kwargs):
            if cmd == ["git", "remote"]:
                return subprocess.CompletedProcess(args="", returncode=0, stdout="origin\nupstream\n", stderr="")
            if cmd == ["git", "worktree", "list", "--porcelain"]:
                return subprocess.CompletedProcess(
                    args="", returncode=0,
                    stdout="worktree /some/path\nbranch refs/heads/master\n\n", stderr=""
                )
            if cmd == ["git", "branch", "--format", "%(refname:short)"]:
                # master_fdw already exists locally
                return subprocess.CompletedProcess(args="", returncode=0, stdout="master\nmaster_fdw\n", stderr="")
            return subprocess.CompletedProcess(args="", returncode=0, stdout="", stderr="")

        mock_subproc.side_effect = subproc_side_effect
        mock_run.return_value = subprocess.CompletedProcess(args="", returncode=0, stdout="", stderr="")

        pg_build.setup_worktree(repo_root, worktree_dir, "master", None, None, "https://example.com/repo.git")

        # Should have called git branch -D master_fdw
        delete_calls = [c for c in mock_run.call_args_list
                        if "branch" in str(c) and "-D" in str(c) and "master_fdw" in str(c)]
        assert len(delete_calls) == 1


# ============================================================
# Tests for update_source()
# ============================================================

class TestUpdateSource:
    """Tests for update_source()."""

    def test_update_source_no_source_dir(self, tmp_prefix):
        """Should handle missing source directory gracefully."""
        # Should not raise
        pg_build.update_source(tmp_prefix)

    def test_update_source_not_git_repo(self, tmp_prefix):
        """Should handle non-git source directory."""
        source = tmp_prefix / "source"
        source.mkdir()
        # No .git dir
        pg_build.update_source(tmp_prefix)

    @patch("pg_build.run")
    def test_update_source_fetches_all(self, mock_run, tmp_prefix, tmp_source):
        """Should fetch from all remotes."""
        mock_run.return_value = subprocess.CompletedProcess(args="", returncode=0)

        pg_build.update_source(tmp_prefix)

        fetch_calls = [c for c in mock_run.call_args_list if "fetch" in str(c) and "--all" in str(c)]
        assert len(fetch_calls) > 0

    @patch("pg_build.run")
    def test_update_source_prunes_remotes(self, mock_run, tmp_prefix, tmp_source):
        """Should prune stale remote branches."""
        mock_run.return_value = subprocess.CompletedProcess(args="", returncode=0)

        pg_build.update_source(tmp_prefix)

        prune_calls = [c for c in mock_run.call_args_list if "prune" in str(c)]
        assert len(prune_calls) >= 1

    @patch("pg_build.run", side_effect=Exception("network error"))
    def test_update_source_handles_failure(self, mock_run, tmp_prefix, tmp_source):
        """Should handle fetch failures gracefully."""
        # Should not raise
        pg_build.update_source(tmp_prefix)


# ============================================================
# Tests for clean_worktrees()
# ============================================================

class TestCleanWorktrees:
    """Tests for clean_worktrees()."""

    def test_clean_no_worktrees_dir(self, tmp_prefix):
        """Should handle missing worktrees directory."""
        pg_build.clean_worktrees(tmp_prefix)

    def test_clean_empty_worktrees_dir(self, tmp_prefix, tmp_worktrees):
        """Should handle empty worktrees directory."""
        pg_build.clean_worktrees(tmp_prefix)

    @patch("pg_build.run")
    def test_clean_removes_worktrees(self, mock_run, tmp_prefix, tmp_worktrees, tmp_source):
        """Should remove all worktrees."""
        mock_run.return_value = subprocess.CompletedProcess(args="", returncode=0)

        # Create fake worktrees
        (tmp_worktrees / "src_primary").mkdir()
        (tmp_worktrees / "src_fdw").mkdir()

        pg_build.clean_worktrees(tmp_prefix)

        # Worktrees directory should be removed
        assert not tmp_worktrees.exists()

    @patch("pg_build.run")
    def test_clean_stops_running_clusters(self, mock_run, tmp_prefix, tmp_worktrees, tmp_source):
        """Should stop running clusters before cleanup."""
        mock_run.return_value = subprocess.CompletedProcess(args="", returncode=0)

        wt = tmp_worktrees / "src_primary"
        wt.mkdir()

        # Create pghome and pgdata with postmaster.pid
        pghome = tmp_prefix / "pghome" / "primary"
        pghome.mkdir(parents=True)
        pg_ctl = pghome / "bin" / "pg_ctl"
        pg_ctl.parent.mkdir(parents=True, exist_ok=True)
        pg_ctl.touch()

        pgdata = tmp_prefix / "pgdata" / "primary"
        pgdata.mkdir(parents=True)
        (pgdata / "postmaster.pid").touch()

        pg_build.clean_worktrees(tmp_prefix)

        # Should have called pg_ctl stop
        stop_calls = [c for c in mock_run.call_args_list if "stop" in str(c)]
        assert len(stop_calls) > 0


# ============================================================
# Tests for resolve_worktree_dirs()
# ============================================================

class TestResolveWorktreeDirs:
    """Tests for resolve_worktree_dirs()."""

    def test_no_worktrees_dir(self, tmp_prefix):
        """Should return empty list if worktrees dir doesn't exist."""
        result = pg_build.resolve_worktree_dirs(tmp_prefix, "test")
        assert result == []

    def test_no_matching_worktrees(self, tmp_prefix, tmp_worktrees):
        """Should return empty list if no matches."""
        (tmp_worktrees / "src_primary").mkdir()
        result = pg_build.resolve_worktree_dirs(tmp_prefix, "nonexistent")
        assert result == []

    def test_matching_worktrees(self, tmp_prefix, tmp_worktrees):
        """Should return matching worktree directories using name_ prefix."""
        (tmp_worktrees / "test_primary").mkdir()
        (tmp_worktrees / "test_fdw").mkdir()
        (tmp_worktrees / "other_primary").mkdir()

        result = pg_build.resolve_worktree_dirs(tmp_prefix, "test")
        assert len(result) == 2
        names = [r.name for r in result]
        assert "test_primary" in names
        assert "test_fdw" in names

    def test_does_not_match_longer_prefix(self, tmp_prefix, tmp_worktrees):
        """Should not match worktrees that merely start with the name but have no underscore boundary."""
        (tmp_worktrees / "test_primary").mkdir()
        (tmp_worktrees / "testing_primary").mkdir()

        result = pg_build.resolve_worktree_dirs(tmp_prefix, "test")
        assert len(result) == 1
        assert result[0].name == "test_primary"

    def test_exact_name_match(self, tmp_prefix, tmp_worktrees):
        """Should match a worktree whose name equals the query exactly."""
        (tmp_worktrees / "test").mkdir()
        (tmp_worktrees / "test_primary").mkdir()

        result = pg_build.resolve_worktree_dirs(tmp_prefix, "test")
        assert len(result) == 2
        names = [r.name for r in result]
        assert "test" in names
        assert "test_primary" in names

    def test_returns_sorted(self, tmp_prefix, tmp_worktrees):
        """Should return sorted results."""
        (tmp_worktrees / "test_c").mkdir()
        (tmp_worktrees / "test_a").mkdir()
        (tmp_worktrees / "test_b").mkdir()

        result = pg_build.resolve_worktree_dirs(tmp_prefix, "test")
        names = [r.name for r in result]
        assert names == sorted(names)

    def test_ignores_files(self, tmp_prefix, tmp_worktrees):
        """Should only return directories, not files."""
        (tmp_worktrees / "test_primary").mkdir()
        (tmp_worktrees / "test_file.txt").touch()

        result = pg_build.resolve_worktree_dirs(tmp_prefix, "test")
        assert len(result) == 1
        assert result[0].name == "test_primary"


# ============================================================
# Tests for remove_worktree()
# ============================================================

class TestRemoveWorktree:
    """Tests for remove_worktree()."""

    def test_remove_nonexistent_worktree(self, tmp_prefix, tmp_worktrees):
        """Should exit if no matching worktrees found."""
        with pytest.raises(SystemExit):
            pg_build.remove_worktree(tmp_prefix, "nonexistent")

    @patch("pg_build.run")
    def test_remove_worktree_removes_dirs(self, mock_run, tmp_prefix, tmp_worktrees, tmp_source):
        """Should remove worktree, pghome, and pgdata directories."""
        mock_run.return_value = subprocess.CompletedProcess(args="", returncode=0)

        wt = tmp_worktrees / "src_primary"
        wt.mkdir()

        pghome = tmp_prefix / "pghome" / "primary"
        pghome.mkdir(parents=True)

        pgdata = tmp_prefix / "pgdata" / "primary"
        pgdata.mkdir(parents=True)

        pg_build.remove_worktree(tmp_prefix, "src_primary")

        assert not pghome.exists()
        assert not pgdata.exists()

    @patch("pg_build.run")
    def test_remove_worktree_removes_activate_scripts(self, mock_run, tmp_prefix, tmp_worktrees, tmp_source):
        """Should remove the activate script for the worktree."""
        mock_run.return_value = subprocess.CompletedProcess(args="", returncode=0)

        wt = tmp_worktrees / "fdw"
        wt.mkdir()

        # activate script is now simply activate_{name}.sh
        matching_script = tmp_prefix / "activate_fdw.sh"
        matching_script.write_text("#!/bin/bash\n")

        unrelated_script = tmp_prefix / "activate_primary.sh"
        unrelated_script.write_text("#!/bin/bash\n")

        pg_build.remove_worktree(tmp_prefix, "fdw")

        assert not matching_script.exists()
        assert unrelated_script.exists()

    @patch("pg_build.run")
    def test_remove_worktree_cleans_all_artifacts(self, mock_run, tmp_prefix, tmp_worktrees, tmp_source):
        """Should remove worktree dir, pghome, pgdata, and activate script."""
        mock_run.return_value = subprocess.CompletedProcess(args="", returncode=0)

        wt = tmp_worktrees / "myfeature"
        wt.mkdir()

        pghome = tmp_prefix / "pghome" / "myfeature"
        pghome.mkdir(parents=True)

        pgdata = tmp_prefix / "pgdata" / "myfeature"
        pgdata.mkdir(parents=True)

        script = tmp_prefix / "activate_myfeature.sh"
        script.write_text("#!/bin/bash\n")

        pg_build.remove_worktree(tmp_prefix, "myfeature")

        assert not wt.exists()
        assert not pghome.exists()
        assert not pgdata.exists()
        assert not script.exists()

    @patch("pg_build.run")
    def test_remove_worktree_stops_cluster(self, mock_run, tmp_prefix, tmp_worktrees, tmp_source):
        """Should stop running cluster before removal."""
        mock_run.return_value = subprocess.CompletedProcess(args="", returncode=0)

        wt = tmp_worktrees / "src_primary"
        wt.mkdir()

        pghome = tmp_prefix / "pghome" / "primary"
        pghome.mkdir(parents=True)
        pg_ctl = pghome / "bin" / "pg_ctl"
        pg_ctl.parent.mkdir(parents=True, exist_ok=True)
        pg_ctl.touch()

        pgdata = tmp_prefix / "pgdata" / "primary"
        pgdata.mkdir(parents=True)
        (pgdata / "postmaster.pid").touch()

        pg_build.remove_worktree(tmp_prefix, "src_primary")

        stop_calls = [c for c in mock_run.call_args_list if "stop" in str(c)]
        assert len(stop_calls) > 0


# ============================================================
# Tests for list_worktrees()
# ============================================================

class TestListWorktrees:
    """Tests for list_worktrees()."""

    def test_list_no_worktrees_dir(self, tmp_prefix):
        """Should handle missing worktrees directory."""
        pg_build.list_worktrees(tmp_prefix)

    def test_list_empty_worktrees(self, tmp_prefix, tmp_worktrees):
        """Should handle empty worktrees directory."""
        pg_build.list_worktrees(tmp_prefix)

    @patch("pg_build.subprocess.run")
    def test_list_shows_worktrees(self, mock_subproc, tmp_prefix, tmp_worktrees, capsys):
        """Should list existing worktrees with info."""
        mock_subproc.return_value = subprocess.CompletedProcess(
            args="", returncode=0, stdout="main\n", stderr=""
        )

        wt = tmp_worktrees / "src_primary"
        wt.mkdir()

        pg_build.list_worktrees(tmp_prefix)

        # The function logs output, check it was called
        assert mock_subproc.call_count >= 1


# ============================================================
# Tests for setup_replication()
# ============================================================

class TestSetupReplication:
    """Tests for setup_replication()."""

    @patch("pg_build.run")
    @patch("pg_build.stop_postgres")
    def test_setup_replication_configures_primary(self, mock_stop, mock_run, tmp_path):
        """Should configure primary for replication."""
        primary_home = tmp_path / "primary_home"
        primary_home.mkdir()
        (primary_home / "bin").mkdir()

        primary_data = tmp_path / "primary_data"
        primary_data.mkdir()
        (primary_data / "postgresql.conf").write_text("# config\n")
        (primary_data / "pg_hba.conf").write_text("# hba\n")

        replica_home = tmp_path / "replica_home"
        replica_home.mkdir()
        (replica_home / "bin").mkdir()

        replica_data = tmp_path / "replica_data"

        mock_run.return_value = subprocess.CompletedProcess(
            args="", returncode=0, stdout="PRIMARY\n", stderr=""
        )

        pg_build.setup_replication(
            primary_home, primary_data, 5432,
            replica_home, replica_data, 5452
        )

        # Check primary conf was updated
        conf = (primary_data / "postgresql.conf").read_text()
        assert "wal_level = replica" in conf
        assert "max_wal_senders = 3" in conf

    @patch("pg_build.run")
    @patch("pg_build.stop_postgres")
    def test_setup_replication_adds_hba_entry(self, mock_stop, mock_run, tmp_path):
        """Should add replication entry to pg_hba.conf."""
        primary_home = tmp_path / "primary_home"
        primary_home.mkdir()
        (primary_home / "bin").mkdir()

        primary_data = tmp_path / "primary_data"
        primary_data.mkdir()
        (primary_data / "postgresql.conf").write_text("# config\n")
        (primary_data / "pg_hba.conf").write_text("# hba\n")

        replica_home = tmp_path / "replica_home"
        replica_home.mkdir()
        (replica_home / "bin").mkdir()

        replica_data = tmp_path / "replica_data"

        mock_run.return_value = subprocess.CompletedProcess(
            args="", returncode=0, stdout="PRIMARY\n", stderr=""
        )

        pg_build.setup_replication(
            primary_home, primary_data, 5432,
            replica_home, replica_data, 5452
        )

        hba = (primary_data / "pg_hba.conf").read_text()
        assert "replication" in hba

    @patch("pg_build.run")
    @patch("pg_build.stop_postgres")
    def test_setup_replication_skips_duplicate_hba(self, mock_stop, mock_run, tmp_path):
        """Should not add duplicate replication entry."""
        primary_home = tmp_path / "primary_home"
        primary_home.mkdir()
        (primary_home / "bin").mkdir()

        primary_data = tmp_path / "primary_data"
        primary_data.mkdir()
        (primary_data / "postgresql.conf").write_text("# config\n")
        (primary_data / "pg_hba.conf").write_text("host replication all 127.0.0.1/32 trust\n")

        replica_home = tmp_path / "replica_home"
        replica_home.mkdir()
        (replica_home / "bin").mkdir()

        replica_data = tmp_path / "replica_data"

        mock_run.return_value = subprocess.CompletedProcess(
            args="", returncode=0, stdout="PRIMARY\n", stderr=""
        )

        pg_build.setup_replication(
            primary_home, primary_data, 5432,
            replica_home, replica_data, 5452
        )

        hba = (primary_data / "pg_hba.conf").read_text()
        # Should only have one replication line
        assert hba.count("replication") == 1


# ============================================================
# Tests for main() argument parsing
# ============================================================

class TestMainArgParsing:
    """Tests for main() argument parsing and dispatch."""

    @patch("pg_build.list_worktrees")
    def test_main_list_worktrees(self, mock_list, tmp_path):
        """Should call list_worktrees when -l flag is used."""
        with patch("sys.argv", ["pg_build.py", "--prefix", str(tmp_path), "-l"]):
            pg_build.main()
        mock_list.assert_called_once()

    @patch("pg_build.clean_worktrees")
    def test_main_clean_worktrees(self, mock_clean, tmp_path):
        """Should call clean_worktrees when --clean-worktrees flag is used."""
        with patch("sys.argv", ["pg_build.py", "--prefix", str(tmp_path), "--clean-worktrees"]):
            pg_build.main()
        mock_clean.assert_called_once()

    @patch("pg_build.remove_worktree")
    def test_main_remove_worktree(self, mock_remove, tmp_path):
        """Should call remove_worktree when --remove-worktree flag is used."""
        with patch("sys.argv", ["pg_build.py", "--prefix", str(tmp_path), "--remove-worktree", "test"]):
            pg_build.main()
        mock_remove.assert_called_once()

    @patch("pg_build.update_source")
    def test_main_update_source(self, mock_update, tmp_path):
        """Should call update_source when --update-source flag is used."""
        with patch("sys.argv", ["pg_build.py", "--prefix", str(tmp_path), "--update-source"]):
            pg_build.main()
        mock_update.assert_called_once()

    def test_main_requires_ref(self, tmp_path):
        """Should error if no branch/tag/commit provided for build."""
        with patch("sys.argv", ["pg_build.py", "--prefix", str(tmp_path)]):
            with pytest.raises(SystemExit):
                pg_build.main()

    def test_main_mutually_exclusive_refs(self, tmp_path):
        """Should error if multiple refs provided."""
        with patch("sys.argv", ["pg_build.py", "--prefix", str(tmp_path),
                                "--branch", "main", "--tag", "v16"]):
            with pytest.raises(SystemExit):
                pg_build.main()

    def test_main_list_with_other_options_errors(self, tmp_path):
        """Should error if -l is used with other options."""
        with patch("sys.argv", ["pg_build.py", "--prefix", str(tmp_path),
                                "-l", "--branch", "main"]):
            with pytest.raises(SystemExit):
                pg_build.main()

    def test_main_clean_with_other_options_errors(self, tmp_path):
        """Should error if --clean-worktrees is used with other options."""
        with patch("sys.argv", ["pg_build.py", "--prefix", str(tmp_path),
                                "--clean-worktrees", "--branch", "main"]):
            with pytest.raises(SystemExit):
                pg_build.main()

    @patch("pg_build.activate_script")
    def test_main_recreate_activate_script(self, mock_activate, tmp_path):
        """Should recreate activation script when flag is used."""
        with patch("sys.argv", ["pg_build.py", "--prefix", str(tmp_path),
                                "--recreate-activate-script"]):
            pg_build.main()
        mock_activate.assert_called_once()

    @patch("pg_build.build_instance")
    def test_main_build_primary(self, mock_build, tmp_path):
        """Should build primary instance."""
        with patch("sys.argv", ["pg_build.py", "--prefix", str(tmp_path),
                                "--branch", "main"]):
            pg_build.main()
        mock_build.assert_called_once()
        call_kwargs = mock_build.call_args
        assert "primary" in str(call_kwargs)

    @patch("pg_build.setup_replication")
    @patch("pg_build.build_instance")
    def test_main_build_with_replica(self, mock_build, mock_repl, tmp_path):
        """Should build replica and setup replication."""
        with patch("sys.argv", ["pg_build.py", "--prefix", str(tmp_path),
                                "--branch", "main", "--create-replica"]):
            pg_build.main()
        # Should build primary + replica = 2 calls
        assert mock_build.call_count == 2
        mock_repl.assert_called_once()

    @patch("pg_build.build_instance")
    def test_main_build_with_fdw(self, mock_build, tmp_path):
        """Should build FDW instance."""
        with patch("sys.argv", ["pg_build.py", "--prefix", str(tmp_path),
                                "--branch", "main", "--create-fdw"]):
            pg_build.main()
        # Should build primary + fdw = 2 calls
        assert mock_build.call_count == 2

    @patch("pg_build.build_instance")
    def test_main_custom_port(self, mock_build, tmp_path):
        """Should pass custom port to build_instance."""
        with patch("sys.argv", ["pg_build.py", "--prefix", str(tmp_path),
                                "--branch", "main", "--port", "9999"]):
            pg_build.main()
        call_args = mock_build.call_args
        assert 9999 in call_args[0] or 9999 in call_args[1].values()

    @patch("pg_build.build_instance")
    def test_main_default_port(self, mock_build, tmp_path):
        """Should use default port 5432."""
        with patch("sys.argv", ["pg_build.py", "--prefix", str(tmp_path),
                                "--branch", "main"]):
            pg_build.main()
        call_args = mock_build.call_args
        assert 5432 in call_args[0] or 5432 in call_args[1].values()


# ============================================================
# Edge case / integration-style tests
# ============================================================

class TestEdgeCases:
    """Edge case and integration-style tests."""

    def test_resolve_worktree_dirs_exact_match(self, tmp_prefix, tmp_worktrees):
        """Exact name match should work."""
        (tmp_worktrees / "exact_name").mkdir()
        result = pg_build.resolve_worktree_dirs(tmp_prefix, "exact_name")
        assert len(result) == 1

    def test_resolve_worktree_dirs_prefix_match(self, tmp_prefix, tmp_worktrees):
        """Prefix matching should return all matches with underscore boundary."""
        (tmp_worktrees / "prefix_a").mkdir()
        (tmp_worktrees / "prefix_b").mkdir()
        (tmp_worktrees / "prefixed_c").mkdir()
        (tmp_worktrees / "other").mkdir()
        result = pg_build.resolve_worktree_dirs(tmp_prefix, "prefix")
        assert len(result) == 2

    @patch("pg_build.subprocess.run")
    @patch("pg_build.run")
    def test_setup_worktree_with_tag(self, mock_run, mock_subproc, tmp_path):
        """Should work with tag reference."""
        repo_root = tmp_path / "source"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()
        worktree_dir = tmp_path / "worktree"

        mock_subproc.return_value = subprocess.CompletedProcess(
            args="", returncode=0, stdout="origin\nupstream\n", stderr=""
        )
        mock_run.return_value = subprocess.CompletedProcess(args="", returncode=0, stdout="", stderr="")

        result = pg_build.setup_worktree(repo_root, worktree_dir, None, "REL_16_0", None, "https://example.com/repo.git")
        assert result == worktree_dir.resolve()

    def test_activate_script_path_in_exports(self, tmp_path, saved_env):
        """PATH should include pg_home/bin and indent path."""
        pg_home = tmp_path / "pghome"
        pgdata = tmp_path / "pgdata"
        script = tmp_path / "activate.sh"
        indent_path = tmp_path / "indent"

        pg_build.activate_script(pg_home, pgdata, 5432, script, indent_path)

        content = script.read_text()
        assert f"{pg_home}/bin" in content
        assert str(indent_path) in content

    @patch("pg_build.run")
    def test_start_db_logfile_path(self, mock_run, tmp_path):
        """Logfile should be in pgdata directory."""
        pg_home = tmp_path / "pghome"
        pgdata = tmp_path / "pgdata"
        pgdata.mkdir(parents=True)
        env = {}

        pg_build.start_db(pg_home, pgdata, env)

        call_args = mock_run.call_args[0][0]
        assert str(pgdata / "logfile") in call_args
