"""
wipe.py — Wipe strategies, execution engine, and verification for safewipe.

Supports:
  - quick    : zero the first and last 10 MB (fast, for quick reuse)
  - zero     : full overwrite with /dev/zero
  - random   : full overwrite with /dev/urandom
  - secure   : 3-pass (zero, random, zero) — DoD 5220.22-M inspired
  - blkdiscard: SSD TRIM/discard (hardware-level erase)

Architecture:
  - WipeStrategy (abstract): Defines the wipe interface (Open/Closed Principle)
  - Concrete strategies: QuickWipeStrategy, ZeroWipeStrategy, etc.
  - WipeVerifier (Single Responsibility): Handles verification logic
  - wipe_device(): Main entry point, delegates to strategies

Progress is emitted via a callback so the UI layer stays decoupled.
"""

import abc
import os
import random
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from safewipe import config
from safewipe.device import BlockDevice
from safewipe.exceptions import (
    MissingDependencyError,
    WipeError,
    WipeExecutionError,
    WipeVerificationError,
)


# ──────────────────────────────────────────────────────────────
# Type aliases
# ──────────────────────────────────────────────────────────────

ProgressCallback = Callable[["WipeProgress"], None]


# ──────────────────────────────────────────────────────────────
# Enumerations & data classes
# ──────────────────────────────────────────────────────────────

class WipeMethod(str, Enum):
    """Wipe method enum — do NOT change existing values."""
    QUICK      = "quick"
    ZERO       = "zero"
    RANDOM     = "random"
    SECURE     = "secure"
    BLKDISCARD = "blkdiscard"


METHOD_DESCRIPTIONS = {
    WipeMethod.QUICK:      "Zero first & last 10 MB only (instant, not secure)",
    WipeMethod.ZERO:       "Full overwrite with zeros (fast, recoverable with forensics)",
    WipeMethod.RANDOM:     "Full overwrite with random data (secure, slow on large disks)",
    WipeMethod.SECURE:     "3-pass wipe: zero → random → zero (DoD-grade, slowest)",
    WipeMethod.BLKDISCARD: "SSD TRIM discard (fastest on SSDs, hardware-level erase)",
}

METHOD_PASS_COUNT = {
    WipeMethod.QUICK:      1,
    WipeMethod.ZERO:       1,
    WipeMethod.RANDOM:     1,
    WipeMethod.SECURE:     3,
    WipeMethod.BLKDISCARD: 1,
}


@dataclass
class WipeProgress:
    """Snapshot of wipe progress, emitted to the progress callback."""
    method: WipeMethod
    pass_number: int
    total_passes: int
    bytes_written: int
    total_bytes: int
    elapsed_seconds: float
    pass_label: str = ""

    @property
    def percent(self) -> float:
        """Calculate overall wipe percentage."""
        if self.total_bytes == 0:
            return 0.0
        overall_done = (self.pass_number - 1) * self.total_bytes + self.bytes_written
        overall_total = self.total_passes * self.total_bytes
        return min(100.0, overall_done / overall_total * 100)

    @property
    def speed_bytes_per_sec(self) -> float:
        """Calculate current write speed in bytes per second."""
        if self.elapsed_seconds == 0:
            return 0.0
        return self.bytes_written / self.elapsed_seconds

    @property
    def eta_seconds(self) -> Optional[float]:
        """Estimate time remaining in seconds."""
        remaining = self.total_bytes * self.total_passes - (
            (self.pass_number - 1) * self.total_bytes + self.bytes_written
        )
        if self.speed_bytes_per_sec == 0:
            return None
        return remaining / self.speed_bytes_per_sec


@dataclass
class WipeResult:
    """Result of a wipe operation."""
    success: bool
    method: WipeMethod
    device_path: str
    duration_seconds: float
    bytes_wiped: int
    passes_completed: int
    error_message: str = ""
    verified: bool = False
    verification_passed: Optional[bool] = None
    log_path: Optional[Path] = None

