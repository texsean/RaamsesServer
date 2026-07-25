"""Trust but Verify — filesystem and Git timestamp inspection.

This module answers verification questions by checking actual file system
and Git repository timestamps, rather than trusting what an agent claims.

Key capabilities:
  - last_repo_activity() -> human-readable string (e.g. "last commit was Thursday, 3 days ago")
  - last_files_modified(n) -> list of recently modified files
  - recent_project_updates(n) -> list of recently updated directories
  - verify_agent_claims(claims) -> detect discrepancies between what an
    agent says and what the filesystem/git actually shows

Usage from the RAAMSES protocol:
  - Gateway command: /verify <agent_id> [question]
  - HTTP endpoint:    GET /verify?agent_id=...&question=...
  - HTTP endpoint:    POST /verify with JSON body
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _run_git(repo_path: Path, args: list[str]) -> Optional[str]:
    """Run a git command and return stdout, or None on failure."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path)] + args,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.debug("git command failed in %s: %s", repo_path, e)
    return None


def _humanize_timedelta(delta: timedelta) -> str:
    """Convert a timedelta into a human-readable relative time string."""
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return f"{seconds} seconds ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    if days < 7:
        return f"{days} day{'s' if days != 1 else ''} ago"
    weeks = days // 7
    if weeks < 4:
        return f"{weeks} week{'s' if weeks != 1 else ''} ago"
    months = days // 30
    if months < 12:
        return f"{months} month{'s' if months != 1 else ''} ago"
    years = days // 365
    return f"{years} year{'s' if years != 1 else ''} ago"


def _parse_git_timestamp(ts_str: str) -> Optional[datetime]:
    """Parse a git ISO timestamp into a timezone-aware datetime."""
    # Git log --format=%cI produces ISO 8601 (e.g. 2026-07-25T14:23:18+00:00)
    try:
        return datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        return None


@dataclass
class FileActivity:
    """A recently modified file."""
    path: str
    modified_at: datetime
    size_bytes: int

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "modified_at": self.modified_at.isoformat(),
            "size_bytes": self.size_bytes,
        }


@dataclass
class ProjectUpdate:
    """A recently updated project directory."""
    path: str
    modified_at: datetime
    file_count: int

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "modified_at": self.modified_at.isoformat(),
            "file_count": self.file_count,
        }


@dataclass
class RepoActivity:
    """Git repository activity summary."""
    repo_path: str
    last_commit_hash: Optional[str] = None
    last_commit_message: Optional[str] = None
    last_commit_author: Optional[str] = None
    last_commit_at: Optional[datetime] = None
    human_readable: Optional[str] = None  # "last commit was Thursday, 3 days ago"
    total_commits: int = 0

    def to_dict(self) -> dict:
        return {
            "repo_path": self.repo_path,
            "last_commit_hash": self.last_commit_hash,
            "last_commit_message": self.last_commit_message,
            "last_commit_author": self.last_commit_author,
            "last_commit_at": self.last_commit_at.isoformat() if self.last_commit_at else None,
            "lastRepoActivity": self.human_readable,  # field name matches protocol spec
            "total_commits": self.total_commits,
        }


@dataclass
class VerificationResult:
    """Result of a trust-but-verify check."""
    agent_id: str
    question: str
    answer: str
    evidence: dict = field(default_factory=dict)
    discrepancies: list = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "question": self.question,
            "answer": self.answer,
            "evidence": self.evidence,
            "discrepancies": self.discrepancies,
            "timestamp": self.timestamp,
        }


