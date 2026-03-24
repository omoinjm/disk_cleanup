"""
device.py — Device discovery, validation, and safety checks for safewipe.

Responsible for:
- Enumerating block devices via lsblk
- Detecting system/boot disks
- Checking mount status
- Auto-unmounting with user confirmation
- Enforcing safety rules

Architecture (Single Responsibility Principle):
- SystemDiskDetector: Detects system/boot disks
- MountpointResolver: Resolves and queries mount points
- DeviceDiscovery: Coordinates device enumeration
- DeviceValidator: Validates devices for wipe operations
- BlockDevice: Data model for block devices
"""

import json
import re
import subprocess
from dataclasses import dataclass, field
from typing import Optional

from safewipe.exceptions import (
    DeviceError,
    DeviceMountedError,
    MissingDependencyError,
    SystemDiskError,
)


# ──────────────────────────────────────────────────────────────
# Data model
# ──────────────────────────────────────────────────────────────


@dataclass
class BlockDevice:
    """
    Represents a block device (disk, partition, or loop device).

    Attributes:
        name: Device name without /dev prefix (e.g. "sdb")
        path: Full device path (e.g. "/dev/sdb")
        size: Human-readable size (e.g. "32G")
        size_bytes: Size in bytes
        model: Device model string
        vendor: Device vendor string
        tran: Transport type (usb, sata, nvme, etc.)
        removable: Whether the device is removable
        ro: Whether the device is read-only
        mount_points: List of mount points for this device
        children: Child partitions of this device
        is_system: Whether this is a system/boot disk
        hotplug: Whether the device supports hotplug
        serial: Device serial number
    """

    name: str
    path: str
    size: str
    size_bytes: int
    model: str
    vendor: str
    tran: str
    removable: bool
    ro: bool
    mount_points: list[str] = field(default_factory=list)
    children: list["BlockDevice"] = field(default_factory=list)
    is_system: bool = False
    hotplug: bool = False
    serial: str = ""

    @property
    def display_name(self) -> str:
        """Return a user-friendly display name for this device."""
        parts = [self.model or self.vendor or "Unknown device"]
        if self.serial:
            parts.append(f"(s/n {self.serial[:12]})")
        return " ".join(parts)

    @property
    def is_mounted(self) -> bool:
        """Check if this device or any of its children are mounted."""
        if self.mount_points:
            return True
        return any(c.is_mounted for c in self.children)

    @property
    def all_mount_points(self) -> list[str]:
        """Get all mount points from this device and its children."""
        mps = list(self.mount_points)
        for c in self.children:
            mps.extend(c.all_mount_points)
        return mps

    @property
    def transport_icon(self) -> str:
        """Return an emoji icon representing the transport type."""
        icons = {"usb": "🔌", "sata": "💾", "nvme": "⚡", "mmc": "📱"}
        return icons.get(self.tran, "🖴")


# ──────────────────────────────────────────────────────────────
# System Disk Detector (SRP: Single Responsibility)
# ──────────────────────────────────────────────────────────────


