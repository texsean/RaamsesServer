"""User-Reported Issues — generate log bundles and open email client.

When a user triggers "Report Issue" (equivalent to right-click on Windows),
this module:

  1. Collects the last 24 hours of server/agent logs into a zip file
  2. Opens the user's default email client with a pre-filled email to
     support@raamses.io containing:
       - Site ID
       - Agent ID
       - Reported vs actual status
       - Timestamp
  3. Opens the folder containing the log zip so the user can attach it

This is the Linux equivalent of the Windows right-click "Report Issue" action.
On Linux, it uses xdg-open for both the mailto: link and the folder browser.
On headless systems (no display), it returns the paths and mailto link
so the operator can handle it manually.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from rgs.site_config import get_site_id

logger = logging.getLogger(__name__)

SUPPORT_EMAIL = "support@raamses.io"
_DEFAULT_LOG_HOURS = 24
_DEFAULT_LOG_DIR = Path(".")  # Will be resolved relative to project root
_DEFAULT_OUTPUT_DIR = Path.home() / ".raamses" / "reports"


@dataclass
class IssueReport:
    """Result of a report-issue action."""
    site_id: str
    agent_id: str
    reported_status: str
    actual_status: str
    timestamp: str
    zip_path: Optional[str] = None
    mailto_url: Optional[str] = None
    folder_opened: bool = False
    email_opened: bool = False
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "site_id": self.site_id,
            "agent_id": self.agent_id,
            "reported_status": self.reported_status,
            "actual_status": self.actual_status,
            "timestamp": self.timestamp,
            "zip_path": self.zip_path,
            "mailto_url": self.mailto_url,
            "folder_opened": self.folder_opened,
            "email_opened": self.email_opened,
            "error": self.error,
        }


def _collect_logs(
    log_dir: Path,
    hours: int = _DEFAULT_LOG_HOURS,
    output_dir: Path = _DEFAULT_OUTPUT_DIR,
) -> Optional[str]:
    """Collect log files from the last N hours into a zip file.

    Returns the path to the created zip file, or None on failure.
    """
    if not log_dir.exists():
        logger.warning("Log directory does not exist: %s", log_dir)
        return None

    cutoff = datetime.now() - timedelta(hours=hours)

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate zip filename with timestamp
    ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = output_dir / f"raamses_logs_{ts_str}.zip"

    # Find log files modified within the time window
    log_files: list[Path] = []
    for fpath in log_dir.iterdir():
        if fpath.is_file() and fpath.suffix in (".log", ".txt"):
            try:
                mtime = datetime.fromtimestamp(fpath.stat().st_mtime)
                if mtime >= cutoff:
                    log_files.append(fpath)
            except OSError:
                continue

    if not log_files:
        logger.info("No log files found in %s within the last %d hours", log_dir, hours)
        # Still create an empty zip with a README
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "README.txt",
                f"Raamses log bundle created at {datetime.now(timezone.utc).isoformat()}\n"
                f"No log files found in {log_dir} within the last {hours} hours.\n",
            )
        return str(zip_path)

    # Create the zip file
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add a metadata file
        zf.writestr(
            "_metadata.txt",
            f"Raamses Log Bundle\n"
            f"Created: {datetime.now(timezone.utc).isoformat()}\n"
            f"Log directory: {log_dir}\n"
            f"Time window: last {hours} hours (since {cutoff.isoformat()})\n"
            f"Files included: {len(log_files)}\n"
            f"Site ID: {get_site_id()}\n",
        )
        for log_file in log_files:
            # Add file to zip with just its name (not full path)
            zf.write(log_file, arcname=log_file.name)

    logger.info("Created log bundle: %s (%d files)", zip_path, len(log_files))
    return str(zip_path)


def _build_mailto(
    site_id: str,
    agent_id: str,
    reported_status: str,
    actual_status: str,
    zip_filename: Optional[str] = None,
) -> str:
    """Build a mailto: URL with pre-filled email to support@raamses.io."""
    timestamp = datetime.now(timezone.utc).isoformat()

    subject = f"RAAMSES Issue Report — Site {site_id[:8]} — {timestamp[:10]}"

    body_lines = [
        "RAAMSES Issue Report",
        "=" * 40,
        f"Site ID:          {site_id}",
        f"Agent ID:         {agent_id}",
        f"Timestamp:        {timestamp}",
        f"Platform:         {platform.system()} {platform.machine()}",
        "",
        "Reported Status:",
        f"  {reported_status}",
        "",
        "Actual Status:",
        f"  {actual_status}",
        "",
        "Discrepancy Description:",
        "  (Please describe the issue you observed)",
        "",
    ]

    if zip_filename:
        body_lines.extend([
            "Log Bundle:",
            f"  Please attach: {zip_filename}",
            f"  (The folder containing this file has been opened for your convenience)",
            "",
        ])

    body_lines.extend([
        "Additional Notes:",
        "  (Add any additional context here)",
        "",
        f"-- RAAMSES Gateway Server",
    ])

    body = "\n".join(body_lines)

    # URL-encode subject and body for mailto:
    from urllib.parse import quote
    encoded_subject = quote(subject)
    encoded_body = quote(body)

    return f"mailto:{SUPPORT_EMAIL}?subject={encoded_subject}&body={encoded_body}"


def _open_email_client(mailto_url: str) -> bool:
    """Open the user's default email client with the mailto: URL.

    Returns True if the command was launched, False otherwise.
    On headless systems, this will fail gracefully.
    """
    system = platform.system()

    try:
        if system == "Linux":
            # Check if we have a display
            if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
                logger.info("No display detected — email client not opened")
                return False
            # Try xdg-open (standard on most Linux desktops)
            if shutil.which("xdg-open"):
                subprocess.Popen(
                    ["xdg-open", mailto_url],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True
            # Fallback: trygio open (GNOME)
            if shutil.which("gio"):
                subprocess.Popen(
                    ["gio", "open", mailto_url],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True

        elif system == "Windows":
            os.startfile(mailto_url)  # type: ignore[attr-defined]
            return True

        elif system == "Darwin":
            subprocess.Popen(
                ["open", mailto_url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True

    except Exception as e:
        logger.warning("Failed to open email client: %s", e)
        return False

    return False


def _open_folder(folder_path: Path) -> bool:
    """Open the file manager at the given folder path.

    Returns True if the command was launched, False otherwise.
    On headless systems, this will fail gracefully.
    """
    system = platform.system()

    try:
        if system == "Linux":
            if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
                logger.info("No display detected — folder not opened")
                return False
            if shutil.which("xdg-open"):
                subprocess.Popen(
                    ["xdg-open", str(folder_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True

        elif system == "Windows":
            os.startfile(str(folder_path))  # type: ignore[attr-defined]
            return True

        elif system == "Darwin":
            subprocess.Popen(
                ["open", str(folder_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True

    except Exception as e:
        logger.warning("Failed to open folder: %s", e)
        return False

    return False


def report_issue(
    agent_id: str,
    reported_status: str = "",
    actual_status: str = "",
    log_dir: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    hours: int = _DEFAULT_LOG_HOURS,
    open_apps: bool = True,
) -> IssueReport:
    """Generate a user-reported issue bundle.

    This is the main entry point for the "Report Issue" action.

    Args:
        agent_id:         The agent ID the issue is about
        reported_status:  What the agent/user reported (the claim)
        actual_status:    What was actually observed
        log_dir:          Directory containing log files (default: project root or gateway.log dir)
        output_dir:       Where to save the zip (default: ~/.raamses/reports/)
        hours:            How many hours of logs to include (default: 24)
        open_apps:        Whether to open email client + folder browser (default: True)

    Returns:
        IssueReport with all the generated paths and status info.
    """
    # Resolve paths
    if log_dir is None:
        # Default: look for logs in the current working directory (where gateway runs)
        log_dir = Path.cwd()
    else:
        log_dir = Path(log_dir)

    if output_dir is None:
        output_dir = _DEFAULT_OUTPUT_DIR
    else:
        output_dir = Path(output_dir)

    timestamp = datetime.now(timezone.utc).isoformat()
    site_id = get_site_id()

    # Collect logs into a zip
    zip_path = _collect_logs(log_dir, hours, output_dir)

    # Build mailto URL
    zip_filename = Path(zip_path).name if zip_path else None
    mailto_url = _build_mailto(
        site_id=site_id,
        agent_id=agent_id,
        reported_status=reported_status or "(not specified)",
        actual_status=actual_status or "(not specified)",
        zip_filename=zip_filename,
    )

    # Open email client and folder
    email_opened = False
    folder_opened = False

    if open_apps:
        if zip_path:
            folder_opened = _open_folder(Path(zip_path).parent)
        email_opened = _open_email_client(mailto_url)

    report = IssueReport(
        site_id=site_id,
        agent_id=agent_id,
        reported_status=reported_status,
        actual_status=actual_status,
        timestamp=timestamp,
        zip_path=zip_path,
        mailto_url=mailto_url,
        folder_opened=folder_opened,
        email_opened=email_opened,
    )

    logger.info(
        "Issue report generated: site=%s agent=%s zip=%s email_opened=%s folder_opened=%s",
        site_id, agent_id, zip_path, email_opened, folder_opened,
    )

    return report