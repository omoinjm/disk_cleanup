"""
tests/test_safewipe.py — Test suite for safewipe using loopback devices.

Tests run WITHOUT touching any real disk.  All wipe and format operations
are performed on a temporary loopback device backed by a file.

Prerequisites (run as root):
    pip install pytest
    apt install util-linux dosfstools

Usage:
    sudo pytest tests/test_safewipe.py -v
"""

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

# ── Skip entire module if not root ────────────────────────────
if os.geteuid() != 0:
    pytest.skip("safewipe tests require root (sudo pytest …)", allow_module_level=True)


# ──────────────────────────────────────────────────────────────
# Fixtures — loopback device lifecycle
# ──────────────────────────────────────────────────────────────

LOOP_SIZE_MB = 64  # 64 MiB — small enough for fast tests


@pytest.fixture(scope="module")
def loop_device():
    """
    Create a temporary file, attach it as a loopback device, yield the
    path (e.g. /dev/loop8), and clean up afterwards.
    """
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".img")
    tmp.seek(LOOP_SIZE_MB * 1024 * 1024 - 1)
    tmp.write(b"\x00")
    tmp.flush()
    tmp.close()

    result = subprocess.run(
        ["losetup", "--find", "--show", tmp.name],
        capture_output=True, text=True, check=True,
    )
    loop_path = result.stdout.strip()

    yield loop_path

    # Teardown
    subprocess.run(["losetup", "-d", loop_path], check=False)
    Path(tmp.name).unlink(missing_ok=True)


# ──────────────────────────────────────────────────────────────
# device.py tests
# ──────────────────────────────────────────────────────────────

class TestDeviceDiscovery:
    def test_list_devices_returns_list(self):
        from safewipe.device import list_devices
        devices = list_devices(include_loop=True)
        assert isinstance(devices, list)

    def test_loop_device_appears(self, loop_device):
        from safewipe.device import list_devices
        devices = list_devices(include_loop=True)
        paths = [d.path for d in devices]
        assert loop_device in paths, f"{loop_device} not in {paths}"

    def test_loop_device_not_system(self, loop_device):
        from safewipe.device import get_device_by_path
        dev = get_device_by_path(loop_device)
        assert dev is not None
        assert not dev.is_system

    def test_get_device_by_path_unknown(self):
        from safewipe.device import get_device_by_path
        assert get_device_by_path("/dev/nonexistent_xyz") is None

    def test_validate_wipe_target_clean(self, loop_device):
        from safewipe.device import get_device_by_path, validate_wipe_target
        dev = get_device_by_path(loop_device)
        assert dev is not None
        warnings = validate_wipe_target(dev, force=False)
        # Should have no CRITICAL warnings for a clean loop device
        critical = [w for w in warnings if w.startswith("CRITICAL")]
        assert not critical, f"Unexpected critical warnings: {critical}"


# ──────────────────────────────────────────────────────────────
# wipe.py tests
# ──────────────────────────────────────────────────────────────

class TestWipeMethods:
    """All wipe tests use dry_run=True to avoid actual I/O in normal test runs,
    and a separate set uses the loopback device for real writes."""

    def test_dry_run_quick(self, loop_device):
        from safewipe.device import get_device_by_path
        from safewipe.wipe import wipe_device, WipeMethod
        dev = get_device_by_path(loop_device)
        result = wipe_device(dev, WipeMethod.QUICK, dry_run=True)
        assert result.success
        assert result.passes_completed == 1

    def test_dry_run_zero(self, loop_device):
        from safewipe.device import get_device_by_path
        from safewipe.wipe import wipe_device, WipeMethod
        dev = get_device_by_path(loop_device)
        result = wipe_device(dev, WipeMethod.ZERO, dry_run=True)
        assert result.success

    def test_dry_run_random(self, loop_device):
        from safewipe.device import get_device_by_path
        from safewipe.wipe import wipe_device, WipeMethod
        dev = get_device_by_path(loop_device)
        result = wipe_device(dev, WipeMethod.RANDOM, dry_run=True)
        assert result.success

    def test_dry_run_secure(self, loop_device):
        from safewipe.device import get_device_by_path
        from safewipe.wipe import wipe_device, WipeMethod
        dev = get_device_by_path(loop_device)
        result = wipe_device(dev, WipeMethod.SECURE, dry_run=True)
        assert result.success
        assert result.passes_completed == 3

    def test_real_zero_wipe_and_verify(self, loop_device):
        """Perform a real zero wipe on the loopback device and verify."""
        from safewipe.device import get_device_by_path
        from safewipe.wipe import wipe_device, verify_wipe, WipeMethod
        dev = get_device_by_path(loop_device)
        assert dev is not None

        result = wipe_device(dev, WipeMethod.ZERO, dry_run=False)
        assert result.success, f"Wipe failed: {result.error_message}"
        assert result.bytes_wiped > 0

        passed = verify_wipe(dev, WipeMethod.ZERO, dry_run=False)
        assert passed, "Verification failed after zero wipe"

    def test_progress_callback_called(self, loop_device):
        """Ensure progress callback fires during a dry-run zero wipe."""
        from safewipe.device import get_device_by_path
        from safewipe.wipe import wipe_device, WipeMethod, WipeProgress
        dev = get_device_by_path(loop_device)

        calls: list[WipeProgress] = []
        wipe_device(dev, WipeMethod.ZERO, progress_cb=calls.append, dry_run=True)
        assert len(calls) > 0
        assert all(isinstance(c, WipeProgress) for c in calls)
        # Percentage should be monotonically increasing
        percents = [c.percent for c in calls]
        assert percents == sorted(percents), "Percentages not monotonically increasing"