# ──────────────────────────────────────────────────────────────
# Progress callback type
# ──────────────────────────────────────────────────────────────

# (defined above with type aliases)


# ──────────────────────────────────────────────────────────────
# Abstract WipeStrategy (Open/Closed Principle)
# ──────────────────────────────────────────────────────────────


class WipeStrategy(abc.ABC):
    """
    Abstract base class for wipe strategies.

    Implements the Open/Closed Principle: open for extension (new strategies),
    closed for modification (existing strategies don't change). Each strategy
    encapsulates its own wipe logic and pass management.
    """

    @abc.abstractmethod
    def execute(
        self,
        device: BlockDevice,
        progress_cb: Optional[ProgressCallback] = None,
        dry_run: bool = False,
    ) -> WipeResult:
        """
        Execute the wipe strategy.

        Args:
            device: The BlockDevice to wipe.
            progress_cb: Optional callback for progress updates.
            dry_run: If True, simulate without modifying the device.

        Returns:
            WipeResult with success/failure details.
        """
        pass


class QuickWipeStrategy(WipeStrategy):
    """
    Quick wipe: zeros the first and last 10 MB of the device.
    Fastest strategy, suitable for quick device reuse.
    """

    def execute(
        self,
        device: BlockDevice,
        progress_cb: Optional[ProgressCallback] = None,
        dry_run: bool = False,
    ) -> WipeResult:
        """Zero the first and last 10 MB of the device."""
        start = time.monotonic()
        quick_size = config.get_quick_wipe_size()
        block_size = config.get_block_size()
        written = 0

        if not dry_run:
            try:
                zeros = b"\x00" * block_size
                with open(device.path, "wb", buffering=0) as f:
                    # First section
                    remaining = quick_size
                    while remaining > 0:
                        chunk = min(block_size, remaining)
                        f.write(zeros[:chunk])
                        written += chunk
                        remaining -= chunk
                        if progress_cb:
                            progress_cb(WipeProgress(
                                method=WipeMethod.QUICK,
                                pass_number=1,
                                total_passes=1,
                                bytes_written=written,
                                total_bytes=quick_size * 2,
                                elapsed_seconds=time.monotonic() - start,
                                pass_label="Zeroing header",
                            ))
                    # Last section
                    if device.size_bytes > quick_size * 2:
                        f.seek(device.size_bytes - quick_size)
                        remaining = quick_size
                        while remaining > 0:
                            chunk = min(block_size, remaining)
                            f.write(zeros[:chunk])
                            written += chunk
                            remaining -= chunk
                            if progress_cb:
                                progress_cb(WipeProgress(
                                    method=WipeMethod.QUICK,
                                    pass_number=1,
                                    total_passes=1,
                                    bytes_written=written,
                                    total_bytes=quick_size * 2,
                                    elapsed_seconds=time.monotonic() - start,
                                    pass_label="Zeroing footer",
                                ))
                    os.fsync(f.fileno())
            except OSError as e:
                raise WipeExecutionError(
                    f"Quick wipe failed on {device.path}: {e}"
                ) from e
        else:
            if progress_cb:
                for i in range(1, 11):
                    time.sleep(0.05)
                    progress_cb(WipeProgress(
                        method=WipeMethod.QUICK,
                        pass_number=1,
                        total_passes=1,
                        bytes_written=i * quick_size // 5,
                        total_bytes=quick_size * 2,
                        elapsed_seconds=time.monotonic() - start,
                        pass_label="Quick wipe (dry run)",
                    ))
            written = quick_size * 2

        return WipeResult(
            success=True,
            method=WipeMethod.QUICK,
            device_path=device.path,
            duration_seconds=time.monotonic() - start,
            bytes_wiped=written,
            passes_completed=1,
        )


