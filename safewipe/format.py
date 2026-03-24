"""
format.py — Partition table creation, filesystem formatting, and mounting for safewipe.

Supports:
  Partition tables : MBR (msdos), GPT
  Filesystems      : FAT32, exFAT, ext4
  Mounting         : auto-mount to /media/<user>/<label>

Architecture:
- PartitionTableStrategy: Abstract pattern for partition table operations (OCP)
- FilesystemStrategy: Abstract pattern for filesystem formatting (OCP)
- MountStrategy: Abstract pattern for device mounting (OCP)
- PartitionTableManager: Handles parted operations (SRP)
- FilesystemFormatter: Handles mkfs operations (SRP)
- DeviceMounter: Handles mount and permission management (SRP)
"""

import os
import re
import shutil
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from safewipe import config
from safewipe.exceptions import (
    FilesystemError,
    MissingDependencyError,
    MountError,
    PartitionError,
)


# ──────────────────────────────────────────────────────────────
# Enumerations
# ──────────────────────────────────────────────────────────────

class PartitionTable(str, Enum):
    MBR = "mbr"
    GPT = "gpt"


class Filesystem(str, Enum):
    FAT32  = "fat32"
    EXFAT  = "exfat"
    EXT4   = "ext4"
    NONE   = "none"   # skip formatting


FS_DESCRIPTIONS = {
    Filesystem.FAT32:  "FAT32 — Universal (Windows/Mac/Linux/cameras/consoles)",
    Filesystem.EXFAT:  "exFAT — Large files >4 GB, cross-platform (needs exfatprogs)",
    Filesystem.EXT4:   "ext4  — Linux-native, journaled, best performance on Linux",
    Filesystem.NONE:   "None  — Skip formatting (partition table only)",
}

PT_DESCRIPTIONS = {
    PartitionTable.MBR: "MBR  — Legacy (BIOS), max 2 TB, max 4 primary partitions",
    PartitionTable.GPT: "GPT  — Modern (UEFI), >2 TB, up to 128 partitions",
}


@dataclass
class FormatResult:
    success: bool
    device_path: str
    partition_path: Optional[str]
    filesystem: Optional[Filesystem]
    label: Optional[str]
    mount_point: Optional[str]
    error_message: str = ""
    duration_seconds: float = 0.0


# ──────────────────────────────────────────────────────────────
# Tool availability checks
# ──────────────────────────────────────────────────────────────

def _require_tool(cmd: str, package: str) -> None:
    """Verify tool is available; raise MissingDependencyError if not."""
    if not shutil.which(cmd):
        raise MissingDependencyError(
            f"Required tool '{cmd}' not found. Install it with: apt install {package}"
        )


def check_format_deps(fs: Filesystem) -> list[str]:
    """Return list of missing tool names for the given filesystem."""
    missing = []
    required: dict[str, str] = {
        "parted": "parted",
        "partprobe": "parted",
    }
    if fs == Filesystem.FAT32:
        required["mkfs.fat"] = "dosfstools"
    elif fs == Filesystem.EXFAT:
        required["mkfs.exfat"] = "exfatprogs"
    elif fs == Filesystem.EXT4:
        required["mkfs.ext4"] = "e2fsprogs"

    for tool in required:
        if not shutil.which(tool):
            missing.append(tool)
    return missing


# ──────────────────────────────────────────────────────────────
# Abstract Strategies (Open/Closed Principle)
# ──────────────────────────────────────────────────────────────

class PartitionTableStrategy(ABC):
    """Abstract strategy for partition table operations.
    
    Enables new partition table types to be added without modifying
    existing code (Open/Closed Principle).
    """

    @abstractmethod
    def create_table(self, device_path: str, dry_run: bool = False) -> None:
        """Create a fresh partition table on device."""

    @abstractmethod
    def get_parted_type(self) -> str:
        """Get the parted label type (msdos, gpt, etc.)."""


