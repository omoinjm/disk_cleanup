"""
logger.py — Structured operation logging for safewipe.

All operations are appended to ~/.safewipe/logs/safewipe-YYYY-MM-DD.log
in a JSON-lines format for easy parsing.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from safewipe import config
from safewipe.exceptions import SafeWipeError


class OperationLogger:
    """Manages structured operation logging to JSON lines files."""

    def __init__(self) -> None:
        """Initialize logger and ensure log directory exists."""
        self.log_dir = config.get_log_dir()
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _get_log_file(self) -> Path:
        """Get the log file path for today's date."""
        date_str = datetime.now().strftime("%Y-%m-%d")
        return self.log_dir / f"safewipe-{date_str}.log"

    def log_operation(
        self,
        operation: str,
        device_path: str,
        result: str,  # "success" | "failure" | "dry_run" | "aborted"
        details: Optional[dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> Path:
        """
        Append a structured log entry and return the log file path.

        Args:
            operation: Name of operation (e.g., "wipe", "format", "mount")
            device_path: Path to device (e.g., "/dev/sdb")
            result: Outcome of operation
            details: Additional structured data to log
            error: Error message if operation failed

        Returns:
            Path to the log file written to.

        Raises:
            SafeWipeError: If unable to write log file.
        """
        entry: dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "operation": operation,
            "device": device_path,
            "result": result,
            "pid": os.getpid(),
        }

        if config.get_log_sensitive_data():
            entry["user"] = os.getenv("USER") or os.getenv("LOGNAME") or "unknown"

        if details:
            entry.update(details)

        if error:
            entry["error"] = error

        log_file = self._get_log_file()

        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError as e:
            raise SafeWipeError(f"Failed to write log file {log_file}: {e}") from e

        return log_file

    def read_recent_logs(
        self, n: int = 20, operation: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """
        Read recent log entries from today's log file.

        Args:
            n: Maximum number of entries to return
            operation: Filter to only this operation type (e.g., "wipe")

        Returns:
            List of log entries as dictionaries, most recent first.
        """
        log_file = self._get_log_file()

        if not log_file.exists():
            return []

        entries: list[dict[str, Any]] = []

        try:
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        entry = json.loads(line)
                        if operation is None or entry.get("operation") == operation:
                            entries.append(entry)
                    except json.JSONDecodeError:
                        # Skip malformed lines
                        continue

        except OSError:
            # Return empty if unable to read
            return []

        # Return most recent first
        return list(reversed(entries[-n:]))


# Global logger instance
_logger = OperationLogger()


def log_operation(
    operation: str,
    device_path: str,
    result: str,
    details: Optional[dict[str, Any]] = None,
    error: Optional[str] = None,
) -> Path:
    """Module-level convenience function for logging operations."""
    return _logger.log_operation(operation, device_path, result, details, error)


def read_recent_logs(
    n: int = 20, operation: Optional[str] = None
) -> list[dict[str, Any]]:
    """Module-level convenience function for reading recent logs."""
    return _logger.read_recent_logs(n, operation)

    return log_file


def read_recent_logs(n: int = 20) -> list[dict]:
    """Return the last n log entries across all log files."""
    entries: list[dict] = []
    if not LOG_DIR.exists():
        return entries

    log_files = sorted(LOG_DIR.glob("safewipe-*.log"), reverse=True)
    for lf in log_files:
        try:
            lines = lf.read_text().strip().splitlines()
            for line in reversed(lines):
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
                if len(entries) >= n:
                    return entries
        except OSError:
            continue

    return entries