class ZeroWipeStrategy(WipeStrategy):
    """
    Zero wipe: full overwrite with zeros from /dev/zero.
    Fast, but data is recoverable with forensics tools.
    """

    def execute(
        self,
        device: BlockDevice,
        progress_cb: Optional[ProgressCallback] = None,
        dry_run: bool = False,
    ) -> WipeResult:
        """Execute single-pass zero wipe."""
        return self._run_pass_strategy(
            device=device,
            method=WipeMethod.ZERO,
            passes=[("/dev/zero", "Writing zeros")],
            progress_cb=progress_cb,
            dry_run=dry_run,
        )

    def _run_pass_strategy(
        self,
        device: BlockDevice,
        method: WipeMethod,
        passes: list[tuple[str, str]],
        progress_cb: Optional[ProgressCallback],
        dry_run: bool,
    ) -> WipeResult:
        """Execute multi-pass wipe strategy."""
        start = time.monotonic()
        total_bytes = device.size_bytes
        total_written = 0

        try:
            for idx, (source, label) in enumerate(passes, 1):
                written = self._run_dd_pass(
                    source=source,
                    dest_path=device.path,
                    total_bytes=total_bytes,
                    pass_number=idx,
                    total_passes=len(passes),
                    method=method,
                    pass_label=label,
                    progress_cb=progress_cb,
                    dry_run=dry_run,
                )
                total_written += written
        except OSError as e:
            raise WipeExecutionError(
                f"Wipe failed on {device.path}: {e}"
            ) from e

        return WipeResult(
            success=True,
            method=method,
            device_path=device.path,
            duration_seconds=time.monotonic() - start,
            bytes_wiped=total_written,
            passes_completed=len(passes),
        )

    def _run_dd_pass(
        self,
        source: str,
        dest_path: str,
        total_bytes: int,
        pass_number: int,
        total_passes: int,
        method: WipeMethod,
        pass_label: str,
        progress_cb: Optional[ProgressCallback],
        dry_run: bool,
    ) -> int:
        """Stream source → dest using Python's open() for granular progress."""
        block_size = config.get_block_size()

        if dry_run:
            written = 0
            start = time.monotonic()
            chunk = min(block_size, total_bytes)
            while written < total_bytes:
                to_write = min(chunk, total_bytes - written)
                written += to_write
                time.sleep(0.02)
                if progress_cb:
                    progress_cb(WipeProgress(
                        method=method,
                        pass_number=pass_number,
                        total_passes=total_passes,
                        bytes_written=written,
                        total_bytes=total_bytes,
                        elapsed_seconds=time.monotonic() - start,
                        pass_label=pass_label,
                    ))
            return written

        written = 0
        start = time.monotonic()
        buf = bytearray(block_size)

        src_fd = None
        dst_fd = None
        try:
            if source == "/dev/zero":
                dst_fd = open(dest_path, "wb", buffering=0)
                while written < total_bytes:
                    to_write = min(block_size, total_bytes - written)
                    dst_fd.write(memoryview(buf)[:to_write])
                    written += to_write
                    if progress_cb:
                        progress_cb(WipeProgress(
                            method=method,
                            pass_number=pass_number,
                            total_passes=total_passes,
                            bytes_written=written,
                            total_bytes=total_bytes,
                            elapsed_seconds=time.monotonic() - start,
                            pass_label=pass_label,
                        ))
            else:
                src_fd = open(source, "rb", buffering=0)
                dst_fd = open(dest_path, "wb", buffering=0)
                while written < total_bytes:
                    to_write = min(block_size, total_bytes - written)
                    data = src_fd.read(to_write)
                    if not data:
                        break
                    dst_fd.write(data)
                    written += len(data)
                    if progress_cb:
                        progress_cb(WipeProgress(
                            method=method,
                            pass_number=pass_number,
                            total_passes=total_passes,
                            bytes_written=written,
                            total_bytes=total_bytes,
                            elapsed_seconds=time.monotonic() - start,
                            pass_label=pass_label,
                        ))
        finally:
            if src_fd:
                src_fd.close()
            if dst_fd:
                try:
                    dst_fd.flush()
                    os.fsync(dst_fd.fileno())
                except OSError:
                    pass
                dst_fd.close()

        return written