class MBRStrategy(PartitionTableStrategy):
    """MBR (msdos) partition table strategy."""

    def get_parted_type(self) -> str:
        return "msdos"

    def create_table(self, device_path: str, dry_run: bool = False) -> None:
        if dry_run:
            return
        _require_tool("parted", "parted")
        result = subprocess.run(
            ["parted", "-s", device_path, "mklabel", self.get_parted_type()],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise PartitionError(
                f"Failed to create MBR partition table: {result.stderr.strip()}"
            )


class GPTStrategy(PartitionTableStrategy):
    """GPT partition table strategy."""

    def get_parted_type(self) -> str:
        return "gpt"

    def create_table(self, device_path: str, dry_run: bool = False) -> None:
        if dry_run:
            return
        _require_tool("parted", "parted")
        result = subprocess.run(
            ["parted", "-s", device_path, "mklabel", self.get_parted_type()],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise PartitionError(
                f"Failed to create GPT partition table: {result.stderr.strip()}"
            )


class FilesystemStrategy(ABC):
    """Abstract strategy for filesystem formatting.
    
    Enables new filesystems to be added without modifying existing code
    (Open/Closed Principle).
    """

    @abstractmethod
    def format(
        self, partition_path: str, label: Optional[str], dry_run: bool = False
    ) -> None:
        """Format partition with this filesystem."""

    @abstractmethod
    def get_mkfs_cmd(self, partition_path: str, label: str) -> list[str]:
        """Get the mkfs command for this filesystem."""


class FAT32Strategy(FilesystemStrategy):
    """FAT32 filesystem formatting strategy."""

    def get_mkfs_cmd(self, partition_path: str, label: str) -> list[str]:
        # FAT32 labels are max 11 chars, uppercase
        safe_label = label[:11].upper()
        return ["mkfs.fat", "-F", "32", "-n", safe_label, partition_path]

    def format(
        self, partition_path: str, label: Optional[str], dry_run: bool = False
    ) -> None:
        if dry_run:
            return
        _require_tool("mkfs.fat", "dosfstools")
        safe_label = (label or "SAFEWIPE")[:11].upper()
        cmd = self.get_mkfs_cmd(partition_path, safe_label)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise FilesystemError(
                f"mkfs.fat failed: {result.stderr.strip()}"
            )


class ExFATStrategy(FilesystemStrategy):
    """exFAT filesystem formatting strategy."""

    def get_mkfs_cmd(self, partition_path: str, label: str) -> list[str]:
        return ["mkfs.exfat", "-n", label, partition_path]

    def format(
        self, partition_path: str, label: Optional[str], dry_run: bool = False
    ) -> None:
        if dry_run:
            return
        _require_tool("mkfs.exfat", "exfatprogs")
        safe_label = label or "SAFEWIPE"
        cmd = self.get_mkfs_cmd(partition_path, safe_label)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise FilesystemError(
                f"mkfs.exfat failed: {result.stderr.strip()}"
            )


class EXT4Strategy(FilesystemStrategy):
    """ext4 filesystem formatting strategy."""

    def get_mkfs_cmd(self, partition_path: str, label: str) -> list[str]:
        return ["mkfs.ext4", "-L", label, "-q", partition_path]

    def format(
        self, partition_path: str, label: Optional[str], dry_run: bool = False
    ) -> None:
        if dry_run:
            return
        _require_tool("mkfs.ext4", "e2fsprogs")
        safe_label = label or "SAFEWIPE"
        cmd = self.get_mkfs_cmd(partition_path, safe_label)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise FilesystemError(
                f"mkfs.ext4 failed: {result.stderr.strip()}"
            )


# ──────────────────────────────────────────────────────────────
# Manager Classes (Single Responsibility Principle)
# ──────────────────────────────────────────────────────────────

class PartitionTableManager:
    """Manages partition table creation. Single responsibility: parted operations."""

    def __init__(self) -> None:
        self.strategies: dict[PartitionTable, PartitionTableStrategy] = {
            PartitionTable.MBR: MBRStrategy(),
            PartitionTable.GPT: GPTStrategy(),
        }

    def create_table(
        self, device_path: str, table_type: PartitionTable, dry_run: bool = False
    ) -> None:
        """Create a fresh partition table."""
        strategy = self.strategies.get(table_type)
        if not strategy:
            raise PartitionError(f"Unsupported partition table type: {table_type}")
        strategy.create_table(device_path, dry_run)

    def create_partition(
        self, device_path: str, table_type: PartitionTable, dry_run: bool = False
    ) -> str:
        """Create a single primary partition using 100% of the disk.
        Returns the partition device path (e.g. /dev/sdb1).
        """
        if dry_run:
            # Return predictable partition path for dry run
            return device_path + ("p1" if "nvme" in device_path else "1")

        _require_tool("parted", "parted")
        result = subprocess.run(
            [
                "parted", "-s", device_path,
                "mkpart", "primary",
                "1MiB", "100%",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise PartitionError(
                f"Failed to create partition: {result.stderr.strip()}"
            )

        # Notify kernel of partition table changes
        subprocess.run(
            ["partprobe", device_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        time.sleep(1)  # Allow kernel to register the new partition

        # Derive partition path based on device type
        if re.search(r"nvme\d+n\d+$", device_path):
            part_path = device_path + "p1"
        else:
            part_path = device_path + "1"

        # Wait for device node to appear
        timeout_secs = config.get_partition_detection_timeout()
        max_retries = config.get_partition_detection_retries()
        retry_interval = timeout_secs / max_retries

        for _ in range(max_retries):
            if Path(part_path).exists():
                return part_path
            time.sleep(retry_interval)

        raise PartitionError(
            f"Partition device {part_path} did not appear after partitioning "
            f"(waited {timeout_secs}s)"
        )


class FilesystemFormatter:
    """Formats filesystems. Single responsibility: mkfs operations."""

    def __init__(self) -> None:
        self.strategies: dict[Filesystem, FilesystemStrategy] = {
            Filesystem.FAT32: FAT32Strategy(),
            Filesystem.EXFAT: ExFATStrategy(),
            Filesystem.EXT4: EXT4Strategy(),
        }

    def format(
        self,
        partition_path: str,
        filesystem: Filesystem,
        label: Optional[str] = None,
        dry_run: bool = False,
    ) -> None:
        """Format partition with the given filesystem."""
        if filesystem == Filesystem.NONE:
            return

        strategy = self.strategies.get(filesystem)
        if not strategy:
            raise FilesystemError(f"Unsupported filesystem: {filesystem}")

        strategy.format(partition_path, label, dry_run)


def _get_current_user() -> str:
    """Get current user, accounting for sudo. Raises MountError if detection fails."""
    # If running with sudo, prefer SUDO_USER
    sudo_user = os.getenv("SUDO_USER")
    if sudo_user:
        return sudo_user

    # Fall back to environment variables
    user = os.getenv("USER") or os.getenv("LOGNAME")
    if user:
        return user

    # Last resort: try to get from id command
    try:
        result = subprocess.run(
            ["id", "-un"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        user = result.stdout.strip()
        if user:
            return user
    except Exception:
        pass

    raise MountError(
        "Unable to determine current user. Set USER or LOGNAME environment variable."
    )


class DeviceMounter:
    """Handles device mounting and permissions. Single responsibility: mount operations."""

    def mount(
        self,
        partition_path: str,
        label: Optional[str],
        dry_run: bool = False,
    ) -> str:
        """Mount the partition to /media/<user>/<label>.
        Returns the mount point path.
        """
        user = _get_current_user()
        mount_label = (label or "SAFEWIPE").replace(" ", "_")
        mount_base = config.get_mount_base()
        mount_point = mount_base / user / mount_label

        if dry_run:
            return str(mount_point)

        # Create mount point directory
        try:
            mount_point.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise MountError(
                f"Failed to create mount point {mount_point}: {e}"
            ) from e

        # Perform mount
        result = subprocess.run(
            ["mount", partition_path, str(mount_point)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise MountError(
                f"Failed to mount {partition_path} at {mount_point}: "
                f"{result.stderr.strip()}"
            )

        # Fix permissions so non-root user can write
        try:
            uid_result = subprocess.run(
                ["id", "-u", user],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
            gid_result = subprocess.run(
                ["id", "-g", user],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
            uid = int(uid_result.stdout.strip())
            gid = int(gid_result.stdout.strip())
            os.chown(str(mount_point), uid, gid)
        except Exception as e:
            # Log but don't fail — permissions may be acceptable as-is
            import sys
            print(
                f"Warning: Could not adjust mount point permissions: {e}",
                file=sys.stderr,
            )

        return str(mount_point)


def format_mount_label(label: Optional[str]) -> str:
    """Format a label for safe use as a mount path component."""
    return (label or "SAFEWIPE").replace(" ", "_")


# ──────────────────────────────────────────────────────────────
# High-level orchestrator
# ──────────────────────────────────────────────────────────────

def prepare_device(
    device_path: str,
    table_type: PartitionTable,
    filesystem: Filesystem,
    label: Optional[str],
    auto_mount: bool,
    dry_run: bool = False,
    status_callback: Optional[Callable[[str], None]] = None,
) -> FormatResult:
    """
    Full partition + format + (optional) mount workflow.
    
    This orchestrator coordinates the three main phases of device preparation:
    1. Partition table creation (via PartitionTableManager)
    2. Filesystem formatting (via FilesystemFormatter)
    3. Device mounting (via DeviceMounter)
    
    Args:
        device_path: Path to device (e.g., /dev/sdb)
        table_type: Partition table type (MBR or GPT)
        filesystem: Filesystem type (FAT32, exFAT, ext4, or NONE)
        label: Volume label for the filesystem
        auto_mount: Whether to mount after formatting
        dry_run: If True, simulate without making changes
        status_callback: Optional function to receive status messages
    
    Returns:
        FormatResult with success status and details
    """
    start = time.monotonic()

    def _status(msg: str) -> None:
        if status_callback:
            status_callback(msg)

    partition_path: Optional[str] = None
    mount_point: Optional[str] = None
    pt_manager = PartitionTableManager()
    fs_formatter = FilesystemFormatter()
    mounter = DeviceMounter()

    try:
        _status(f"Creating {table_type.value.upper()} partition table…")
        pt_manager.create_table(device_path, table_type, dry_run)

        _status("Creating primary partition…")
        partition_path = pt_manager.create_partition(device_path, table_type, dry_run)

        if filesystem != Filesystem.NONE:
            _status(f"Formatting as {filesystem.value.upper()}…")
            fs_formatter.format(partition_path, filesystem, label, dry_run)

        if auto_mount and filesystem != Filesystem.NONE:
            _status("Mounting to /media/…")
            mount_point = mounter.mount(partition_path, label, dry_run)

    except (PartitionError, FilesystemError, MountError, MissingDependencyError) as e:
        return FormatResult(
            success=False,
            device_path=device_path,
            partition_path=partition_path,
            filesystem=filesystem,
            label=label,
            mount_point=None,
            error_message=str(e),
            duration_seconds=time.monotonic() - start,
        )

    return FormatResult(
        success=True,
        device_path=device_path,
        partition_path=partition_path,
        filesystem=filesystem,
        label=label,
        mount_point=mount_point,
        duration_seconds=time.monotonic() - start,
    )
