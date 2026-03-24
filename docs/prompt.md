You are a senior systems engineer and CLI UX expert.

Build a production-grade Linux CLI tool called **"safewipe"** that safely wipes, formats, and prepares external storage devices (USB flash drives, HDDs, SSDs).

The tool must be significantly safer, more user-friendly, and more modern than traditional tools like `dd`, `shred`, or `nwipe`.

---

## 🎯 Core Objectives

1. Prevent accidental data loss at all costs
2. Provide a beautiful, intuitive CLI experience
3. Support full disk wipe workflows end-to-end
4. Be fast, reliable, and scriptable
5. Be suitable for both beginners and advanced users

---

## 🧠 Core Features

### 🔍 Device Discovery

- Automatically detect all block devices using `lsblk`
- Display:
  - Device name (e.g., /dev/sdb)
  - Size
  - Model/vendor
  - Mount status

- Clearly highlight:
  - ⚠️ System disk (e.g., /dev/sda) → MUST NOT be wipeable by default

- Only allow removable devices unless `--force` is used

---

### 🛡️ Safety Mechanisms (CRITICAL)

- Require multi-step confirmation:
  - User must select device from a numbered list
  - Must type full device name (e.g., `/dev/sdb`)
  - Must type a confirmation phrase like: `WIPE /dev/sdb`

- Refuse to run if:
  - Device is mounted (auto-unmount with confirmation)
  - Device is the system disk (unless `--force` flag is used)

- Add a `--dry-run` mode

---

### ⚡ Wipe Methods

Support multiple wipe strategies:

1. Quick format
2. Zero wipe (use `dd if=/dev/zero`)
3. Random wipe (`/dev/urandom`)
4. Secure wipe (multiple passes)
5. SSD optimized wipe (use `blkdiscard` when available)

Allow user to select method interactively or via flags.

---

### 📊 Progress & UX

- Real-time progress bar (percentage, speed, ETA)
- Clean terminal UI (use colors, spacing, icons where appropriate)
- Show:
  - Bytes written
  - Time elapsed
  - Estimated remaining time

---

### 🧱 Partition + Format

After wipe:

- Option to:
  - Create partition table (MBR/GPT)
  - Create partition
  - Format filesystem:
    - FAT32
    - exFAT
    - ext4

- Allow labeling (e.g., MYUSB)

---

### 🔌 Mounting

- Option to auto-mount after formatting
- Default mount path:
  - `/media/<user>/<label>`

- Ensure correct permissions for non-root usage

---

### ✅ Verification

- Option to verify wipe by sampling sectors
- Display:
  - “Wipe successful” or “Verification failed”

---

### 📁 Logging

- Log all operations to:
  - `~/.safewipe/logs/`

- Include:
  - Device info
  - Method used
  - Duration
  - Result

---

## 🧑‍💻 CLI Design (IMPORTANT)

Commands should feel modern and clean:

Examples:

- `safewipe list`
- `safewipe wipe`
- `safewipe wipe /dev/sdb --method zero`
- `safewipe format /dev/sdb1 --fs exfat --label MYUSB`
- `safewipe auto` (full guided workflow)

Include:

- `--interactive`
- `--force`
- `--dry-run`
- `--no-confirm`

---

## 🎨 UX Requirements

- Use a modern CLI framework (e.g., Python + Rich + Typer OR Go with Cobra)
- Use colors and formatting for clarity
- Show warnings in red, confirmations in yellow, success in green
- Make it impossible to confuse devices visually

---

## 🧱 Code Requirements

- Clean, modular architecture:
  - device.py
  - wipe.py
  - format.py
  - ui.py
  - main.py

- Use subprocess safely
- Handle errors gracefully
- Include inline documentation

---

## 🧪 Testing

- Include a safe test mode using loopback devices (e.g., files mounted as disks)
- Ensure no real disk is wiped during testing

---

## 📦 Output Requirements

- Provide:
  1. Full working code
  2. Installation instructions
  3. Usage examples
  4. Sample output screenshots (ASCII mockups)
  5. README.md

---

## 🔥 Stretch Goals (if possible)

- Fuzzy search for device selection
- Keyboard navigation (arrow keys)
- Config file support (~/.safewipe/config.yaml)
- Plugin system for new wipe methods

---

## 🚨 Final Rule

This tool must be:

- Safer than `dd`
- Easier than GUI tools
- Powerful enough for professionals

Focus heavily on UX, safety, and clarity.

Do NOT produce a minimal script — build a polished, production-quality CLI tool.