class RandomWipeStrategy(WipeStrategy):
    """
    Random wipe: full overwrite with random data from /dev/urandom.
    More secure than zero, but slower.
    """

    def execute(
        self,
        device: BlockDevice,
        progress_cb: Optional[ProgressCallback] = None,
        dry_run: bool = False,
    ) -> WipeResult:
        """Execute single-pass random wipe."""
        strategy = ZeroWipeStrategy()
        return strategy._run_pass_strategy(
            device=device,
            method=WipeMethod.RANDOM,
            passes=[("/dev/urandom", "Writing random data")],
            progress_cb=progress_cb,
            dry_run=dry_run,
        )


class SecureWipeStrategy(WipeStrategy):
    """
    Secure wipe: 3-pass DoD 5220.22-M inspired pattern.
    Pass 1: zeros, Pass 2: random, Pass 3: zeros.
    Slowest but most secure for magnetic media.
    """

    def execute(
        self,
        device: BlockDevice,
        progress_cb: Optional[ProgressCallback] = None,
        dry_run: bool = False,
    ) -> WipeResult:
        """Execute 3-pass secure wipe."""
        strategy = ZeroWipeStrategy()
        return strategy._run_pass_strategy(
            device=device,
            method=WipeMethod.SECURE,
            passes=[
                ("/dev/zero",    "Pass 1/3: Zeros"),
                ("/dev/urandom", "Pass 2/3: Random"),
                ("/dev/zero",    "Pass 3/3: Zeros"),
            ],
            progress_cb=progress_cb,
            dry_run=dry_run,
        )


class BlkdiscardStrategy(WipeStrategy):
    """
    Blkdiscard: SSD TRIM/discard via the blkdiscard utility.
    Fastest on SSDs with TRIM support, hardware-level erase.
    """

    def execute(
        self,
        device: BlockDevice,
        progress_cb: Optional[ProgressCallback] = None,
        dry_run: bool = False,
    ) -> WipeResult:
        """Execute blkdiscard-based wipe."""
        start = time.monotonic()

        if not shutil.which("blkdiscard"):
            raise MissingDependencyError(
                "blkdiscard not found — install util-linux"
            )

        if dry_run:
            time.sleep(0.5)
            return WipeResult(
                success=True,
                method=WipeMethod.BLKDISCARD,
                device_path=device.path,
                duration_seconds=time.monotonic() - start,
                bytes_wiped=0,
                passes_completed=1,
            )

        result = subprocess.run(
            ["blkdiscard", "-f", device.path],
            capture_output=True,
            text=True,
        )
        elapsed = time.monotonic() - start

        if result.returncode != 0:
            raise WipeExecutionError(
                f"blkdiscard failed on {device.path}: {result.stderr.strip()}"
            )

        return WipeResult(
            success=True,
            method=WipeMethod.BLKDISCARD,
            device_path=device.path,
            duration_seconds=elapsed,
            bytes_wiped=0,
            passes_completed=1,
        )


# ──────────────────────────────────────────────────────────────
# WipeVerifier (Single Responsibility Principle)
# ──────────────────────────────────────────────────────────────


