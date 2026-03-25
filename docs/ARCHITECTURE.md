# safewipe Architecture

## Overview

safewipe follows SOLID principles and clean architecture patterns to ensure maintainability, testability, and extensibility. The codebase is organized into functional modules with clear separation of concerns.

---

## Directory Structure

```
safewipe/
├── __init__.py              # Package initialization
├── config.py                # Configuration management (environment, defaults)
├── exceptions.py            # Custom exception hierarchy
├── logger.py                # Operation logging (structured JSON)
├── device.py                # Device discovery and validation
├── wipe.py                  # Wipe strategies and verification
├── format.py                # Partition and filesystem management
├── ui.py                    # Terminal UI components
└── main.py                  # CLI entrypoint and command routing
```

---

## Module Descriptions

### `config.py` — Configuration Management

**Responsibility**: Centralized configuration loading and validation.

**Features**:
- Loads environment variables from `.env` file
- Provides typed getter functions for all configuration values
- Validates configuration on startup
- Supports environment variable overrides for all settings

**Key Functions**:
- `get_log_dir()` → `Path` - Directory for operation logs
- `get_block_size()` → `int` - I/O block size for wipe operations
- `get_auto_mount()` → `bool` - Auto-mount after formatting
- `validate_config()` → `list[str]` - Validate all settings

**Idiomatic Python**:
- Uses `Path.expanduser()` for home directory expansion
- Type hints on all functions
- Graceful fallback to defaults if environment variables missing

---

### `exceptions.py` — Exception Hierarchy

**Responsibility**: Typed, descriptive exceptions for all error scenarios.

**Exception Classes**:
```
SafeWipeError (base)
├── DeviceError
│   ├── DeviceNotFoundError
│   ├── DeviceMountedError
│   └── SystemDiskError
├── WipeError
│   ├── WipeExecutionError
│   └── WipeVerificationError
├── FormatError
│   ├── PartitionError
│   ├── FilesystemError
│   └── MountError
├── ConfigError
├── MissingDependencyError
└── PermissionError_
```

**SOLID Principle Applied**: Single Responsibility
- Each exception represents a specific failure category
- Enables precise error handling and recovery
- Improves debugging through exception specificity

---

### `logger.py` — Operation Logging

**Responsibility**: Structured logging of all device operations.

**Architecture**:
- `OperationLogger` class encapsulates logging logic
- Module-level functions provide convenience interface
- JSON-lines format for easy parsing and analysis

**Key Features**:
- Timestamps in ISO 8601 format
- Operation type, device, result, and error tracking
- Optional sensitive data filtering (controlled by `SAFEWIPE_LOG_SENSITIVE_DATA`)
- Graceful error handling with typed exceptions

**SOLID Principles Applied**:
- **Single Responsibility**: Only handles logging, no business logic
- **Dependency Inversion**: Uses config module for paths, not hardcoded values

---

### `device.py` — Device Discovery & Validation

**Responsibility**: Enumerate, discover, and validate block devices.

**Architecture** (SOLID — Single Responsibility):

| Class | Responsibility |
|-------|-----------------|
| `BlockDevice` | Data model for a block device |
| `SystemDiskDetector` | Detects system/boot disks (via findmnt, /proc/mounts) |
| `MountpointResolver` | Queries and resolves mount points |
| `DeviceDiscovery` | Orchestrates device enumeration (via lsblk) |
| `DeviceValidator` | Validates devices for wipe operations (safety checks) |

**Public API** (unchanged):
- `list_devices(include_loop: bool) → list[BlockDevice]` - Enumerate all devices
- `get_device_by_path(path: str) → Optional[BlockDevice]` - Find device by path
- `validate_wipe_target(device, force, dry_run) → list[str]` - Pre-wipe safety checks
- `unmount_device(device, dry_run) → list[str]` - Safely unmount device

**Key Safety Checks**:
- System disk detection (prevents accidental system wipe)
- Mount status validation (requires explicit unmounting)
- Read-only device detection
- Removable device verification (unless --force)

**Error Handling**:
- Specific exceptions: `DeviceError`, `DeviceMountedError`, `SystemDiskError`, etc.
- No bare `except: pass` clauses
- Detailed error messages with context

**SOLID Principles Applied**:
- **Single Responsibility**: Each class has one reason to change
- **Open/Closed**: New device types don't require modifying existing code
- **Dependency Inversion**: Abstract detection logic from discovery logic

