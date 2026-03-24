"""
ui.py — Rich-based terminal UI components for safewipe.

Provides:
  - Device listing table
  - Interactive device selector
  - Multi-step confirmation prompts
  - Live wipe progress bar
  - Status / success / error panels
  - Method selection menu
  - Post-wipe format wizard
"""

import sys
import time
from typing import Optional

from rich import box
from rich.align import Align
from rich.columns import Columns
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.prompt import Confirm, Prompt
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich import print as rprint

from safewipe.device import BlockDevice
from safewipe.wipe import (
    METHOD_DESCRIPTIONS,
    METHOD_PASS_COUNT,
    WipeMethod,
    WipeProgress,
    WipeResult,
    format_bytes,
    format_eta,
    format_speed,
)
from safewipe.format import (
    FS_DESCRIPTIONS,
    PT_DESCRIPTIONS,
    Filesystem,
    FormatResult,
    PartitionTable,
)

console = Console()
err_console = Console(stderr=True)


# ──────────────────────────────────────────────────────────────
# Brand / header
# ──────────────────────────────────────────────────────────────

BANNER = """
 ███████╗ █████╗ ███████╗███████╗██╗    ██╗██╗██████╗ ███████╗
 ██╔════╝██╔══██╗██╔════╝██╔════╝██║    ██║██║██╔══██╗██╔════╝
 ███████╗███████║█████╗  █████╗  ██║ █╗ ██║██║██████╔╝█████╗  
 ╚════██║██╔══██║██╔══╝  ██╔══╝  ██║███╗██║██║██╔═══╝ ██╔══╝  
 ███████║██║  ██║██║     ███████╗╚███╔███╔╝██║██║     ███████╗
 ╚══════╝╚═╝  ╚═╝╚═╝     ╚══════╝ ╚══╝╚══╝ ╚═╝╚═╝     ╚══════╝
"""


def print_banner():
    console.print(Text(BANNER, style="bold red"), justify="center")
    console.print(
        Align.center(
            Text(
                "Production-grade storage wipe & format tool  •  v1.0.0",
                style="dim",
            )
        )
    )
    console.print()


# ──────────────────────────────────────────────────────────────
# Device table
# ──────────────────────────────────────────────────────────────

def _size_color(size_bytes: int) -> str:
    gb = size_bytes / (1024 ** 3)
    if gb < 1:
        return "cyan"
    elif gb < 32:
        return "green"
    elif gb < 500:
        return "yellow"
    return "red"


def print_device_table(devices: list[BlockDevice], show_index: bool = True) -> None:
    """Render a Rich table of detected devices."""
    if not devices:
        console.print(
            Panel(
                "[yellow]No removable/external devices detected.[/]\n"
                "Connect a USB drive or use [bold]--force[/] to show all devices.",
                title="📭  No Devices Found",
                border_style="yellow",
            )
        )
        return

    table = Table(
        title="[bold]Detected Block Devices[/]",
        box=box.ROUNDED,
        border_style="blue",
        header_style="bold cyan",
        show_lines=True,
        expand=False,
    )

    if show_index:
        table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Device",     style="bold white",  min_width=12)
    table.add_column("Model / Vendor", min_width=22)
    table.add_column("Size",       justify="right",     min_width=8)
    table.add_column("Type",       min_width=8)
    table.add_column("Mount",      min_width=14)
    table.add_column("Status",     min_width=10)

    for i, dev in enumerate(devices, 1):
        # Status badge
        if dev.is_system:
            status = Text("⛔  SYSTEM", style="bold red")
        elif dev.ro:
            status = Text("🔒  READ-ONLY", style="yellow")
        elif dev.is_mounted:
            status = Text("📌  MOUNTED", style="yellow")
        else:
            status = Text("✅  READY", style="green")

        # Mount point display
        mps = dev.all_mount_points
        if mps:
            mount_str = Text(", ".join(mps[:2]), style="yellow")
            if len(mps) > 2:
                mount_str.append(f" +{len(mps) - 2}", style="dim")
        else:
            mount_str = Text("—", style="dim")

        # Transport / type
        transport = Text(
            f"{dev.transport_icon} {dev.tran.upper() or '?'}",
            style="cyan",
        )

        # Model name
        model_text = Text(dev.display_name[:30], style="white")
        if dev.is_system:
            model_text.stylize("bold red")

        size_text = Text(dev.size, style=_size_color(dev.size_bytes))

        row: list = []
        if show_index:
            row.append(str(i))
        row.extend([
            Text(dev.path, style="bold white" if not dev.is_system else "bold red"),
            model_text,
            size_text,
            transport,
            mount_str,
            status,
        ])
        table.add_row(*row)

    console.print(table)
    console.print()


