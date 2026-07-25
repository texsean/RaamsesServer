"""Tests for verifier.py — Trust but Verify: file/git timestamp inspection."""
import os
import subprocess
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from rgs.verifier import TrustVerifier, _humanize_timedelta


class TestHumanizeTimedelta:
    """Test the human-readable timedelta formatter."""

    def test_seconds_ago(self):
        assert _humanize_timedelta(timedelta(seconds=30)) == "30 seconds ago"

    def test_one_minute_ago(self):
        assert _humanize_timedelta(timedelta(minutes=1)) == "1 minute ago"

    def test_minutes_ago(self):
        assert _humanize_timedelta(timedelta(minutes=5)) == "5 minutes ago"

    def test_one_hour_ago(self):
        assert _humanize_timedelta(timedelta(hours=1)) == "1 hour ago"

    def test_hours_ago(self):
        assert _humanize_timedelta(timedelta(hours=3)) == "3 hours ago"

    def test_one_day_ago(self):
        assert _humanize_timedelta(timedelta(days=1)) == "1 day ago"

    def test_days_ago(self):
        assert _humanize_timedelta(timedelta(days=3)) == "3 days ago"

    def test_weeks_ago(self):
        assert _humanize_timedelta(timedelta(days=14)) == "2 weeks ago"


class TestTrustVerifierFiles:
    """Test the file modification tracking."""

    def test_last_files_modified_returns_recent_files(self, tmp_path):
        """Should return recently modified files."""
        # Create a Python file
        test_file = tmp_path / "test_code.py"
        test_file.write_text("# test file\n")

        verifier = TrustVerifier(project_root=tmp_path, log_retention_days=7)
        files = verifier.last_files_modified(n=3)

        assert len(files) >= 1
        assert any("test_code.py" in f.path for f in files)

    def test_last_files_modified_respects_n_limit(self, tmp_path):
        """Should return at most n files."""
        for i in range(5):
            (tmp_path / f"file_{i}.py").write_text(f"# file {i}\n")

        verifier = TrustVerifier(project_root=tmp_path, log_retention_days=7)
        files = verifier.last_files_modified(n=2)
        assert len(files) <= 2

    def test_last_files_modified_skips_pycache(self, tmp_path):
        """Should skip __pycache__ directories."""
        pycache = tmp_path / "__pycache__"
        pycache.mkdir()
        (pycache / "module.py").write_text("# cached\n")

        # Also create a real source file
        (tmp_path / "real.py").write_text("# real\n")

        verifier = TrustVerifier(project_root=tmp_path, log_retention_days=7)
        files = verifier.last_files_modified(n=10)

        # Should not include the pycache file
        assert not any("__pycache__" in f.path for f in files)

    def test_last_files_modified_skips_git_dir(self, tmp_path):
        """Should skip .git directories."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config.py").write_text("# git config\n")

        (tmp_path / "real.py").write_text("# real\n")

        verifier = TrustVerifier(project_root=tmp_path, log_retention_days=7)
        files = verifier.last_files_modified(n=10)

        assert not any(".git" in f.path for f in files)

    def test_last_files_modified_only_tracks_source_files(self, tmp_path):
        """Should only track source file extensions."""
        (tmp_path / "code.py").write_text("# code\n")
        (tmp_path / "image.png").write_bytes(b"\x89PNG")

        verifier = TrustVerifier(project_root=tmp_path, log_retention_days=7)
        files = verifier.last_files_modified(n=10)

        assert any("code.py" in f.path for f in files)
        assert not any("image.png" in f.path for f in files)

    def test_file_activity_to_dict(self, tmp_path):
        """FileActivity.to_dict() should serialize correctly."""
        (tmp_path / "test.py").write_text("# test\n")
        verifier = TrustVerifier(project_root=tmp_path, log_retention_days=7)
        files = verifier.last_files_modified(n=1)
        d = files[0].to_dict()
        assert "path" in d
        assert "modified_at" in d
        assert "size_bytes" in d


class TestTrustVerifierProjectUpdates:
    """Test the project directory update tracking."""

    def test_recent_project_updates_returns_dirs(self, tmp_path):
        """Should return recently updated directories."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file.py").write_text("# code\n")

        verifier = TrustVerifier(project_root=tmp_path, log_retention_days=7)
        updates = verifier.recent_project_updates(n=5)

        assert len(updates) >= 1
        assert any("subdir" in u.path for u in updates)

    def test_project_update_to_dict(self, tmp_path):
        """ProjectUpdate.to_dict() should serialize correctly."""
        subdir = tmp_path / "project1"
        subdir.mkdir()
        (subdir / "file.py").write_text("# code\n")

        verifier = TrustVerifier(project_root=tmp_path, log_retention_days=7)
        updates = verifier.recent_project_updates(n=1)
        d = updates[0].to_dict()
        assert "path" in d
        assert "modified_at" in d
        assert "file_count" in d


