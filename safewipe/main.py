"""
main.py — safewipe CLI entrypoint.

Commands:
  safewipe list                          — list block devices
  safewipe wipe [DEVICE]                 — wipe a device
  safewipe format DEVICE                 — partition + format
  safewipe auto                          — guided full workflow
  safewipe logs                          — view recent operation logs
  safewipe verify DEVICE                 — spot-check wipe quality
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table
from rich import box

# ── Local imports ─────────────────────────────────────────────
from safewipe import device as dev_mod
from safewipe import wipe as wipe_mod
from safewipe import format as fmt_mod
from safewipe import ui
from safewipe import logger as log_mod

app = typer.Typer(
    name="safewipe",
    help="[bold red]safewipe[/] — Safely wipe, format, and prepare storage devices.",
    rich_markup_mode="rich",
    add_completion=True,
    no_args_is_help=True,
)

console = Console()


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _abort(msg: str, code: int = 1) -> None:
    ui.print_error(msg)
    raise typer.Exit(code)


def _require_root() -> None:
    import os
    if os.geteuid() != 0:
        ui.print_error(
            "safewipe must be run as root (use sudo).\n"
            "  Example: [bold]sudo safewipe wipe[/]"
        )
        raise typer.Exit(1)


def _get_device(path: Optional[str], force: bool) -> dev_mod.BlockDevice:
    """Resolve device path → BlockDevice, handling interactive selection."""
    devices = dev_mod.list_devices(include_loop=force)

    if not force:
        # Only show removable / non-system unless --force
        selectable = [d for d in devices if (d.removable or d.hotplug) and not d.is_system]
    else:
        selectable = devices

    if path:
        # Find by path in all devices (including system for --force)
        found = dev_mod.get_device_by_path(path)
        if found is None:
            _abort(f"Device not found: {path}")
        if found.is_system and not force:
            _abort(
                f"{path} is a system disk. Use --force to override (DANGEROUS)."
            )
        return found
    else:
        # Interactive selection
        if not selectable:
            if not force:
                ui.print_error(
                    "No removable devices found.\n"
                    "  Connect a USB drive, or use [bold]--force[/] to show all devices."
                )
            else:
                ui.print_error("No block devices found.")
            raise typer.Exit(1)

        chosen = ui.select_device(selectable, force=force)
        if chosen is None:
            console.print("[dim]Aborted.[/]")
            raise typer.Exit(0)
        return chosen


def _handle_mounted(device: dev_mod.BlockDevice, dry_run: bool) -> None:
    """Prompt to unmount if mounted, abort if user refuses."""
    if device.is_mounted:
        if not ui.confirm_unmount(device):
            _abort("Device is mounted. Aborting.")
        try:
            unmounted = dev_mod.unmount_device(device, dry_run=dry_run)
            for mp in unmounted:
                ui.print_success(f"Unmounted {mp}")
        except RuntimeError as e:
            _abort(str(e))


# ──────────────────────────────────────────────────────────────
# safewipe list
# ──────────────────────────────────────────────────────────────

@app.command("list")
def cmd_list(
    all_devices: bool = typer.Option(
        False, "--all", "-a",
        help="Show all devices including system disks.",
    ),
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Same as --all.",
    ),
):
    """
    [cyan]List[/] all detected block devices.

    By default only removable/external devices are shown.
    Use [bold]--all[/] or [bold]--force[/] to also show system disks.
    """
    ui.print_banner()
    devices = dev_mod.list_devices(include_loop=all_devices or force)

    if not (all_devices or force):
        devices = [d for d in devices if d.removable or d.hotplug or d.is_system]

    if not devices:
        ui.print_warning("No block devices detected.")
        return

    ui.print_device_table(devices, show_index=False)
    console.print(
        f"[dim]  {len(devices)} device(s) found.  "
        "Use [bold]safewipe wipe[/] to start wiping.[/]\n"
    )


# ──────────────────────────────────────────────────────────────
# safewipe wipe
# ──────────────────────────────────────────────────────────────

@app.command("wipe")
def cmd_wipe(
    device_path: Optional[str] = typer.Argument(
        None, help="Device path (e.g. /dev/sdb). Omit for interactive selection."
    ),
    method: Optional[wipe_mod.WipeMethod] = typer.Option(
        None, "--method", "-m",
        help="Wipe method: quick|zero|random|secure|blkdiscard",
    ),
    verify: bool = typer.Option(
        False, "--verify", "-V",
        help="Verify wipe by sampling random sectors after completion.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="Simulate the wipe without writing anything.",
    ),
    force: bool = typer.Option(
        False, "--force",
        help="Allow wiping non-removable or system disks.",
    ),
    no_confirm: bool = typer.Option(
        False, "--no-confirm",
        help="Skip confirmation prompts (DANGEROUS — for scripting only).",
    ),
    no_format: bool = typer.Option(
        False, "--no-format",
        help="Skip the format wizard after wiping.",
    ),
):
    """
    [bold red]Wipe[/] a storage device securely.

    Multiple safety checks are performed before any data is destroyed.
    You will be asked to confirm by typing the device path and a
    confirmation phrase.

    Examples:

      sudo safewipe wipe
      sudo safewipe wipe /dev/sdb --method zero
      sudo safewipe wipe /dev/sdb --method secure --verify
      sudo safewipe wipe /dev/sdb --dry-run
    """
    _require_root()
    ui.print_banner()
    ui.print_section("Device Selection")

    chosen = _get_device(device_path, force)

    # Safety validation
    warnings = dev_mod.validate_wipe_target(chosen, force=force)
    critical = [w for w in warnings if w.startswith("CRITICAL")]
    non_critical = [w for w in warnings if not w.startswith("CRITICAL")]

    for w in non_critical:
        ui.print_warning(w.replace("WARNING: ", ""))

    if critical:
        for c in critical:
            ui.print_error(c.replace("CRITICAL: ", ""), title="Critical Safety Check")
        raise typer.Exit(1)

    # Handle mounted
    _handle_mounted(chosen, dry_run)

    # Method selection
    ui.print_section("Wipe Method")
    chosen_method = method or ui.select_wipe_method()

    # Confirmation
    if not no_confirm:
        if not ui.confirm_wipe(chosen, dry_run=dry_run):
            console.print("[dim]Wipe aborted.[/]")
            raise typer.Exit(0)

    # ── Execute wipe ────────────────────────────────────────────
    ui.print_section("Wiping")

    display = ui.WipeProgressDisplay(
        total_bytes=chosen.size_bytes or (1024 * 1024 * 100),
        method=chosen_method,
    )

    result: wipe_mod.WipeResult
    with display:
        result = wipe_mod.wipe_device(
            device=chosen,
            method=chosen_method,
            progress_cb=display.update,
            dry_run=dry_run,
        )

    # Verification
    if verify and result.success:
        ui.print_info("Verifying wipe…")
        passed = wipe_mod.verify_wipe(chosen, chosen_method, dry_run)
        result.verified = True
        result.verification_passed = passed

    # Logging
    log_path = log_mod.log_operation(
        operation="wipe",
        device_path=chosen.path,
        result="dry_run" if dry_run else ("success" if result.success else "failure"),
        details={
            "method": chosen_method.value,
            "bytes_wiped": result.bytes_wiped,
            "passes": result.passes_completed,
            "duration_s": round(result.duration_seconds, 2),
            "model": chosen.display_name,
            "size": chosen.size,
            "verified": result.verification_passed,
        },
        error=result.error_message or None,
    )
    result.log_path = log_path

    ui.print_section("Result")
    ui.print_wipe_result(result)

    if not result.success:
        raise typer.Exit(1)

    # ── Optional format wizard ──────────────────────────────────
    if not no_format and result.success:
        ui.print_section("Format")
        fmt_opts = ui.format_wizard(chosen.path, dry_run=dry_run)
        if fmt_opts:
            fmt_result = fmt_mod.prepare_device(
                device_path=chosen.path,
                table_type=fmt_opts["table_type"],
                filesystem=fmt_opts["filesystem"],
                label=fmt_opts["label"],
                auto_mount=fmt_opts["auto_mount"],
                dry_run=dry_run,
                status_callback=ui.print_info,
            )
            log_mod.log_operation(
                operation="format",
                device_path=chosen.path,
                result="dry_run" if dry_run else ("success" if fmt_result.success else "failure"),
                details={
                    "filesystem": fmt_result.filesystem.value if fmt_result.filesystem else None,
                    "label": fmt_result.label,
                    "partition": fmt_result.partition_path,
                    "mount": fmt_result.mount_point,
                },
                error=fmt_result.error_message or None,
            )
            ui.print_format_result(fmt_result)


# ──────────────────────────────────────────────────────────────
# safewipe format
# ──────────────────────────────────────────────────────────────

@app.command("format")
def cmd_format(
    device_path: str = typer.Argument(
        ..., help="Device path to partition and format (e.g. /dev/sdb)."
    ),
    fs: fmt_mod.Filesystem = typer.Option(
        fmt_mod.Filesystem.FAT32, "--fs",
        help="Filesystem: fat32|exfat|ext4",
    ),
    table: fmt_mod.PartitionTable = typer.Option(
        fmt_mod.PartitionTable.GPT, "--table", "-t",
        help="Partition table: mbr|gpt",
    ),
    label: Optional[str] = typer.Option(
        None, "--label", "-l",
        help="Volume label (max 11 chars).",
    ),
    mount: bool = typer.Option(
        True, "--mount/--no-mount",
        help="Auto-mount after formatting.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="Simulate without writing.",
    ),
    force: bool = typer.Option(
        False, "--force",
        help="Skip safety checks.",
    ),
):
    """
    [bold cyan]Partition and format[/] a device (no wipe).

    Creates a fresh partition table, a single partition, and formats it.

    Examples:

      sudo safewipe format /dev/sdb --fs fat32 --label MYUSB
      sudo safewipe format /dev/sdb --fs ext4 --table gpt
      sudo safewipe format /dev/sdb1 --fs exfat --no-mount
    """
    _require_root()
    ui.print_banner()

    # Check deps
    missing = fmt_mod.check_format_deps(fs)
    if missing:
        _abort(
            f"Missing tools for {fs.value}: {', '.join(missing)}\n"
            f"  Install with: [bold]apt install {' '.join(missing)}[/]"
        )

    device = dev_mod.get_device_by_path(device_path)
    if device is None:
        _abort(f"Device not found: {device_path}")

    ui.print_section("Format")
    console.print(
        f"  Device    : [bold]{device_path}[/]\n"
        f"  Table     : {table.value.upper()}\n"
        f"  Filesystem: {fs.value.upper()}\n"
        f"  Label     : {label or 'SAFEWIPE'}\n"
        f"  Mount     : {'yes' if mount else 'no'}\n"
    )

    if not Confirm.ask("Proceed?", default=True):
        console.print("[dim]Aborted.[/]")
        raise typer.Exit(0)

    result = fmt_mod.prepare_device(
        device_path=device_path,
        table_type=table,
        filesystem=fs,
        label=label,
        auto_mount=mount,
        dry_run=dry_run,
        status_callback=ui.print_info,
    )

    log_mod.log_operation(
        operation="format",
        device_path=device_path,
        result="dry_run" if dry_run else ("success" if result.success else "failure"),
        details={
            "filesystem": result.filesystem.value if result.filesystem else None,
            "label": result.label,
            "mount": result.mount_point,
        },
        error=result.error_message or None,
    )

    ui.print_format_result(result)
    if not result.success:
        raise typer.Exit(1)


# ──────────────────────────────────────────────────────────────
# safewipe auto
# ──────────────────────────────────────────────────────────────

@app.command("auto")
def cmd_auto(
    ctx: typer.Context,
    dry_run: bool = typer.Option(False, "--dry-run"),
    force:   bool = typer.Option(False, "--force"),
):
    """
    [bold green]Guided full workflow[/] — select → wipe → format → mount.

    The complete end-to-end experience for preparing a storage device.
    Perfect for beginners or one-time use.
    """
    _require_root()
    ui.print_banner()
    console.print(
        "[bold cyan]Welcome to safewipe Auto Mode![/]\n"
        "This wizard will guide you through wiping and formatting a device.\n"
    )
    # Delegate to wipe (which includes format wizard)
    ctx.invoke(cmd_wipe, device_path=None, method=None, verify=True,
               dry_run=dry_run, force=force, no_confirm=False, no_format=False)


# ──────────────────────────────────────────────────────────────
# safewipe verify
# ──────────────────────────────────────────────────────────────

@app.command("verify")
def cmd_verify(
    device_path: str = typer.Argument(..., help="Device path to verify (e.g. /dev/sdb)."),
    method: wipe_mod.WipeMethod = typer.Option(
        wipe_mod.WipeMethod.ZERO, "--method", "-m",
        help="Wipe method that was used (to know what to check for).",
    ),
):
    """
    [bold yellow]Verify[/] a wipe by sampling random sectors.

    Checks that the device was correctly wiped according to the given method.
    For zero/secure wipes, confirms sectors contain only zeros.
    For random wipes, confirms non-zero random data.
    """
    _require_root()
    ui.print_banner()

    device = dev_mod.get_device_by_path(device_path)
    if device is None:
        _abort(f"Device not found: {device_path}")

    ui.print_info(f"Verifying {device_path} (method: {method.value})…")
    passed = wipe_mod.verify_wipe(device, method)

    if passed:
        ui.print_success(f"Verification PASSED — {device_path} appears correctly wiped.")
    else:
        ui.print_error(
            f"Verification FAILED — {device_path} may not be fully wiped.",
            title="Verification Failed",
        )
        raise typer.Exit(1)


# ──────────────────────────────────────────────────────────────
# safewipe logs
# ──────────────────────────────────────────────────────────────

@app.command("logs")
def cmd_logs(
    n: int = typer.Option(20, "--last", "-n", help="Number of recent entries to show."),
):
    """
    [bold]View recent operation logs.[/]

    Logs are stored in [bold]~/.safewipe/logs/[/] as JSON-lines files.
    """
    entries = log_mod.read_recent_logs(n)

    if not entries:
        console.print("[dim]No log entries found.[/]")
        return

    table = Table(
        title=f"[bold]Last {len(entries)} Operations[/]",
        box=box.ROUNDED,
        border_style="blue",
        header_style="bold cyan",
        show_lines=True,
    )
    table.add_column("Time",      min_width=20)
    table.add_column("Operation", min_width=8)
    table.add_column("Device",    min_width=10)
    table.add_column("Method",    min_width=10)
    table.add_column("Result",    min_width=9)
    table.add_column("Duration",  min_width=8, justify="right")

    result_styles = {
        "success":  "green",
        "failure":  "red",
        "dry_run":  "yellow",
        "aborted":  "dim",
    }

    for e in entries:
        result_str = e.get("result", "?")
        style = result_styles.get(result_str, "white")
        table.add_row(
            e.get("timestamp", "")[:19],
            e.get("operation", "?"),
            e.get("device", "?"),
            e.get("method", "—"),
            f"[{style}]{result_str}[/]",
            f"{e.get('duration_s', 0):.1f}s" if e.get("duration_s") else "—",
        )

    console.print(table)
    from safewipe.logger import LOG_DIR
    console.print(f"\n[dim]Log directory: {LOG_DIR}[/]")


# ──────────────────────────────────────────────────────────────
# Entrypoint
# ──────────────────────────────────────────────────────────────

def main():
    app()


if __name__ == "__main__":
    main()