# ──────────────────────────────────────────────────────────────
# Device selector
# ──────────────────────────────────────────────────────────────

def select_device(
    devices: list[BlockDevice],
    force: bool = False,
) -> Optional[BlockDevice]:
    """
    Interactive numbered device picker.
    Returns selected device or None if user quits.
    """
    wipeable = [d for d in devices if not d.is_system or force]
    if not wipeable:
        console.print("[red]No wipeable devices available.[/]")
        return None

    print_device_table(wipeable, show_index=True)

    while True:
        choice = Prompt.ask(
            "[cyan]Select device number[/] ([dim]q to quit[/])",
            default="q",
        )
        if choice.lower() in ("q", "quit", "exit"):
            return None
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(wipeable):
                return wipeable[idx]
            console.print(f"[red]Invalid selection. Enter 1–{len(wipeable)}.[/]")
        except ValueError:
            console.print("[red]Please enter a number.[/]")


# ──────────────────────────────────────────────────────────────
# Safety confirmation
# ──────────────────────────────────────────────────────────────

def confirm_wipe(device: BlockDevice, dry_run: bool = False) -> bool:
    """
    Multi-step confirmation before wiping.
    Returns True if user confirmed, False if aborted.
    """
    console.print()
    console.print(
        Panel(
            f"[bold red]⚠️   YOU ARE ABOUT TO PERMANENTLY DESTROY ALL DATA   ⚠️[/]\n\n"
            f"  Device : [bold]{device.path}[/]\n"
            f"  Model  : {device.display_name}\n"
            f"  Size   : [bold yellow]{device.size}[/]\n"
            + (f"  [blink red]DRY RUN — no data will be written[/]" if dry_run else ""),
            title="[bold red]⚠  DANGER ZONE[/]",
            border_style="red",
        )
    )
    console.print()

    # Step 1: Type device path
    console.print(
        f"[yellow]Step 1/2[/] — Type the device path to confirm: "
        f"[bold]{device.path}[/]"
    )
    step1 = Prompt.ask("  Device path")
    if step1.strip() != device.path:
        console.print("[red]✗  Device path mismatch. Wipe aborted.[/]")
        return False

    # Step 2: Type confirmation phrase
    phrase = f"WIPE {device.path}"
    console.print()
    console.print(
        f"[yellow]Step 2/2[/] — Type exactly: [bold red]{phrase}[/]"
    )
    step2 = Prompt.ask("  Confirmation")
    if step2.strip() != phrase:
        console.print("[red]✗  Confirmation phrase mismatch. Wipe aborted.[/]")
        return False

    console.print()
    if dry_run:
        console.print("[green bold]✓  Dry-run confirmed. Simulating wipe.[/]")
    else:
        console.print("[green bold]✓  Confirmed. Proceeding with wipe…[/]")
    console.print()
    return True


# ──────────────────────────────────────────────────────────────
# Method selection
# ──────────────────────────────────────────────────────────────

def select_wipe_method() -> WipeMethod:
    """Present an interactive menu to pick a wipe method."""
    methods = list(WipeMethod)
    table = Table(
        title="[bold]Wipe Method[/]",
        box=box.SIMPLE_HEAVY,
        border_style="blue",
        header_style="bold cyan",
        show_lines=False,
    )
    table.add_column("#",       width=3, justify="right", style="dim")
    table.add_column("Method",  min_width=14, style="bold white")
    table.add_column("Passes",  width=7,  justify="center")
    table.add_column("Description")

    styles = {
        WipeMethod.QUICK:      "cyan",
        WipeMethod.ZERO:       "green",
        WipeMethod.RANDOM:     "yellow",
        WipeMethod.SECURE:     "red",
        WipeMethod.BLKDISCARD: "magenta",
    }

    for i, m in enumerate(methods, 1):
        table.add_row(
            str(i),
            Text(m.value.capitalize(), style=styles.get(m, "white")),
            str(METHOD_PASS_COUNT[m]),
            METHOD_DESCRIPTIONS[m],
        )

    console.print(table)

    while True:
        choice = Prompt.ask(
            "[cyan]Select method[/]",
            default="1",
        )
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(methods):
                return methods[idx]
        except ValueError:
            pass
        console.print(f"[red]Enter 1–{len(methods)}[/]")