# ──────────────────────────────────────────────────────────────
# format.py tests
# ──────────────────────────────────────────────────────────────

class TestFormat:
    def test_dry_run_prepare_device_fat32(self, loop_device):
        from safewipe.format import prepare_device, PartitionTable, Filesystem
        result = prepare_device(
            device_path=loop_device,
            table_type=PartitionTable.MBR,
            filesystem=Filesystem.FAT32,
            label="TEST",
            auto_mount=False,
            dry_run=True,
        )
        assert result.success
        assert result.partition_path == loop_device + "1"

    def test_dry_run_prepare_device_ext4(self, loop_device):
        from safewipe.format import prepare_device, PartitionTable, Filesystem
        result = prepare_device(
            device_path=loop_device,
            table_type=PartitionTable.GPT,
            filesystem=Filesystem.EXT4,
            label="TESTEXT4",
            auto_mount=False,
            dry_run=True,
        )
        assert result.success

    @pytest.mark.skipif(
        not shutil.which("mkfs.fat"),
        reason="dosfstools not installed",
    )
    def test_real_format_fat32(self, loop_device):
        """Real format test: zero the device first, then partition + FAT32."""
        from safewipe.device import get_device_by_path
        from safewipe.wipe import wipe_device, WipeMethod
        from safewipe.format import prepare_device, PartitionTable, Filesystem

        dev = get_device_by_path(loop_device)
        wipe_result = wipe_device(dev, WipeMethod.QUICK, dry_run=False)
        assert wipe_result.success

        fmt_result = prepare_device(
            device_path=loop_device,
            table_type=PartitionTable.MBR,
            filesystem=Filesystem.FAT32,
            label="TESTDRIVE",
            auto_mount=False,
            dry_run=False,
        )
        assert fmt_result.success, f"Format failed: {fmt_result.error_message}"
        assert fmt_result.partition_path is not None


# ──────────────────────────────────────────────────────────────
# logger.py tests
# ──────────────────────────────────────────────────────────────

class TestLogger:
    def test_log_and_read(self, tmp_path, monkeypatch):
        import safewipe.logger as log_mod
        monkeypatch.setattr(log_mod, "LOG_DIR", tmp_path / "logs")

        log_mod.log_operation(
            operation="wipe",
            device_path="/dev/test",
            result="success",
            details={"method": "zero", "bytes_wiped": 1000},
        )

        entries = log_mod.read_recent_logs(10)
        assert len(entries) >= 1
        last = entries[0]
        assert last["operation"] == "wipe"
        assert last["device"] == "/dev/test"
        assert last["result"] == "success"
        assert last["method"] == "zero"

    def test_log_error(self, tmp_path, monkeypatch):
        import safewipe.logger as log_mod
        monkeypatch.setattr(log_mod, "LOG_DIR", tmp_path / "logs2")

        log_mod.log_operation(
            operation="wipe",
            device_path="/dev/sdz",
            result="failure",
            error="Permission denied",
        )
        entries = log_mod.read_recent_logs(5)
        assert entries[0]["result"] == "failure"
        assert "Permission denied" in entries[0].get("error", "")


# ──────────────────────────────────────────────────────────────
# wipe helpers tests
# ──────────────────────────────────────────────────────────────

class TestHelpers:
    def test_format_bytes(self):
        from safewipe.wipe import format_bytes
        assert format_bytes(0) == "0.0 B"
        assert "KB" in format_bytes(1500)
        assert "MB" in format_bytes(5 * 1024 * 1024)
        assert "GB" in format_bytes(2 * 1024 ** 3)

    def test_format_eta(self):
        from safewipe.wipe import format_eta
        assert format_eta(None) == "—"
        assert "s" in format_eta(30)
        assert "m" in format_eta(125)

    def test_wipe_progress_percent(self):
        from safewipe.wipe import WipeProgress, WipeMethod
        p = WipeProgress(
            method=WipeMethod.ZERO,
            pass_number=1,
            total_passes=1,
            bytes_written=512 * 1024 * 1024,  # 512 MiB
            total_bytes=1024 * 1024 * 1024,   # 1 GiB
            elapsed_seconds=10.0,
        )
        assert abs(p.percent - 50.0) < 0.01
        assert p.speed_bytes_per_sec > 0
        assert p.eta_seconds is not None
