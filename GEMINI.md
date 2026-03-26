# GEMINI.md — Project Context: safewipe

This file provides critical context, architectural mandates, and operational guidelines for the `safewipe` project. Adhere to these standards for all development, maintenance, and refactoring tasks.

## 1. Project Overview
`safewipe` is a production-grade Python CLI tool designed for the secure wiping, partitioning, and formatting of external storage devices (USB drives, SD cards, SSDs) on Linux. It prioritizes safety through multi-layered system-disk detection, interactive confirmations, and robust validation.

- **Main Technologies**: Python 3.11+, Typer (CLI), Rich (UI), python-dotenv (Config), pytest (Testing).
- **Core Architecture**: SOLID-based modular design using Strategy and Manager patterns.
- **Key Modules**:
  - `device.py`: Discovery, system-disk detection, and validation.
  - `wipe.py`: Implementation of wipe strategies (Zero, Random, Secure, Blkdiscard).
  - `format.py`: Partitioning and filesystem formatting (GPT/MBR, FAT32/exFAT/ext4).
  - `ui.py`: Rich terminal components and interactive wizards.
  - `logger.py`: Structured JSON logging to `~/.safewipe/logs/`.

## 2. Engineering Standards & Mandates

### 2.1 Architectural Integrity (SOLID)
- **Single Responsibility (SRP)**: Isolate logic into dedicated classes (e.g., `SystemDiskDetector` vs. `DeviceDiscovery`).
- **Open/Closed (OCP)**: Extend functionality by adding new strategies (e.g., a new `WipeStrategy` or `FilesystemStrategy`) rather than modifying existing logic.
- **Dependency Inversion (DIP)**: High-level modules must depend on abstract interfaces or the centralized `config` module, not concrete implementations or hardcoded values.

### 2.2 Development Conventions
- **Type Hinting**: All functions and methods MUST have comprehensive PEP 484 type annotations.
- **Error Handling**: Use the typed exception hierarchy in `exceptions.py`. Avoid bare `except` blocks; catch specific exceptions and provide contextual error messages.
- **Configuration**: Never hardcode paths or constants. Use `safewipe.config` getters, which load from `.env` or environment variables.
- **Code Style**: Adhere to a 100-character line length limit. Use `ruff` for linting and formatting.

### 2.3 Testing Mandate
- **Safety First**: NEVER run tests against real physical disks.
- **Loopback Testing**: Use the loopback device fixtures provided in `tests/test_safewipe.py` for all functional tests.
- **Validation**: Every new feature or bug fix must include a corresponding test case in the `tests/` directory.

## 3. Operational Workflows

### 3.1 Setup & Installation
```bash
# Recommended: Virtual Environment Setup
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 3.2 Building & Running
- **Run Tool**: `sudo .venv/bin/safewipe [COMMAND]` (Root is mandatory for block device access).
- **List Devices**: `sudo .venv/bin/safewipe list`
- **Auto Mode**: `sudo .venv/bin/safewipe auto` (Full guided workflow).

### 3.3 Testing & Quality Control
- **Run All Tests**: `sudo .venv/bin/pytest tests/ -v`
- **Check Coverage**: `sudo .venv/bin/pytest tests/ --cov=safewipe`
- **Linting**: `ruff check .`

## 4. Dev Container Support
The project is fully configured for VS Code Dev Containers.
- **Privileged Access**: The container requires `--privileged` and a bind-mount for `/dev` to interact with host storage devices.
- **Post-Create**: The container automatically sets up the virtual environment and installs dependencies via `.devcontainer/scripts/post-create-commands.sh`.

## 5. Security & Safety Rules
- **System Disks**: `safewipe` must block operations on system disks unless the `--force` flag is explicitly used.
- **Confirmation**: Destructive operations (wipe/format) must require multi-step user confirmation.
- **Logging**: All destructive operations must be logged to a structured JSON file for auditability.