# ──────────────────────────────────────────────────────────────
# Wipe progress
# ──────────────────────────────────────────────────────────────

class WipeProgressDisplay:
    """
    Live Rich progress display driven by WipeProgress callbacks.
    Usage:
        display = WipeProgressDisplay(total_bytes=device.size_bytes)
        with display:
            wipe_device(..., progress_cb=display.update)
    """

    def __init__(self, total_bytes: int, method: WipeMethod):
        self.total_bytes = total_bytes
        self.method = method
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(bar_width=40, complete_style="green", finished_style="bold green"),
            TextColumn("[progress.percentage]{task.percentage:>5.1f}%"),
            TransferSpeedColumn(),
            TimeElapsedColumn(),
            TextColumn("ETA"),
            TimeRemainingColumn(),
            console=console,
            transient=False,
            expand=True,
        )
        self._task: Optional[TaskID] = None
        self._live: Optional[Live] = None

    def __enter__(self):
        self._progress.__enter__()
        total_passes = METHOD_PASS_COUNT[self.method]
        self._task = self._progress.add_task(
            f"[cyan]{self.method.value.capitalize()} wipe",
            total=self.total_bytes * total_passes,
        )
        return self

    def __exit__(self, *args):
        self._progress.__exit__(*args)

    def update(self, prog: WipeProgress) -> None:
        """Called by wipe engine on each chunk."""
        if self._task is None:
            return
        overall = (prog.pass_number - 1) * prog.total_bytes + prog.bytes_written
        self._progress.update(
            self._task,
            completed=overall,
            description=(
                f"[cyan]{prog.pass_label or self.method.value.capitalize()}"
            ),
        )


# ──────────────────────────────────────────────────────────────
# Format wizard
# ──────────────────────────────────────────────────────────────

def format_wizard(device_path: str, dry_run: bool = False) -> Optional[dict]:
    """
    Interactive wizard to configure partition table + filesystem + label + mount.
    Returns a dict of choices, or None if user skips.
    """
    console.print()
    if not Confirm.ask(
        "[cyan]Partition and format the device after wiping?[/]",
        default=True,
    ):
        return None

    # Partition table
    console.print()
    pts = list(PartitionTable)
    _print_choice_table(
        "Partition Table",
        [(pt.value.upper(), PT_DESCRIPTIONS[pt]) for pt in pts],
    )
    pt_choice = _pick(len(pts), default=2)  # default GPT
    table_type = pts[pt_choice]

    # Filesystem
    console.print()
    fss = list(Filesystem)
    _print_choice_table(
        "Filesystem",
        [(fs.value.upper(), FS_DESCRIPTIONS[fs]) for fs in fss],
    )
    fs_choice = _pick(len(fss), default=1)  # default FAT32
    filesystem = fss[fs_choice]

    # Label
    label = None
    if filesystem != Filesystem.NONE:
        label = Prompt.ask(
            "[cyan]Volume label[/] (max 11 chars)",
            default="SAFEWIPE",
        )[:11]

    # Auto-mount
    auto_mount = False
    if filesystem != Filesystem.NONE:
        auto_mount = Confirm.ask(
            "[cyan]Auto-mount after formatting?[/]",
            default=True,
        )

    return {
        "table_type": table_type,
        "filesystem": filesystem,
        "label": label,
        "auto_mount": auto_mount,
    }