---

### `wipe.py` — Wipe Strategies & Verification

**Responsibility**: Execute device wipes and verify success.

**Architecture** (SOLID — Strategy Pattern):

| Class | Strategy |
|-------|----------|
| `WipeStrategy` (ABC) | Abstract base for wipe implementations |
| `QuickWipeStrategy` | 10 MB header/footer only (fast, for reuse) |
| `ZeroWipeStrategy` | Full overwrite with zeros (fast, recoverable) |
| `RandomWipeStrategy` | Full overwrite with random (secure, slow) |
| `SecureWipeStrategy` | 3-pass: zero → random → zero (DoD-grade) |
| `BlkdiscardStrategy` | SSD TRIM/hardware erase (fastest on SSDs) |
| `WipeVerifier` | Spot-check wipe success by sampling sectors |

**Key Classes**:
- `WipeMethod` (Enum) - Available wipe strategies
- `WipeProgress` - Progress tracking (bytes, passes, ETA)
- `WipeResult` - Operation result and metadata

**Public API** (unchanged):
- `wipe_device(device, method, progress_cb, dry_run) → WipeResult` - Execute wipe
- `verify_wipe(device, method, dry_run) → bool` - Verify wipe success
- Helper functions: `format_bytes()`, `format_speed()`, `format_eta()`

**Error Handling**:
- Specific exceptions: `WipeError`, `WipeExecutionError`, `WipeVerificationError`
- Subprocess error handling with detailed messages
- Device disconnection detection

**SOLID Principles Applied**:
- **Open/Closed**: New wipe methods inherit from `WipeStrategy`, no existing code changes
- **Liskov Substitution**: All strategies implement consistent `execute()` interface
- **Single Responsibility**: `WipeVerifier` separated from `WipeStrategy`
- **Dependency Inversion**: Strategies depend on abstract interface, not implementation

**Configuration Integration**:
- Block size: `config.get_block_size()`
- Quick wipe size: `config.get_quick_wipe_size()`
- Verification samples: `config.get_verify_sample_count()`

---

### `format.py` — Partitioning & Filesystem Management

**Responsibility**: Partition and format block devices.

**Architecture** (SOLID — Strategy + Manager Patterns):

| Class | Responsibility |
|-------|-----------------|
| `PartitionTableStrategy` (ABC) | Abstract partition table implementation |
| `MBRStrategy` | Legacy MBR/msdos partitioning |
| `GPTStrategy` | Modern GPT partitioning |
| `FilesystemStrategy` (ABC) | Abstract filesystem implementation |
| `FAT32Strategy` | FAT32 filesystem creation |
| `ExFATStrategy` | exFAT filesystem creation |
| `EXT4Strategy` | ext4 filesystem creation |
| `PartitionTableManager` | Orchestrate partition table creation |
| `FilesystemFormatter` | Orchestrate filesystem formatting |
| `DeviceMounter` | Mount device and fix permissions |

**Key Classes**:
- `PartitionTable` (Enum) - MBR, GPT
- `Filesystem` (Enum) - FAT32, exFAT, ext4, none
- `FormatResult` - Operation result and metadata

**Public API** (unchanged):
- `check_format_deps() → list[str]` - Verify required tools installed
- `prepare_device(...) → FormatResult` - Execute partition + format + mount workflow

**Improvements**:
- No silent failures (all exceptions properly caught and reported)
- Better permission handling (detects sudo via `SUDO_USER`)
- Proper mount point creation and cleanup
- Partition detection with configurable retry logic

**SOLID Principles Applied**:
- **Open/Closed**: New partition tables/filesystems inherit from abstract strategies
- **Single Responsibility**: Manager and strategy classes separated
- **Liskov Substitution**: Strategies implement consistent interface
- **Dependency Inversion**: Strategies depend on abstract interface

**Configuration Integration**:
- Mount base path: `config.get_mount_base()`
- Partition detection timeout: `config.get_partition_detection_timeout()`
- Partition detection retries: `config.get_partition_detection_retries()`

---

### `ui.py` — Terminal User Interface

**Responsibility**: Rich-based terminal UI components.

