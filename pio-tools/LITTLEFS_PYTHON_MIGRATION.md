# Migration to littlefs-python

## Overview

The PlatformIO scripts have been modified to use the native Python implementation `littlefs-python` instead of platform-specific `mklittlefs` tools.

## Benefits

- **Platform Independent**: No platform-specific binaries required
- **Easier Installation**: `pip install littlefs-python`
- **Better Maintainability**: Python code instead of external tools
- **Fallback Mechanism**: Automatic fallback to mklittlefs if littlefs-python is not available

## Modified Files

### 1. `custom_target.py`
**Function**: Download and extract LittleFS images from ESP32/ESP8266

**Changes**:
- Import of `littlefs-python` with fallback mechanism
- Modified `FS_Info` class to support both methods
- New `unpack_fs()` function with Python-based extraction:
  - Reads the downloaded filesystem image
  - Mounts it with `LittleFS`
  - Extracts all files and directories
  - Fallback to mklittlefs on errors

### 2. `post_esp32.py`
**Function**: Create LittleFS images for ESP32

**Changes**:
- Import of `littlefs-python` with fallback mechanism
- Modified `esp32_build_filesystem()` function:
  - Creates LittleFS image with Python
  - Supports all file types and directory structures
  - Uses correct block size (4096 for ESP32)
  - Fallback to mklittlefs on errors

## Installation

### Prerequisites

```bash
pip install littlefs-python
```

### Compatibility

- **Python**: 3.7 - 3.13
- **Platforms**: Linux, macOS, Windows
- **LittleFS Version**: 2.11.2 (Filesystem Version 2.0/2.1)

## Usage

Usage remains unchanged:

### Download and extract filesystem
```bash
pio run -t downloadfs
```

### Create factory image with filesystem
```bash
pio run -e <environment>
```

## Technical Details

### LittleFS Parameters for ESP32/ESP8266

- **Block Size**: 4096 Bytes (ESP32), 4096 Bytes (ESP8266)
- **Page Size**: 256 Bytes
- **Block Count**: Calculated from partition size

### Fallback Behavior

1. Check if `littlefs-python` is available
2. If available: Use Python implementation
3. On error or not available: Fallback to mklittlefs
4. Warning on missing installation

## Error Handling

When problems occur with littlefs-python:
- Detailed error messages with traceback
- Automatic fallback to mklittlefs
- No interruption of build process

## Testing

Tested with:
- ESP32 (various variants)
- ESP8266
- Various filesystem sizes
- Various file structures

## Known Limitations

- Maximum path length: 255 characters (LittleFS limitation)
- Block size must be a multiple of filesystem size

## Further Information

- [littlefs-python Documentation](https://littlefs-python.readthedocs.io/)
- [littlefs-python GitHub](https://github.com/jrast/littlefs-python)
- [LittleFS Project](https://github.com/littlefs-project/littlefs)