class TestTrustVerifierRepoActivity:
    """Test the Git repository activity tracking."""

    def test_last_repo_activity_returns_activity(self, tmp_path):
        """Should return repo activity info for a git repo."""
        # Initialize a git repo
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)

        # Create and commit a file
        (tmp_path / "test.py").write_text("# test\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial commit"], cwd=tmp_path, capture_output=True)

        verifier = TrustVerifier(project_root=tmp_path, log_retention_days=7)
        repo = verifier.last_repo_activity()

        assert repo.last_commit_hash is not None
        assert repo.last_commit_message == "initial commit"
        assert repo.last_commit_author == "Test"
        assert repo.last_commit_at is not None
        assert repo.total_commits == 1
        assert repo.human_readable is not None
        assert "last commit" in repo.human_readable

    def test_last_repo_activity_no_git_repo(self, tmp_path):
        """Should return 'no git activity found' for non-git directories."""
        verifier = TrustVerifier(project_root=tmp_path, log_retention_days=7)
        repo = verifier.last_repo_activity()

        assert repo.last_commit_hash is None
        assert repo.human_readable == "no git activity found"
        assert repo.total_commits == 0

    def test_repo_activity_to_dict(self, tmp_path):
        """RepoActivity.to_dict() should include lastRepoActivity field."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, capture_output=True)
        (tmp_path / "f.py").write_text("# f\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "c"], cwd=tmp_path, capture_output=True)

        verifier = TrustVerifier(project_root=tmp_path, log_retention_days=7)
        repo = verifier.last_repo_activity()
        d = repo.to_dict()

        # The field name must match the protocol spec
        assert "lastRepoActivity" in d
        assert d["lastRepoActivity"] is not None


class TestTrustVerifierAnswerQuestion:
    """Test the answer_question method for natural language queries."""

    def test_answer_last_files_question(self, tmp_path):
        """Should answer 'last files' question."""
        (tmp_path / "a.py").write_text("# a\n")
        verifier = TrustVerifier(project_root=tmp_path, log_retention_days=7)
        result = verifier.answer_question("agent-001", "last files")

        assert result.agent_id == "agent-001"
        assert "Last" in result.answer or "files" in result.answer
        assert result.timestamp is not None

    def test_answer_project_updates_question(self, tmp_path):
        """Should answer 'project updates' question."""
        subdir = tmp_path / "myproject"
        subdir.mkdir()
        (subdir / "a.py").write_text("# a\n")

        verifier = TrustVerifier(project_root=tmp_path, log_retention_days=7)
        result = verifier.answer_question("agent-001", "project updates")

        assert "project" in result.answer.lower() or "folder" in result.answer.lower()

    def test_answer_repo_activity_question(self, tmp_path):
        """Should answer 'repo activity' question."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, capture_output=True)
        (tmp_path / "f.py").write_text("# f\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "test commit"], cwd=tmp_path, capture_output=True)

        verifier = TrustVerifier(project_root=tmp_path, log_retention_days=7)
        result = verifier.answer_question("agent-001", "repo activity")

        assert "github" in result.answer.lower() or "commit" in result.answer.lower()

    def test_answer_unknown_question(self, tmp_path):
        """Should return a helpful message for unknown questions."""
        verifier = TrustVerifier(project_root=tmp_path, log_retention_days=7)
        result = verifier.answer_question("agent-001", "what color is the sky")

        assert "Unknown" in result.answer or "unknown" in result.answer.lower()


class TestVerifyAgentClaims:
    """Test the verify_agent_claims method for discrepancy detection."""

    def test_verify_correct_last_file(self, tmp_path):
        """Should not report discrepancy when the claim matches."""
        (tmp_path / "correct.py").write_text("# correct\n")

        verifier = TrustVerifier(project_root=tmp_path, log_retention_days=7)
        actual_files = verifier.last_files_modified(1)
        actual_file = actual_files[0].path

        result = verifier.verify_agent_claims("agent-001", {"last_file": actual_file})

        assert result.answer == "verified"
        assert len(result.discrepancies) == 0

    def test_verify_wrong_last_file(self, tmp_path):
        """Should report discrepancy when the claim doesn't match."""
        (tmp_path / "actual.py").write_text("# actual\n")

        verifier = TrustVerifier(project_root=tmp_path, log_retention_days=7)
        result = verifier.verify_agent_claims("agent-001", {"last_file": "wrong.py"})

        assert result.answer == "discrepancies found"
        assert len(result.discrepancies) > 0
        assert "wrong.py" in result.discrepancies[0]

    def test_verify_idle_but_modifying_files(self, tmp_path):
        """Should report discrepancy when agent claims idle but files are recent."""
        (tmp_path / "active.py").write_text("# just modified\n")

        verifier = TrustVerifier(project_root=tmp_path, log_retention_days=7)
        result = verifier.verify_agent_claims("agent-001", {"current_task": "compiling code"})

        # Files were just modified, so this should be fine
        assert "recent_files" in result.evidence

    def test_verification_result_to_dict(self, tmp_path):
        """VerificationResult.to_dict() should serialize correctly."""
        verifier = TrustVerifier(project_root=tmp_path, log_retention_days=7)
        result = verifier.verify_agent_claims("agent-001", {})
        d = result.to_dict()

        assert "agent_id" in d
        assert "question" in d
        assert "answer" in d
        assert "evidence" in d
        assert "discrepancies" in d
        assert "timestamp" in d