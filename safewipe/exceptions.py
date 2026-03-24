"""
exceptions.py — Custom exception hierarchy for safewipe.

Provides typed, descriptive exceptions for all error scenarios:
- SafeWipeError: Base exception for all safewipe errors
- DeviceError: Device discovery/validation failures
- WipeError: Wipe operation failures
- FormatError: Partitioning/filesystem failures
- ConfigError: Configuration/environment issues
"""


class SafeWipeError(Exception):
    """Base exception for all safewipe operations."""

    pass


class DeviceError(SafeWipeError):
    """Exception raised during device discovery, validation, or mount operations."""

    pass


class DeviceNotFoundError(DeviceError):
    """Device path does not exist or was not found in device listing."""

    pass


class DeviceMountedError(DeviceError):
    """Device is mounted and cannot be wiped without unmounting first."""

    pass


class SystemDiskError(DeviceError):
    """Operation attempted on system/boot disk without --force flag."""

    pass


class WipeError(SafeWipeError):
    """Exception raised during wipe operations."""

    pass


class WipeExecutionError(WipeError):
    """Wipe method execution failed (dd, blkdiscard, etc.)."""

    pass


class WipeVerificationError(WipeError):
    """Post-wipe verification failed or inconclusive."""

    pass


class FormatError(SafeWipeError):
    """Exception raised during partition/filesystem operations."""

    pass


class PartitionError(FormatError):
    """Partition table creation or modification failed."""

    pass


class FilesystemError(FormatError):
    """Filesystem creation or formatting failed."""

    pass


class MountError(FormatError):
    """Device mounting or permission management failed."""

    pass


class ConfigError(SafeWipeError):
    """Configuration or environment variable issue."""

    pass


class MissingDependencyError(SafeWipeError):
    """Required system utility is missing (e.g., lsblk, parted, mkfs)."""

    pass


class PermissionError_(SafeWipeError):
    """Operation requires elevated privileges (must run as root)."""

    pass
