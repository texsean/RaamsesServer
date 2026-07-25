"""Tests for report_issue.py — log zip generation and email/folder handling."""
import json
import os
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from rgs.report_issue import (
    report_issue,
    _collect_logs,
    _build_mailto,
    SUPPORT_EMAIL,
    IssueReport,
)
from rgs.site_config import SiteConfig


class TestCollectLogs:
    """Test the log collection into zip files."""

    def test_collects_recent_log_files(self, tmp_path):
        """Should collect .log files from the last 24 hours."""
        # Create some log files
        log1 = tmp_path / "server.log"
        log1.write_text("server log line 1\n")
        log2 = tmp_path / "agent.log"
        log2.write_text("agent log line 1\n")
        # Create an old file (outside the time window)
        old_log = tmp_path / "old.log"
        old_log.write_text("old log\n")
        old_time = datetime.now() - timedelta(hours=48)
        os.utime(str(old_log), (old_time.timestamp(), old_time.timestamp()))

        output_dir = tmp_path / "output"
        zip_path = _collect_logs(tmp_path, hours=24, output_dir=output_dir)

        assert zip_path is not None
        assert Path(zip_path).exists()

        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            assert "server.log" in names
            assert "agent.log" in names
            assert "old.log" not in names
            assert "_metadata.txt" in names

    def test_creates_zip_even_with_no_logs(self, tmp_path):
        """Should create a zip with README even if no logs found."""
        output_dir = tmp_path / "output"
        zip_path = _collect_logs(tmp_path, hours=24, output_dir=output_dir)

        assert zip_path is not None
        assert Path(zip_path).exists()

        with zipfile.ZipFile(zip_path, "r") as zf:
            assert "README.txt" in zf.namelist()

    def test_handles_nonexistent_log_dir(self, tmp_path):
        """Should return None if log directory doesn't exist."""
        zip_path = _collect_logs(tmp_path / "nonexistent", hours=24, output_dir=tmp_path)
        assert zip_path is None

    def test_only_collects_log_files(self, tmp_path):
        """Should only collect .log and .txt files."""
        (tmp_path / "server.log").write_text("log\n")
        (tmp_path / "readme.txt").write_text("txt\n")
        (tmp_path / "data.json").write_text("{}")
        (tmp_path / "binary.bin").write_bytes(b"\x00\x01")

        output_dir = tmp_path / "output"
        zip_path = _collect_logs(tmp_path, hours=24, output_dir=output_dir)

        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            assert "server.log" in names
            assert "readme.txt" in names
            assert "data.json" not in names
            assert "binary.bin" not in names


class TestBuildMailto:
    """Test the mailto: URL builder."""

    def test_builds_mailto_url(self, tmp_path, monkeypatch):
        """Should build a valid mailto: URL."""
        # Use a temp site config to avoid clobbering the real one
        config_path = tmp_path / "site.json"
        monkeypatch.setenv("RAAMSES_SITE_CONFIG", str(config_path))

        from rgs.site_config import _site_config
        # Reset the singleton
        import rgs.site_config as sc
        sc._site_config = None

        url = _build_mailto(
            site_id="test-site-id",
            agent_id="agent-001",
            reported_status="agent says idle",
            actual_status="actually working",
            zip_filename="raamses_logs_20260725.zip",
        )

        assert url.startswith(f"mailto:{SUPPORT_EMAIL}")
        assert "subject=" in url
        assert "body=" in url
        assert "test-site-id" in url
        assert "agent-001" in url
        assert "raamses_logs_20260725.zip" in url

    def test_mailto_without_zip_filename(self, tmp_path, monkeypatch):
        """Should build mailto without zip filename if not provided."""
        config_path = tmp_path / "site.json"
        monkeypatch.setenv("RAAMSES_SITE_CONFIG", str(config_path))

        url = _build_mailto(
            site_id="site-x",
            agent_id="agent-002",
            reported_status="status A",
            actual_status="status B",
        )

        assert url.startswith(f"mailto:{SUPPORT_EMAIL}")
        assert "Log%20Bundle" not in url  # no zip section


class TestReportIssue:
    """Test the main report_issue function."""

    def test_returns_issue_report_dataclass(self, tmp_path, monkeypatch):
        """Should return an IssueReport object."""
        config_path = tmp_path / "site.json"
        monkeypatch.setenv("RAAMSES_SITE_CONFIG", str(config_path))

        # Reset the singleton
        import rgs.site_config as sc
        sc._site_config = None

        # Create a log file
        (tmp_path / "gateway.log").write_text("test log\n")

        report = report_issue(
            agent_id="agent-001",
            reported_status="idle",
            actual_status="active",
            log_dir=tmp_path,
            output_dir=tmp_path / "reports",
            open_apps=False,
        )

        assert isinstance(report, IssueReport)
        assert report.agent_id == "agent-001"
        assert report.reported_status == "idle"
        assert report.actual_status == "active"
        assert report.zip_path is not None
        assert Path(report.zip_path).exists()
        assert report.mailto_url is not None
        assert report.email_opened is False  # open_apps=False
        assert report.folder_opened is False

    def test_to_dict_serializes_all_fields(self, tmp_path, monkeypatch):
        """IssueReport.to_dict() should include all fields."""
        config_path = tmp_path / "site.json"
        monkeypatch.setenv("RAAMSES_SITE_CONFIG", str(config_path))

        import rgs.site_config as sc
        sc._site_config = None

        (tmp_path / "gateway.log").write_text("log\n")

        report = report_issue(
            agent_id="a1",
            reported_status="s1",
            actual_status="s2",
            log_dir=tmp_path,
            output_dir=tmp_path / "reports",
            open_apps=False,
        )

        d = report.to_dict()
        assert "site_id" in d
        assert "agent_id" in d
        assert "reported_status" in d
        assert "actual_status" in d
        assert "timestamp" in d
        assert "zip_path" in d
        assert "mailto_url" in d
        assert "folder_opened" in d
        assert "email_opened" in d
        assert "error" in d

    def test_includes_site_id_in_report(self, tmp_path, monkeypatch):
        """Report should include a valid site ID."""
        config_path = tmp_path / "site.json"
        monkeypatch.setenv("RAAMSES_SITE_CONFIG", str(config_path))

        import rgs.site_config as sc
        sc._site_config = None

        report = report_issue(
            agent_id="a1",
            log_dir=tmp_path,
            output_dir=tmp_path / "reports",
            open_apps=False,
        )

        assert report.site_id is not None
        assert len(report.site_id) == 36  # UUID format