class TrustVerifier:
    """Trust but Verify engine for the RAAMSES gateway.

    Inspects file system and Git timestamps to answer verification questions
    and detect discrepancies between agent claims and actual activity.

    Parameters:
        project_root:  The root directory to scan for file activity (default: cwd)
        log_retention: How far back to look for file modifications (default: 7 days)
    """

    QUESTIONS = {
        "last_files": "Last three files worked on and saved",
        "project_updates": "Recent project folder updates",
        "repo_activity": "Last GitHub repository activity",
    }

    def __init__(
        self,
        project_root: Optional[Path] = None,
        log_retention_days: int = 7,
    ) -> None:
        self._project_root = Path(project_root) if project_root else Path.cwd()
        self._retention = timedelta(days=log_retention_days)
        # Common directories to skip during file scans
        self._skip_dirs = {
            ".git", "__pycache__", "node_modules", ".venv", "venv",
            ".idea", ".vscode", "build", "dist", ".mypy_cache", ".pytest_cache",
            "htmlcov", ".tox", ".eggs",
        }
        # File extensions to track (source/config files, not binaries)
        self._track_extensions = {
            ".py", ".cpp", ".h", ".hpp", ".c", ".js", ".ts", ".json",
            ".yaml", ".yml", ".xml", ".md", ".txt", ".cfg", ".ini",
            ".sh", ".cmake", ".rs", ".go", ".java", ".cs",
        }

    # ── Public API ────────────────────────────────────────────────────────

    def last_files_modified(self, n: int = 3) -> list[FileActivity]:
        """Return the N most recently modified tracked files in the project."""
        cutoff = datetime.now(timezone.utc) - self._retention
        results: list[FileActivity] = []

        for root, dirs, files in os.walk(self._project_root):
            # Prune skip directories
            dirs[:] = [d for d in dirs if d not in self._skip_dirs and not d.startswith(".git")]

            for fname in files:
                fpath = Path(root) / fname
                ext = fpath.suffix.lower()
                if ext not in self._track_extensions:
                    continue
                try:
                    stat = fpath.stat()
                    mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                    if mtime >= cutoff:
                        results.append(FileActivity(
                            path=str(fpath.relative_to(self._project_root)),
                            modified_at=mtime,
                            size_bytes=stat.st_size,
                        ))
                except (OSError, ValueError):
                    continue

        # Sort by modification time descending
        results.sort(key=lambda f: f.modified_at, reverse=True)
        return results[:n]

    def recent_project_updates(self, n: int = 5) -> list[ProjectUpdate]:
        """Return the N most recently updated directories in the project."""
        cutoff = datetime.now(timezone.utc) - self._retention
        results: list[ProjectUpdate] = []

        for root, dirs, files in os.walk(self._project_root):
            dirs[:] = [d for d in dirs if d not in self._skip_dirs and not d.startswith(".git")]
            dirpath = Path(root)
            try:
                rel = dirpath.relative_to(self._project_root)
                if str(rel) == ".":
                    continue
            except ValueError:
                continue

            # Find the most recent file modification in this directory
            latest_mtime: Optional[datetime] = None
            file_count = 0
            for fname in files:
                fpath = dirpath / fname
                try:
                    stat = fpath.stat()
                    mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                    file_count += 1
                    if latest_mtime is None or mtime > latest_mtime:
                        latest_mtime = mtime
                except (OSError, ValueError):
                    continue

            if latest_mtime and latest_mtime >= cutoff:
                results.append(ProjectUpdate(
                    path=str(rel),
                    modified_at=latest_mtime,
                    file_count=file_count,
                ))

        results.sort(key=lambda p: p.modified_at, reverse=True)
        return results[:n]

    def last_repo_activity(self) -> RepoActivity:
        """Return the last Git commit activity for this repository."""
        repo = RepoActivity(repo_path=str(self._project_root))

        # Get last commit details
        log_output = _run_git(self._project_root, [
            "log", "-1", "--format=%H%n%cI%n%an%n%s"
        ])
        if log_output:
            lines = log_output.split("\n")
            if len(lines) >= 4:
                repo.last_commit_hash = lines[0] if lines else None
                if len(lines) > 1:
                    repo.last_commit_at = _parse_git_timestamp(lines[1])
                if len(lines) > 2:
                    repo.last_commit_author = lines[2]
                if len(lines) > 3:
                    repo.last_commit_message = "\n".join(lines[3:])

        # Total commit count
        count_output = _run_git(self._project_root, ["rev-list", "--count", "HEAD"])
        if count_output and count_output.isdigit():
            repo.total_commits = int(count_output)

        # Build human-readable string
        if repo.last_commit_at:
            now = datetime.now(timezone.utc).astimezone()
            commit_time = repo.last_commit_at.astimezone()
            delta = now - commit_time
            relative = _humanize_timedelta(delta)
            # Get the day name
            day_name = commit_time.strftime("%A")
            repo.human_readable = f"last commit from this agent was {day_name}, {relative}"
        else:
            repo.human_readable = "no git activity found"

        return repo

    def verify_agent_claims(
        self,
        agent_id: str,
        claims: dict,
    ) -> VerificationResult:
        """Verify an agent's claims against actual filesystem/git state.

        Args:
            agent_id: The agent to verify
            claims: Dict of claim_name -> claimed_value. Supported claims:
                - "last_file": agent claims this was the last file worked on
                - "current_task": agent claims to be working on this
                - "repo_active": agent claims repo activity (bool or timestamp)

        Returns:
            VerificationResult with any discrepancies found
        """
        discrepancies: list[str] = []
        evidence: dict = {}

        # Check last_file claim
        if "last_file" in claims:
            claimed_file = claims["last_file"]
            actual_files = self.last_files_modified(1)
            if actual_files:
                actual_file = actual_files[0].path
                evidence["claimed_last_file"] = claimed_file
                evidence["actual_last_file"] = actual_file
                evidence["actual_last_file_mtime"] = actual_files[0].modified_at.isoformat()
                if Path(claimed_file).name != Path(actual_file).name:
                    discrepancies.append(
                        f"Agent claims last file was '{claimed_file}' "
                        f"but filesystem shows '{actual_file}' was modified most recently"
                    )
            else:
                evidence["actual_last_file"] = None

        # Check current_task claim (look for recently modified files matching the task)
        if "current_task" in claims:
            claimed_task = claims["current_task"]
            actual_files = self.last_files_modified(3)
            evidence["claimed_current_task"] = claimed_task
            evidence["recent_files"] = [f.to_dict() for f in actual_files]
            # If no files modified in the last hour, the task may not be actively running
            one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
            recent_active = any(f.modified_at > one_hour_ago for f in actual_files)
            evidence["task_actively_modifying"] = recent_active
            if not recent_active and claimed_task and claimed_task != "idle":
                discrepancies.append(
                    f"Agent claims to be working on '{claimed_task}' "
                    f"but no files modified in the last hour"
                )

        # Check repo_active claim
        if "repo_active" in claims:
            repo = self.last_repo_activity()
            evidence["repo_activity"] = repo.to_dict()
            claimed_active = claims["repo_active"]
            if repo.last_commit_at:
                # If the agent claims activity but last commit was >24h ago
                day_ago = datetime.now(timezone.utc) - timedelta(hours=24)
                if claimed_active is True and repo.last_commit_at.astimezone() < day_ago:
                    discrepancies.append(
                        f"Agent claims repo is active but last commit was "
                        f"{repo.human_readable}"
                    )

        answer = "verified" if not discrepancies else "discrepancies found"
        return VerificationResult(
            agent_id=agent_id,
            question="verify_agent_claims",
            answer=answer,
            evidence=evidence,
            discrepancies=discrepancies,
        )

    def answer_question(self, agent_id: str, question: str) -> VerificationResult:
        """Answer a natural-language verification question.

        Supported questions (case-insensitive substring match):
            - "last files" / "files worked on" -> last 3 modified files
            - "project" / "folder updates"      -> recent project directory updates
            - "repo" / "git" / "github"         -> last repository activity
        """
        q_lower = question.lower().strip()

        if "file" in q_lower or "worked on" in q_lower or "saved" in q_lower:
            files = self.last_files_modified(3)
            answer = f"Last {len(files)} files worked on and saved:\n"
            for i, f in enumerate(files, 1):
                answer += f"  {i}. {f.path} (modified {f.modified_at.isoformat()})"
            evidence = {"files": [f.to_dict() for f in files]}

        elif "project" in q_lower or "folder" in q_lower:
            updates = self.recent_project_updates(5)
            answer = f"Recent project folder updates ({len(updates)}):\n"
            for i, u in enumerate(updates, 1):
                answer += f"  {i}. {u.path} ({u.file_count} files, last modified {u.modified_at.isoformat()})"
            evidence = {"project_updates": [u.to_dict() for u in updates]}

        elif "repo" in q_lower or "git" in q_lower or "github" in q_lower:
            repo = self.last_repo_activity()
            answer = f"Last GitHub repository activity: {repo.human_readable}"
            if repo.last_commit_message:
                answer += f"\n  Commit: {repo.last_commit_hash[:8]} — {repo.last_commit_message}"
            if repo.last_commit_author:
                answer += f"\n  Author: {repo.last_commit_author}"
            evidence = repo.to_dict()

        else:
            answer = f"Unknown verification question: '{question}'. "
            answer += "Supported: 'last files', 'project updates', 'repo activity'."
            evidence = {}

        return VerificationResult(
            agent_id=agent_id,
            question=question,
            answer=answer,
            evidence=evidence,
        )