class WipeVerifier:
    """
    Verifies that a wipe operation completed successfully.

    Single Responsibility: handles all verification logic independent
    of wipe strategy or execution.
    """

    def __init__(self) -> None:
        """Initialize verifier with config values."""
        self.sample_size = config.get_verify_sample_size()
        self.sample_count = config.get_verify_sample_count()

    def verify(
        self,
        device: BlockDevice,
        method: WipeMethod,
        dry_run: bool = False,
    ) -> bool:
        """
        Spot-check random sectors to confirm the wipe.

        For zero/quick/secure final-pass wipes, checks for zero bytes.
        For random wipes, checks entropy (non-zero variance).

        Args:
            device: Device that was wiped.
            method: Wipe method used.
            dry_run: If True, skip verification.

        Returns:
            True if verification passes, False otherwise.

        Raises:
            WipeVerificationError: If verification cannot proceed.
        """
        if dry_run:
            return True

        if method in (WipeMethod.BLKDISCARD,):
            return True

        check_for_zeros = method in (
            WipeMethod.ZERO, WipeMethod.QUICK, WipeMethod.SECURE
        )

        size = device.size_bytes
        if size < self.sample_size * self.sample_count:
            return True

        try:
            with open(device.path, "rb", buffering=0) as f:
                for _ in range(self.sample_count):
                    offset = random.randint(0, size - self.sample_size)
                    offset = (offset // 512) * 512
                    f.seek(offset)
                    data = f.read(self.sample_size)
                    if not data:
                        continue
                    if check_for_zeros:
                        if any(b != 0 for b in data):
                            return False
                    else:
                        if all(b == 0 for b in data):
                            return False
        except OSError as e:
            raise WipeVerificationError(
                f"Failed to verify wipe on {device.path}: {e}"
            ) from e

        return True


# ──────────────────────────────────────────────────────────────
# Strategy factory
# ──────────────────────────────────────────────────────────────


def _get_strategy(method: WipeMethod) -> WipeStrategy:
    """
    Factory function to get the appropriate wipe strategy.

    Args:
        method: The wipe method requested.

    Returns:
        An instance of the corresponding WipeStrategy.

    Raises:
        WipeError: If method is unknown.
    """
    strategies: dict[WipeMethod, WipeStrategy] = {
        WipeMethod.QUICK:      QuickWipeStrategy(),
        WipeMethod.ZERO:       ZeroWipeStrategy(),
        WipeMethod.RANDOM:     RandomWipeStrategy(),
        WipeMethod.SECURE:     SecureWipeStrategy(),
        WipeMethod.BLKDISCARD: BlkdiscardStrategy(),
    }

    if method not in strategies:
        raise WipeError(f"Unknown wipe method: {method}")

    return strategies[method]


# ──────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────


def wipe_device(
    device: BlockDevice,
    method: WipeMethod,
    progress_cb: Optional[ProgressCallback] = None,
    dry_run: bool = False,
) -> WipeResult:
    """
    Main entry point for wiping a device.

    Delegates to the appropriate WipeStrategy for execution.

    Args:
        device: BlockDevice to wipe.
        method: Wipe method to use.
        progress_cb: Optional callback for progress updates.
        dry_run: If True, simulate without modifying device.

    Returns:
        WipeResult with success/failure details.
    """
    try:
        strategy = _get_strategy(method)
        return strategy.execute(
            device=device,
            progress_cb=progress_cb,
            dry_run=dry_run,
        )
    except (WipeExecutionError, MissingDependencyError) as e:
        return WipeResult(
            success=False,
            method=method,
            device_path=device.path,
            duration_seconds=0,
            bytes_wiped=0,
            passes_completed=0,
            error_message=str(e),
        )


def verify_wipe(
    device: BlockDevice,
    method: WipeMethod,
    dry_run: bool = False,
) -> bool:
    """
    Verify that a wipe operation completed successfully.

    Args:
        device: Device that was wiped.
        method: Wipe method used.
        dry_run: If True, skip verification.

    Returns:
        True if verification passes, False otherwise.

    Raises:
        WipeVerificationError: If verification fails.
    """
    verifier = WipeVerifier()
    return verifier.verify(device=device, method=method, dry_run=dry_run)


# ──────────────────────────────────────────────────────────────
# Helper functions for UI formatting
# ──────────────────────────────────────────────────────────────


def format_bytes(n: int) -> str:
    """Format bytes to human-readable size (B, KB, MB, GB, TB, PB)."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def format_speed(bps: float) -> str:
    """Format bytes per second as human-readable speed."""
    return format_bytes(int(bps)) + "/s"


def format_eta(seconds: Optional[float]) -> str:
    """Format seconds as human-readable time (s, m, h)."""
    if seconds is None:
        return "—"
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m"