def _print_choice_table(title: str, items: list[tuple[str, str]]) -> None:
    table = Table(
        title=f"[bold]{title}[/]",
        box=box.SIMPLE_HEAVY,
        border_style="blue",
        header_style="bold cyan",
        show_lines=False,
        expand=False,
    )
    table.add_column("#",    width=3, justify="right", style="dim")
    table.add_column("Name", min_width=10, style="bold white")
    table.add_column("Description")
    for i, (name, desc) in enumerate(items, 1):
        table.add_row(str(i), name, desc)
    console.print(table)


def _pick(count: int, default: int = 1) -> int:
    while True:
        choice = Prompt.ask(
            "[cyan]Select[/]", default=str(default)
        )
        try:
            idx = int(choice) - 1
            if 0 <= idx < count:
                return idx
        except ValueError:
            pass
        console.print(f"[red]Enter 1–{count}[/]")


# ──────────────────────────────────────────────────────────────
# Result panels
# ──────────────────────────────────────────────────────────────

def print_wipe_result(result: WipeResult) -> None:
    if result.success:
        verify_line = ""
        if result.verified:
            if result.verification_passed:
                verify_line = "\n  [green]✓  Verification passed[/]"
            else:
                verify_line = "\n  [red]✗  Verification FAILED — sectors may not be wiped[/]"

        console.print(
            Panel(
                f"  [bold green]Wipe completed successfully![/]\n\n"
                f"  Method   : [bold]{result.method.value}[/]\n"
                f"  Device   : [bold]{result.device_path}[/]\n"
                f"  Passes   : {result.passes_completed}\n"
                f"  Written  : {format_bytes(result.bytes_wiped)}\n"
                f"  Duration : {result.duration_seconds:.1f}s"
                + verify_line
                + (f"\n  Log      : {result.log_path}" if result.log_path else ""),
                title="[bold green]✓  WIPE COMPLETE[/]",
                border_style="green",
            )
        )
    else:
        console.print(
            Panel(
                f"  [bold red]Wipe FAILED[/]\n\n"
                f"  Device : {result.device_path}\n"
                f"  Error  : [red]{result.error_message}[/]",
                title="[bold red]✗  WIPE FAILED[/]",
                border_style="red",
            )
        )


def print_format_result(result: FormatResult) -> None:
    if result.success:
        mount_line = (
            f"\n  Mount    : [bold green]{result.mount_point}[/]"
            if result.mount_point
            else ""
        )
        console.print(
            Panel(
                f"  [bold green]Format completed successfully![/]\n\n"
                f"  Partition: [bold]{result.partition_path}[/]\n"
                f"  Filesystem: {result.filesystem.value if result.filesystem else '—'}\n"
                f"  Label    : {result.label or '—'}"
                + mount_line
                + f"\n  Duration : {result.duration_seconds:.1f}s",
                title="[bold green]✓  FORMAT COMPLETE[/]",
                border_style="green",
            )
        )
    else:
        console.print(
            Panel(
                f"  [bold red]Format FAILED[/]\n\n"
                f"  Error: [red]{result.error_message}[/]",
                title="[bold red]✗  FORMAT FAILED[/]",
                border_style="red",
            )
        )


def print_error(message: str, title: str = "Error") -> None:
    console.print(
        Panel(
            f"[red]{message}[/]",
            title=f"[bold red]✗  {title}[/]",
            border_style="red",
        )
    )


def print_warning(message: str) -> None:
    console.print(f"[bold yellow]⚠  {message}[/]")


def print_success(message: str) -> None:
    console.print(f"[bold green]✓  {message}[/]")


def print_info(message: str) -> None:
    console.print(f"[cyan]ℹ  {message}[/]")


def print_section(title: str) -> None:
    console.print()
    console.print(Rule(f"[bold cyan]{title}[/]", style="blue"))
    console.print()


# ──────────────────────────────────────────────────────────────
# Unmount confirmation
# ──────────────────────────────────────────────────────────────

def confirm_unmount(device: BlockDevice) -> bool:
    mps = ", ".join(device.all_mount_points)
    console.print()
    print_warning(
        f"Device [bold]{device.path}[/] is mounted at: [yellow]{mps}[/]\n"
        "  It must be unmounted before wiping."
    )
    return Confirm.ask("  Unmount now and continue?", default=True)