class SystemDiskDetector:
    """
    Detects which devices are system/boot disks.

    This class encapsulates all logic for determining whether a device
    contains critical system filesystems (/, /boot, /home, etc.).
    """

    # Critical system mount points
    SYSTEM_MOUNTS = {"/", "/boot", "/boot/efi", "/usr", "/var", "/home"}

    def detect_system_devices(self) -> set[str]:
        """
        Determine which devices are 'system' disks.

        Returns:
            Set of device paths like {'/dev/sda'} that contain system mounts.

        Raises:
            DeviceError: If system detection fails completely.
        """
        system_devs: set[str] = set()

        # Try findmnt first (more reliable)
        system_devs.update(self._detect_via_findmnt())

        # Fall back to /proc/mounts
        system_devs.update(self._detect_via_proc_mounts())

        return system_devs

    def _detect_via_findmnt(self) -> set[str]:
        """
        Detect system devices using findmnt command.

        Returns:
            Set of device paths found via findmnt, or empty set if unavailable.
        """
        system_devs: set[str] = set()

        try:
            result = subprocess.run(
                ["findmnt", "--json", "--output", "SOURCE,TARGET"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0:
                try:
                    data = json.loads(result.stdout)
                    for fs in data.get("filesystems", []):
                        self._walk_findmnt_tree(fs, system_devs)
                except json.JSONDecodeError as e:
                    # Silently continue - we have proc/mounts fallback
                    pass
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            # findmnt not available or timed out - that's okay
            pass

        return system_devs

    def _walk_findmnt_tree(self, node: dict, system_devs: set[str]) -> None:
        """Recursively walk findmnt tree to find system mounts."""
        source = node.get("source", "")
        target = node.get("target", "")
        if target in self.SYSTEM_MOUNTS and source.startswith("/dev/"):
            base = re.sub(r"p?\d+$", "", source)
            system_devs.add(source)
            system_devs.add(base)
        for child in node.get("children") or []:
            self._walk_findmnt_tree(child, system_devs)

    def _detect_via_proc_mounts(self) -> set[str]:
        """
        Detect system devices using /proc/mounts as fallback.

        Returns:
            Set of device paths found in /proc/mounts, or empty set if unavailable.
        """
        system_devs: set[str] = set()

        try:
            with open("/proc/mounts") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        source, target = parts[0], parts[1]
                        if target in self.SYSTEM_MOUNTS and source.startswith(
                            "/dev/"
                        ):
                            base = re.sub(r"p?\d+$", "", source)
                            system_devs.add(source)
                            system_devs.add(base)
        except (FileNotFoundError, OSError, IOError):
            # /proc/mounts not available - that's okay on non-Linux
            pass

        return system_devs


# ──────────────────────────────────────────────────────────────
# Mountpoint Resolver (SRP: Single Responsibility)
# ──────────────────────────────────────────────────────────────


class MountpointResolver:
    """
    Resolves and retrieves mount point information for devices.

    This class handles all queries about which mount points
    are currently mounted on which devices.
    """

    def get_mount_points_from_lsblk(
        self, node: dict
    ) -> list[str]:
        """
        Extract mount points from an lsblk node.

        Args:
            node: Dictionary from lsblk JSON output.

        Returns:
            List of mount point paths (empty list for unmounted devices).
        """
        mount_points = node.get("mountpoints") or []
        # lsblk may return [null] for empty/unmounted devices
        return [m for m in mount_points if m]


# ──────────────────────────────────────────────────────────────
# Device Discovery (Coordinator)
# ──────────────────────────────────────────────────────────────


class DeviceDiscovery:
    """
    Coordinates device discovery and enumeration.

    Orchestrates lsblk parsing, system disk detection, and device tree
    construction. Implements the Coordinator pattern.
    """

    def __init__(self) -> None:
        """Initialize discovery with detector and resolver instances."""
        self.system_detector = SystemDiskDetector()
        self.mount_resolver = MountpointResolver()

    def list_devices(self, include_loop: bool = False) -> list[BlockDevice]:
        """
        Return all top-level block disks, annotated with system-disk status.

        Args:
            include_loop: If True, include loop devices; otherwise exclude them.

        Returns:
            List of BlockDevice objects representing top-level devices.

        Raises:
            MissingDependencyError: If lsblk is not available.
            DeviceError: If device discovery fails.
        """
        try:
            raw = self._fetch_lsblk_json()
        except FileNotFoundError:
            raise MissingDependencyError(
                "lsblk not found — is util-linux installed?"
            )
        except subprocess.CalledProcessError as e:
            raise DeviceError(f"lsblk failed: {e.stderr.strip()}")
        except json.JSONDecodeError as e:
            raise DeviceError(f"Failed to parse lsblk output: {e}")

        system_devs = self.system_detector.detect_system_devices()
        devices: list[BlockDevice] = []

        for node in raw.get("blockdevices", []):
            if node.get("type") not in ("disk", "loop"):
                continue
            if node.get("type") == "loop" and not include_loop:
                continue

            dev = self._parse_device(node)
            if dev is None:
                continue

            # Mark as system if device or any child is a system device
            if dev.path in system_devs:
                dev.is_system = True
            for child in dev.children:
                if child.path in system_devs:
                    dev.is_system = True

            devices.append(dev)

        return devices

    def _fetch_lsblk_json(self) -> dict:
        """
        Run lsblk and return parsed JSON output.

        Returns:
            Dictionary containing lsblk JSON output.

        Raises:
            FileNotFoundError: If lsblk is not available.
            subprocess.CalledProcessError: If lsblk fails.
            json.JSONDecodeError: If JSON parsing fails.
        """
        cmd = [
            "lsblk",
            "--json",
            "--output",
            "NAME,SIZE,MODEL,VENDOR,TRAN,RM,RO,MOUNTPOINTS,HOTPLUG,SERIAL,TYPE",
            "--bytes",
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10, check=True
        )
        return json.loads(result.stdout)

    def _parse_device(self, node: dict) -> Optional[BlockDevice]:
        """
        Recursively parse a single lsblk node into a BlockDevice.

        Handles missing/null fields gracefully.

        Args:
            node: Dictionary from lsblk JSON output.

        Returns:
            BlockDevice instance, or None if node is not a valid device type.
        """
        if node.get("type") not in ("disk", "part", "loop"):
            return None

        name = node.get("name", "")
        if not name:
            return None

        # Parse size_bytes, handling missing/invalid fields
        # When lsblk is called with --bytes, the SIZE column is numeric (key: "size")
        # Otherwise, check for SIZEBYTES column or SIZE-BYTES variant
        size_bytes_raw = (
            node.get("sizebytes")
            or node.get("size-bytes", 0)
            or node.get("size", 0)
            or 0
        )
        try:
            size_bytes = int(size_bytes_raw)
        except (ValueError, TypeError):
            size_bytes = 0

        # Parse mount points
        mount_points = self.mount_resolver.get_mount_points_from_lsblk(node)

        # Recursively parse children
        children_raw = node.get("children") or []
        children = [c for c in (self._parse_device(ch) for ch in children_raw) if c]

        return BlockDevice(
            name=name,
            path=f"/dev/{name}",
            size=node.get("size", "?"),
            size_bytes=size_bytes,
            model=(node.get("model") or "").strip(),
            vendor=(node.get("vendor") or "").strip(),
            tran=(node.get("tran") or "").strip().lower(),
            removable=bool(node.get("rm", False)),
            ro=bool(node.get("ro", False)),
            mount_points=mount_points,
            children=children,
            hotplug=bool(node.get("hotplug", False)),
            serial=(node.get("serial") or "").strip(),
        )


# ──────────────────────────────────────────────────────────────
# Device Validator (SRP: Single Responsibility)
# ──────────────────────────────────────────────────────────────


class DeviceValidator:
    """
    Validates devices for wipe operations and related safety checks.

    This class encapsulates all device validation logic, producing
    human-readable warnings about why a device may not be safe to wipe.
    """

    def validate_wipe_target(
        self, device: BlockDevice, force: bool = False
    ) -> list[str]:
        """
        Validate a device as a wipe target.

        Returns a list of warning strings. Warnings prefixed with 'CRITICAL:'
        should prevent wiping unless force=True.

        Args:
            device: The BlockDevice to validate.
            force: If True, suppress critical warnings for system disks.

        Returns:
            List of warning strings (may be empty if device is valid).
        """
        warnings: list[str] = []

        if device.ro:
            warnings.append("CRITICAL: Device is read-only.")

        if device.is_system and not force:
            warnings.append(
                "CRITICAL: This appears to be a system disk. "
                "Use --force to override (DANGEROUS)."
            )

        if device.size_bytes == 0:
            warnings.append("WARNING: Device reports 0 bytes — may be invalid.")

        if device.is_mounted:
            mps = ", ".join(device.all_mount_points)
            warnings.append(f"WARNING: Device is currently mounted at: {mps}")

        return warnings


# ──────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────

# Create module-level discovery and validator instances
_discovery = DeviceDiscovery()
_validator = DeviceValidator()


def list_devices(include_loop: bool = False) -> list[BlockDevice]:
    """
    Return all top-level block disks, annotated with system-disk status.

    Loop devices are excluded unless include_loop=True.

    Args:
        include_loop: If True, include loop devices; otherwise exclude them.

    Returns:
        List of BlockDevice objects representing top-level devices.

    Raises:
        MissingDependencyError: If lsblk is not available.
        DeviceError: If device discovery fails.
    """
    return _discovery.list_devices(include_loop=include_loop)


def get_device_by_path(path: str) -> Optional[BlockDevice]:
    """
    Find a device by its /dev path.

    Searches both top-level devices and their partitions.

    Args:
        path: Device path like "/dev/sdb" or "/dev/sdb1".

    Returns:
        BlockDevice instance if found, None otherwise.
    """
    for dev in list_devices(include_loop=True):
        if dev.path == path:
            return dev
        for child in dev.children:
            if child.path == path:
                return child
    return None


def validate_wipe_target(
    device: BlockDevice,
    force: bool = False,
) -> list[str]:
    """
    Return a list of warning strings for a wipe target.

    Warnings prefixed with 'CRITICAL:' indicate the operation should be
    aborted unless force=True.

    Args:
        device: The BlockDevice to validate.
        force: If True, suppress critical warnings for system disks.

    Returns:
        List of warning strings (may be empty if device is valid).
    """
    return _validator.validate_wipe_target(device, force=force)


# ──────────────────────────────────────────────────────────────
# Mount management
# ──────────────────────────────────────────────────────────────


def unmount_device(device: BlockDevice, dry_run: bool = False) -> list[str]:
    """
    Unmount all partitions of a device.

    Attempts standard unmount first, then lazy unmount if that fails.

    Args:
        device: The BlockDevice to unmount.
        dry_run: If True, return what would be unmounted without actually unmounting.

    Returns:
        List of mount points that were successfully unmounted.

    Raises:
        DeviceMountedError: If unmounting fails and lazy unmount also fails.
    """
    unmounted: list[str] = []

    # Collect all mount points from device + children
    targets: list[tuple[str, str]] = []
    if device.mount_points:
        targets.extend([(device.path, mp) for mp in device.mount_points])
    for child in device.children:
        if child.mount_points:
            targets.extend([(child.path, mp) for mp in child.mount_points])

    for dev_path, mp in targets:
        if dry_run:
            unmounted.append(mp)
            continue

        # Try standard unmount
        result = subprocess.run(
            ["umount", mp], capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
            # Try lazy unmount as fallback
            result2 = subprocess.run(
                ["umount", "-l", mp], capture_output=True, text=True, check=False
            )
            if result2.returncode != 0:
                raise DeviceMountedError(
                    f"Failed to unmount {mp}: {result.stderr.strip()}"
                )
        unmounted.append(mp)

    return unmounted
