"""
config.py — Configuration and environment variable management.

Loads configuration from:
1. .env file (if present)
2. Environment variables
3. Sensible defaults

All paths and timeouts are configurable via .env for flexibility and testing.
"""

import os
from pathlib import Path
from typing import Any, Optional

try:
    from dotenv import load_dotenv
except ImportError:
    # If dotenv is not installed, provide a no-op load_dotenv
    def load_dotenv(dotenv_path: Optional[Path] = None) -> bool:
        return False


def _load_env_file() -> None:
    """Load .env file from project root if it exists."""
    env_path = Path.cwd() / ".env"
    if env_path.exists():
        load_dotenv(env_path)


# Load environment variables on import
_load_env_file()


# ─────────────────────────────────────────────────────────────
# Configuration constants
# ─────────────────────────────────────────────────────────────


def get_log_dir() -> Path:
    """Get the directory for operation logs. Defaults to ~/.safewipe/logs"""
    path_str = os.getenv("SAFEWIPE_LOG_DIR", "~/.safewipe/logs")
    return Path(path_str).expanduser()


def get_mount_base() -> Path:
    """Get the base directory for mounting devices. Defaults to /media"""
    path_str = os.getenv("SAFEWIPE_MOUNT_BASE", "/media")
    return Path(path_str)


def get_log_retention_days() -> int:
    """Get number of days to retain logs before automatic cleanup. Defaults to 30"""
    return int(os.getenv("SAFEWIPE_LOG_RETENTION_DAYS", "30"))


def get_auto_mount() -> bool:
    """Should devices be automatically mounted after formatting? Defaults to True"""
    return os.getenv("SAFEWIPE_AUTO_MOUNT", "true").lower() in ("true", "1", "yes")


def get_verify_by_default() -> bool:
    """Should wipe verification run by default? Defaults to False"""
    return os.getenv("SAFEWIPE_VERIFY_BY_DEFAULT", "false").lower() in ("true", "1", "yes")


def get_block_size() -> int:
    """Get I/O block size for wipe operations (bytes). Defaults to 4 MiB"""
    return int(os.getenv("SAFEWIPE_BLOCK_SIZE", str(4 * 1024 * 1024)))


def get_quick_wipe_size() -> int:
    """Get size of quick wipe (header + footer bytes). Defaults to 10 MiB"""
    return int(os.getenv("SAFEWIPE_QUICK_WIPE_SIZE", str(10 * 1024 * 1024)))


def get_verify_sample_count() -> int:
    """Get number of random samples to verify during wipe verification. Defaults to 8"""
    return int(os.getenv("SAFEWIPE_VERIFY_SAMPLE_COUNT", "8"))


def get_verify_sample_size() -> int:
    """Get size of each verification sample (bytes). Defaults to 512 KiB"""
    return int(os.getenv("SAFEWIPE_VERIFY_SAMPLE_SIZE", str(512 * 1024)))


def get_mount_point_prefix() -> str:
    """Get the prefix for auto-generated mount point labels. Defaults to 'safewipe'"""
    return os.getenv("SAFEWIPE_MOUNT_LABEL_PREFIX", "safewipe")


def get_log_sensitive_data() -> bool:
    """Should sensitive data (serials, usernames) be included in logs? Defaults to False"""
    return os.getenv("SAFEWIPE_LOG_SENSITIVE_DATA", "false").lower() in ("true", "1", "yes")


def get_partition_detection_timeout() -> int:
    """Get timeout in seconds when waiting for partition to appear. Defaults to 5"""
    return int(os.getenv("SAFEWIPE_PARTITION_TIMEOUT", "5"))


def get_partition_detection_retries() -> int:
    """Get number of retries when waiting for partition. Defaults to 10"""
    return int(os.getenv("SAFEWIPE_PARTITION_RETRIES", "10"))


# ─────────────────────────────────────────────────────────────
# Validation helpers
# ─────────────────────────────────────────────────────────────


def validate_config() -> list[str]:
    """
    Validate configuration values. Returns a list of validation errors.
    Empty list means configuration is valid.
    """
    errors: list[str] = []

    block_size = get_block_size()
    if block_size <= 0 or block_size > 1024 * 1024 * 1024:  # 1 GB max
        errors.append(f"SAFEWIPE_BLOCK_SIZE must be between 1 and 1GB, got {block_size}")

    if get_log_retention_days() < 0:
        errors.append(f"SAFEWIPE_LOG_RETENTION_DAYS must be >= 0")

    if get_verify_sample_count() <= 0:
        errors.append(f"SAFEWIPE_VERIFY_SAMPLE_COUNT must be > 0")

    verify_size = get_verify_sample_size()
    if verify_size <= 0 or verify_size > 1024 * 1024 * 1024:
        errors.append(f"SAFEWIPE_VERIFY_SAMPLE_SIZE must be between 1 and 1GB")

    if get_partition_detection_timeout() <= 0:
        errors.append(f"SAFEWIPE_PARTITION_TIMEOUT must be > 0")

    if get_partition_detection_retries() <= 0:
        errors.append(f"SAFEWIPE_PARTITION_RETRIES must be > 0")

    return errors