**Components**:
- Device listing table with filtering and formatting
- Interactive device selector with fuzzy search
- Multi-step confirmation prompts
- Live wipe progress bar with ETA
- Status panels and result displays
- Method selection menu (wipe, filesystem, partition table)
- Format wizard workflow

**Key Functions**:
- `select_device()` - Interactive device selection
- `confirm_wipe()` - Multi-step confirmation
- `select_wipe_method()` - Choose wipe strategy
- `WipeProgressDisplay` - Live progress tracking
- `format_wizard()` - Guided partitioning/formatting workflow

**Design**:
- Decoupled from business logic (no direct device operations)
- Uses data models (BlockDevice, WipeProgress, etc.) for display
- Consistent color scheme: warnings in red, info in yellow, success in green

---

### `main.py` — CLI Entrypoint

**Responsibility**: Command routing and orchestration.

**Commands**:
- `list` - List all block devices
- `wipe` - Wipe a device
- `format` - Partition and format a device
- `auto` - Guided full workflow (discover → wipe → format → mount)
- `verify` - Spot-check wipe quality on existing device
- `logs` - View recent operation logs

**Architecture**:
- Typer for command routing
- Helper functions for common patterns (`_require_root()`, `_get_device()`, etc.)
- Clear separation: validation → UI → execution → logging

**Error Handling**:
- Root privilege checks
- Configuration validation
- Specific exception handling with user-friendly messages

---

## Design Patterns Used

### 1. **Strategy Pattern** (SOLID - OCP, LSP)

Used in `wipe.py` and `format.py`:
```python
# Wipe strategies
class WipeStrategy(abc.ABC):
    @abc.abstractmethod
    def execute(self, device: BlockDevice, progress_cb: ProgressCallback) -> WipeResult:
        pass

class ZeroWipeStrategy(WipeStrategy):
    def execute(self, ...): ...

class RandomWipeStrategy(WipeStrategy):
    def execute(self, ...): ...
```

**Benefit**: New strategies added without modifying existing code.

### 2. **Manager Pattern** (SOLID - SRP)

Used in `format.py`:
```python
class PartitionTableManager:
    def __init__(self, strategy: PartitionTableStrategy):
        self.strategy = strategy
    
    def create(self, device: BlockDevice, ...):
        return self.strategy.execute(device, ...)
```

**Benefit**: Strategies decoupled from orchestration logic.

### 3. **Detector/Resolver Pattern** (SOLID - SRP)

Used in `device.py`:
```python
class SystemDiskDetector:
    """Detects system/boot disks."""
    def detect(self) -> set[str]: ...

class MountpointResolver:
    """Resolves mount points."""
    def get_mount_points(self) -> dict[str, list[str]]: ...
```

**Benefit**: Each responsibility isolated in separate class.

### 4. **Config Pattern** (SOLID - DIP)

All modules depend on abstract `config` module:
```python
from safewipe import config

block_size = config.get_block_size()  # Don't hardcode
log_dir = config.get_log_dir()        # Don't hardcode
```

**Benefit**: Configuration centralized, easily testable/overridable.

---

## SOLID Principles Implementation

### S — Single Responsibility Principle ✅

Each class/module has ONE reason to change:
- `SystemDiskDetector` - only changes if system disk detection logic changes
- `WipeStrategy` implementations - only change if wipe algorithm changes
- `OperationLogger` - only changes if logging format changes

### O — Open/Closed Principle ✅

Classes open for extension, closed for modification:
- Add new wipe method? → Create `NewStrategy(WipeStrategy)`
- Add new filesystem? → Create `NewFilesystemStrategy(FilesystemStrategy)`
- No existing code needs modification

### L — Liskov Substitution Principle ✅

Subtypes substitute for base types without breaking:
```python
strategy: WipeStrategy = QuickWipeStrategy()  # or any other strategy
result = strategy.execute(device, progress_cb)  # Works identically
```

### I — Interface Segregation Principle ✅

Clients depend only on methods they use:
- UI layer doesn't import wipe internals (strategy classes)
- Device discovery layer doesn't import format classes
- Focused interfaces reduce coupling

### D — Dependency Inversion Principle ✅

High-level modules depend on abstractions:
- `main.py` depends on abstract `config`, not concrete values
- `wipe.py` depends on abstract `WipeStrategy`, not concrete implementations
- Strategies depend on abstract `BlockDevice`, not implementation details

---

## Error Handling Strategy

