# safewipe

> **Production-grade CLI tool for safely wiping, formatting, and preparing external storage devices.**
> Safer than `dd`. Easier than GUI tools. Powerful enough for professionals.

```
 ███████╗ █████╗ ███████╗███████╗██╗    ██╗██╗██████╗ ███████╗
 ██╔════╝██╔══██╗██╔════╝██╔════╝██║    ██║██║██╔══██╗██╔════╝
 ███████╗███████║█████╗  █████╗  ██║ █╗ ██║██║██████╔╝█████╗  
 ╚════██║██╔══██║██╔══╝  ██╔══╝  ██║███╗██║██║██╔═══╝ ██╔══╝  
 ███████║██║  ██║██║     ███████╗╚███╔███╔╝██║██║     ███████╗
 ╚══════╝╚═╝  ╚═╝╚═╝     ╚══════╝ ╚══╝╚══╝ ╚═╝╚═╝     ╚══════╝

       Production-grade storage wipe & format tool  •  v1.0.0
```

---

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Commands](#commands)
- [Wipe Methods](#wipe-methods)
- [Safety Mechanisms](#safety-mechanisms)
- [Usage Examples](#usage-examples)
- [Sample Output](#sample-output)
- [Testing](#testing)
- [Architecture](#architecture)
- [FAQ](#faq)

---

## Features

| Feature | safewipe | dd | shred | nwipe |
|---|:---:|:---:|:---:|:---:|
| Device safety checks | ✅ | ❌ | ❌ | ⚠️ |
| Auto system-disk detection | ✅ | ❌ | ❌ | ⚠️ |
| Multi-step confirmation | ✅ | ❌ | ❌ | ✅ |
| Real-time progress + ETA | ✅ | ❌ | ❌ | ✅ |
| Auto format after wipe | ✅ | ❌ | ❌ | ❌ |
| Auto-mount after format | ✅ | ❌ | ❌ | ❌ |
| Wipe verification | ✅ | ❌ | ❌ | ✅ |
| Structured logging | ✅ | ❌ | ❌ | ⚠️ |
| Dry-run mode | ✅ | ❌ | ❌ | ❌ |
| Scriptable CLI | ✅ | ✅ | ✅ | ⚠️ |
| Beautiful TUI | ✅ | ❌ | ❌ | ✅ |

---

## Installation

### Requirements

- **OS**: Linux (Ubuntu 20.04+, Debian 11+, Fedora 36+, Arch, etc.)
- **Python**: 3.11 or newer
- **Root**: Required for disk operations (`sudo`)
- **System tools**: `lsblk`, `parted`, `partprobe` (usually pre-installed)
- **Optional**: `mkfs.fat` (dosfstools), `mkfs.exfat` (exfatprogs), `blkdiscard` (util-linux)

### Install system dependencies

```bash
# Debian / Ubuntu
sudo apt update
sudo apt install python3 python3-pip parted dosfstools exfatprogs util-linux

# Fedora / RHEL
sudo dnf install python3 python3-pip parted dosfstools exfatprogs util-linux

# Arch Linux
sudo pacman -S python python-pip parted dosfstools exfatprogs util-linux
```

### Install safewipe

**Option A — pip (recommended)**

```bash
# Clone the repository
git clone https://github.com/yourname/safewipe.git
cd safewipe

# Install into an isolated virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Run (always as root)
sudo .venv/bin/safewipe --help
```

**Option B — system-wide (for convenience)**

```bash
sudo pip3 install -e .
sudo safewipe --help
```

**Option C — pipx**

```bash
pipx install git+https://github.com/yourname/safewipe.git
sudo safewipe --help
```

### Verify installation

```bash
sudo safewipe list
```

---

## Quick Start

```bash
# 1. List connected devices
sudo safewipe list

# 2. Full guided workflow (recommended for first-time users)
sudo safewipe auto

# 3. Wipe a specific device
sudo safewipe wipe /dev/sdb

# 4. Wipe with a specific method and verify
sudo safewipe wipe /dev/sdb --method secure --verify
```

---

## Commands

### `safewipe list`

List all detected block devices.

```
safewipe list [OPTIONS]

Options:
  --all, -a     Show all devices including system disks
  --force, -f   Same as --all
```

### `safewipe wipe [DEVICE]`

Wipe a storage device securely.

```
safewipe wipe [DEVICE] [OPTIONS]

Arguments:
  DEVICE        Optional device path (e.g. /dev/sdb).
                If omitted, interactive selection is shown.

Options:
  --method, -m  [quick|zero|random|secure|blkdiscard]  Wipe method
  --verify, -V  Verify wipe by sampling random sectors after completion
  --dry-run     Simulate without writing (safe for testing)
  --force       Allow wiping non-removable or system disks
  --no-confirm  Skip confirmation prompts (for scripting only)
  --no-format   Skip the format wizard after wiping
```

### `safewipe format DEVICE`

Partition and format a device (without wiping).

```
safewipe format DEVICE [OPTIONS]

Options:
  --fs          [fat32|exfat|ext4]         Filesystem (default: fat32)
  --table, -t   [mbr|gpt]                  Partition table (default: gpt)
  --label, -l   TEXT                       Volume label (max 11 chars)
  --mount/--no-mount                       Auto-mount after formatting
  --dry-run     Simulate without writing
  --force       Skip safety checks
```

### `safewipe auto`

Full guided workflow: select → wipe → format → mount.

```
safewipe auto [OPTIONS]

Options:
  --dry-run     Simulate the entire workflow
  --force       Show all devices including system disks
```

### `safewipe verify DEVICE`

Spot-check random sectors to confirm a completed wipe.

```
safewipe verify DEVICE [OPTIONS]

Options:
  --method, -m  [zero|random|secure|…]   Wipe method that was used
```

### `safewipe logs`

View recent operation history.

```
safewipe logs [OPTIONS]

Options:
  --last, -n    INTEGER   Number of entries to show (default: 20)
```

---

## Wipe Methods

| Method | Passes | Speed | Security | Best For |
|---|:---:|---|---|---|
| `quick` | 1 | ⚡ Instant | ⭐ None | Quick reuse, device hand-off (not secure) |
| `zero` | 1 | ✅ Fast | ⭐⭐ Low | Reuse on trusted systems |
| `random` | 1 | 🐢 Slow | ⭐⭐⭐ Medium | Privacy-conscious disposal |
| `secure` | 3 | 🐢🐢 Very slow | ⭐⭐⭐⭐ High | Regulatory/compliance, resale |
| `blkdiscard` | 1 | ⚡⚡ Fastest | ⭐⭐⭐⭐⭐ Best (SSD) | SSD/NVMe drives (hardware erase) |

**Secure wipe** uses a 3-pass DoD 5220.22-M inspired sequence:
1. Pass 1: Full overwrite with zeros
2. Pass 2: Full overwrite with random data
3. Pass 3: Full overwrite with zeros

---

## Safety Mechanisms

safewipe implements multiple layers of protection:

### 1. System Disk Detection

Before any operation, safewipe checks `/proc/mounts` and `findmnt` to identify which devices contain `/`, `/boot`, `/boot/efi`, `/usr`, `/var`, or `/home`. These are marked as **SYSTEM** and cannot be wiped without `--force`.

```
⛔  SYSTEM   /dev/sda   Samsung 870 EVO   500G   SATA
```

### 2. Multi-Step Confirmation

Wiping requires two confirmation steps:

```
Step 1/2 — Type the device path to confirm: /dev/sdb
  Device path: /dev/sdb

Step 2/2 — Type exactly: WIPE /dev/sdb
  Confirmation: WIPE /dev/sdb

✓  Confirmed. Proceeding with wipe…
```

### 3. Mount Safety

If a device is mounted, safewipe detects this and offers to unmount before proceeding:

```
⚠  Device /dev/sdb is mounted at: /media/user/USB
   It must be unmounted before wiping.
   Unmount now and continue? [y/N]
```

### 4. Dry-Run Mode

All destructive operations support `--dry-run` — they simulate the workflow (including the full progress bar) without writing a single byte:

```bash
sudo safewipe wipe /dev/sdb --method secure --dry-run
```

### 5. Read-Only Detection

safewipe checks `lsblk` for the `RO` flag and refuses to attempt writes on read-only devices.

---

## Usage Examples

```bash
# Interactive guided wizard — recommended for beginners
sudo safewipe auto

# List all devices (including system disks)
sudo safewipe list --all

# Wipe interactively (prompted to pick a device and method)
sudo safewipe wipe

# Zero-wipe a specific device
sudo safewipe wipe /dev/sdb --method zero

# Secure 3-pass wipe with post-wipe verification
sudo safewipe wipe /dev/sdb --method secure --verify

# SSD-optimized wipe (blkdiscard TRIM)
sudo safewipe wipe /dev/sdb --method blkdiscard

# Dry run — simulate without writing
sudo safewipe wipe /dev/sdb --method secure --dry-run

# Wipe and skip the format wizard
sudo safewipe wipe /dev/sdb --no-format

# Format only (skip wipe) — FAT32 with label
sudo safewipe format /dev/sdb --fs fat32 --label MYUSB

# Format as ext4 with GPT table, no auto-mount
sudo safewipe format /dev/sdb --fs ext4 --table gpt --no-mount

# Format as exFAT with custom label
sudo safewipe format /dev/sdb --fs exfat --label BACKUP

# Verify a previous wipe
sudo safewipe verify /dev/sdb --method zero

# View last 10 operations
sudo safewipe logs --last 10

# Scripting — wipe without interactive prompts
sudo safewipe wipe /dev/sdb --method zero --no-confirm --no-format
```

---

## Sample Output

### `safewipe list`

```
 ███████╗ █████╗ ███████╗███████╗██╗    ██╗██╗██████╗ ███████╗
 ...
       Production-grade storage wipe & format tool  •  v1.0.0

╭────────────────────────────────────────────────────────────────────────────────╮
│                          Detected Block Devices                                │
├────────────┬────────────────────────┬──────────┬──────────┬──────────┬────────┤
│ Device     │ Model / Vendor         │    Size  │ Type     │ Mount    │ Status │
├────────────┼────────────────────────┼──────────┼──────────┼──────────┼────────┤
│ /dev/sda   │ Samsung 870 EVO 500GB  │   500.1G │ 💾 SATA  │ /, /boot │ ⛔ SYSTEM │
│ /dev/sdb   │ SanDisk Ultra          │    32.0G │ 🔌 USB   │ —        │ ✅ READY │
│ /dev/sdc   │ WD Elements 1TB        │     1.0T │ 🔌 USB   │ /media/… │ 📌 MOUNTED │
╰────────────┴────────────────────────┴──────────┴──────────┴──────────┴────────╯

  3 device(s) found.  Use safewipe wipe to start wiping.
```

### `safewipe wipe` — device selection

```
──────────────────────────── Device Selection ───────────────────────────────────

  #  Device      Model / Vendor          Size    Type      Mount    Status
  ─────────────────────────────────────────────────────────────────────────
  1  /dev/sdb    SanDisk Ultra           32.0G   🔌 USB    —        ✅ READY
  2  /dev/sdc    WD Elements 1TB          1.0T   🔌 USB    /media   📌 MOUNTED

Select device number (q to quit): 1
```

### `safewipe wipe` — method selection

```
─────────────────────────────── Wipe Method ──────────────────────────────────

  #  Method        Passes  Description
  ──────────────────────────────────────────────────────────────────────────
  1  Quick              1  Zero first & last 10 MB only (instant, not secure)
  2  Zero               1  Full overwrite with zeros (fast, recoverable)
  3  Random             1  Full overwrite with random data (secure, slow)
  4  Secure             3  3-pass wipe: zero → random → zero (DoD-grade)
  5  Blkdiscard         1  SSD TRIM discard (fastest on SSDs)

Select method [1]: 4
```

### `safewipe wipe` — confirmation

```
╭──────────────────────────── ⚠  DANGER ZONE ──────────────────────────────╮
│                                                                            │
│   ⚠️   YOU ARE ABOUT TO PERMANENTLY DESTROY ALL DATA   ⚠️                │
│                                                                            │
│   Device : /dev/sdb                                                        │
│   Model  : SanDisk Ultra                                                   │
│   Size   : 32.0G                                                           │
│                                                                            │
╰────────────────────────────────────────────────────────────────────────────╯

Step 1/2 — Type the device path to confirm: /dev/sdb
  Device path: /dev/sdb

Step 2/2 — Type exactly: WIPE /dev/sdb
  Confirmation: WIPE /dev/sdb

✓  Confirmed. Proceeding with wipe…
```

### `safewipe wipe` — progress

```
──────────────────────────────── Wiping ────────────────────────────────────────

⠙ Pass 1/3: Zeros  ████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░   32.1%  98.4 MB/s  0:00:12  ETA 0:00:25
```

### `safewipe wipe` — result

```
╭──────────────────────────── ✓  WIPE COMPLETE ──────────────────────────────╮
│                                                                             │
│   Wipe completed successfully!                                              │
│                                                                             │
│   Method   : secure                                                         │
│   Device   : /dev/sdb                                                       │
│   Passes   : 3                                                              │
│   Written  : 96.0 GB  (3 × 32 GB)                                          │
│   Duration : 427.3s                                                         │
│   ✓  Verification passed                                                    │
│   Log      : /root/.safewipe/logs/safewipe-2025-01-15.log                  │
│                                                                             │
╰─────────────────────────────────────────────────────────────────────────────╯
```

### `safewipe format` wizard

```
───────────────────────────────── Format ───────────────────────────────────────

Partition and format the device after wiping? [Y/n]: Y

  #  Name  Description
  ─────────────────────────────────────────────────────────────
  1  MBR   Legacy (BIOS), max 2 TB, max 4 primary partitions
  2  GPT   Modern (UEFI), >2 TB, up to 128 partitions

Select [2]: 2

  #  Name   Description
  ───────────────────────────────────────────────────────────────────────────
  1  FAT32  Universal (Windows/Mac/Linux/cameras/consoles)
  2  EXFAT  Large files >4 GB, cross-platform (needs exfatprogs)
  3  EXT4   Linux-native, journaled, best performance on Linux
  4  NONE   Skip formatting (partition table only)

Select [1]: 1

Volume label (max 11 chars) [SAFEWIPE]: MYUSB
Auto-mount after formatting? [Y/n]: Y

ℹ  Creating GPT partition table…
ℹ  Creating primary partition…
ℹ  Formatting as FAT32…
ℹ  Mounting to /media/…

╭────────────────────────── ✓  FORMAT COMPLETE ──────────────────────────────╮
│                                                                             │
│   Format completed successfully!                                            │
│                                                                             │
│   Partition : /dev/sdb1                                                     │
│   Filesystem: fat32                                                         │
│   Label     : MYUSB                                                         │
│   Mount     : /media/user/MYUSB                                             │
│   Duration  : 3.2s                                                          │
│                                                                             │
╰─────────────────────────────────────────────────────────────────────────────╯
```

### `safewipe logs`

```
╭──────────────────────────── Last 5 Operations ─────────────────────────────╮
│                                                                             │
│  Time                 Operation  Device     Method   Result    Duration     │
│  ─────────────────────────────────────────────────────────────────────     │
│  2025-01-15T14:22:01  wipe       /dev/sdb   secure   success   427.3s      │
│  2025-01-15T14:22:33  format     /dev/sdb   —        success   3.2s        │
│  2025-01-14T09:11:44  wipe       /dev/sdc   zero     success   112.7s      │
│  2025-01-13T18:05:22  wipe       /dev/sdb   quick    success   0.4s        │
│  2025-01-13T17:58:10  wipe       /dev/sdb   zero     dry_run   —           │
│                                                                             │
╰─────────────────────────────────────────────────────────────────────────────╯

Log directory: /root/.safewipe/logs
```

---

## Testing

The test suite uses **loopback devices** (files mounted as block devices) — no real disk is ever touched.

```bash
# Install test dependencies
pip install -e ".[dev]"

# Run all tests (requires root)
sudo pytest tests/ -v

# Run only fast (dry-run) tests
sudo pytest tests/ -v -k "dry_run"

# Run with coverage
sudo pytest tests/ --cov=safewipe --cov-report=term-missing
```

### Loopback device testing

The test fixture creates a 64 MiB temporary file, attaches it as a loopback device via `losetup`, runs all tests against it, and cleans up automatically — even if tests fail.

---

## Architecture

```
safewipe/
├── safewipe/
│   ├── __init__.py     — version & package metadata
│   ├── main.py         — Typer CLI entrypoint, all commands
│   ├── device.py       — lsblk discovery, system-disk detection, mount management
│   ├── wipe.py         — wipe strategies, progress engine, verification
│   ├── format.py       — partition tables, mkfs, auto-mount
│   ├── ui.py           — Rich components: tables, prompts, progress, panels
│   └── logger.py       — JSON-lines structured logging
├── tests/
│   └── test_safewipe.py — pytest suite (loopback device)
├── pyproject.toml
└── README.md
```

### Module responsibilities

| Module | Responsibility |
|---|---|
| `device.py` | Enumerate devices, detect system disks, unmount, validate |
| `wipe.py` | Execute wipe passes, emit progress, verify result |
| `format.py` | Create partition table, mkfs, mount |
| `ui.py` | All Rich terminal UI: tables, prompts, progress bars, panels |
| `logger.py` | Append structured JSON-lines logs to `~/.safewipe/logs/` |
| `main.py` | Typer commands, root check, orchestrate modules |

---

## FAQ

**Q: Why does safewipe need root?**  
Writing to raw block devices requires root privileges on Linux. Always use `sudo safewipe …`.

**Q: Can I wipe my system disk?**  
Not by default. safewipe detects system disks and blocks them. Use `--force` if you truly know what you're doing (e.g., preparing a disk for reinstall from a live ISO).

**Q: Is a zero wipe sufficient for data security?**  
For modern drives (especially SSDs), a single zero pass prevents casual data recovery. For compliance or resale, use `--method secure`. For SSDs, `--method blkdiscard` is the most thorough as it uses the hardware's built-in secure erase.

**Q: How do I test without a real USB drive?**  
Use `--dry-run` mode, or run `sudo pytest tests/` which uses loopback devices automatically.

**Q: What if blkdiscard isn't available?**  
Install `util-linux` (`apt install util-linux`). If the SSD firmware doesn't support TRIM, safewipe will report the error and suggest a fallback method.

**Q: Where are logs stored?**  
In `~/.safewipe/logs/safewipe-YYYY-MM-DD.log` as JSON-lines. View with `safewipe logs` or any JSON-aware tool.

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Contributing

1. Fork the repository
2. Create a feature branch
3. Write tests for your changes
4. Ensure `sudo pytest tests/` passes
5. Open a pull request

---

*safewipe is designed with safety as the primary goal. When in doubt, use `--dry-run` first.*