All error handling follows typed exception hierarchy:

```python
try:
    wipe_device(...)
except WipeExecutionError as e:
    # Handle wipe failure (specific)
    log_operation(..., error=str(e))
except WipeError as e:
    # Handle any wipe-related error (general)
    print(f"Wipe failed: {e}")
except SafeWipeError as e:
    # Handle any safewipe error
    print(f"Error: {e}")
```

**Benefits**:
- Specific handling for specific errors
- Graceful degradation
- Clear error propagation
- Easy testing and debugging

---

## Configuration Approach

All configuration from `.env` file or environment variables:

```python
# In .env
SAFEWIPE_LOG_DIR=~/.safewipe/logs
SAFEWIPE_AUTO_MOUNT=true
SAFEWIPE_BLOCK_SIZE=4194304

# In Python
log_dir = config.get_log_dir()
```

**Benefits**:
- No hardcoded values
- Easy to configure per environment
- Testable (override in tests)
- Secrets-friendly (never commit .env)

---

## Type Hints

All modules use comprehensive type hints for:
- Function parameters and return types
- Class attributes
- Callback signatures
- Generic types (`list[BlockDevice]`, `dict[str, Any]`, etc.)

**Benefits**:
- IDE autocomplete and documentation
- Type checker support (mypy)
- Self-documenting code
- Fewer runtime errors

---

## Future Extension Points

The architecture supports easy extension:

### Add a New Wipe Method
```python
class DoD7PassStrategy(WipeStrategy):
    """DoD 7-pass wipe variant."""
    def execute(self, device, progress_cb):
        # Implementation
        pass
```

### Add a New Filesystem
```python
class NTFSStrategy(FilesystemStrategy):
    """NTFS filesystem support."""
    def execute(self, device, label):
        # Implementation
        pass
```

### Add Configuration
Add to `.env.example` and `config.py`:
```python
def get_my_new_setting() -> str:
    return os.getenv("SAFEWIPE_MY_NEW_SETTING", "default_value")
```

### Add Logging
```python
logger.log_operation(
    operation="custom_op",
    device_path=device.path,
    result="success",
    details={"custom": "data"}
)
```

---

## Testing Strategy

See `test_safewipe.py` for test approach:
- Loopback device fixtures for safe testing
- No real disk access during tests
- Each module independently testable
- Mock external commands (lsblk, parted, mkfs, etc.)

---

## Dependency Graph

```
main.py (orchestrator)
├─ device.py (discovery)
│  └─ config.py
├─ wipe.py (execution)
│  ├─ config.py
│  └─ device.py (type only)
├─ format.py (partitioning)
│  ├─ config.py
│  └─ device.py (type only)
├─ ui.py (presentation)
│  ├─ device.py (BlockDevice)
│  ├─ wipe.py (types)
│  └─ format.py (types)
├─ logger.py (logging)
│  └─ config.py
└─ exceptions.py (no internal deps)
```

**Properties**:
- No circular dependencies ✅
- Clear direction of dependencies (top → down) ✅
- Minimal cross-module coupling ✅

---

## Performance Considerations

- **I/O Operations**: Configurable block size (default 4 MiB) balances speed vs. memory
- **Verification**: Configurable sample count (default 8) and size (512 KiB)
- **Partition Detection**: Configurable retry logic with exponential backoff
- **Progress Tracking**: Live updates without blocking wipe operation

---

## Security Considerations

- **No hardcoded secrets**: All paths/configs in .env
- **Sensitive data filtering**: Optional redaction in logs
- **Permission handling**: Proper sudo detection and permission fixing
- **Device validation**: System disk detection, mount status checking
- **Error details**: Contextual error messages without exposing system paths

---

## Maintenance & Development

### Adding a Feature
1. Identify which module it belongs to (or create new one)
2. Follow SOLID principles (SRP, especially)
3. Add type hints throughout
4. Use config for any new settings
5. Add specific exceptions if needed
6. Update tests

### Debugging
1. Check `.safewipe/logs/` for operation history
2. Use `--dry-run` to simulate without actual changes
3. Import modules individually to test specific functionality
4. Check config values: `python3 -c "from safewipe import config; print(config.get_*())"`

### Code Style
- 100 char line length (ruff configured)
- Type hints required
- f-strings for formatting
- Docstrings for public APIs
- Comments only for non-obvious logic

