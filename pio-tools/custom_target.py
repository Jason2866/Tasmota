# Written by Maximilian Gerhardt <maximilian.gerhardt@rub.de>
# 29th December 2020
# and Christian Baars, Johann Obermeier
# 2023 / 2024
# License: Apache
# Expanded from functionality provided by PlatformIO's espressif32 and espressif8266 platforms, credited below.
# This script provides functions to download the filesystem (LittleFS) from a running ESP32 / ESP8266
# over the serial bootloader using esptool.py, and mklittlefs for extracting.
# run by either using the VSCode task "Custom" -> "Download Filesystem"
# or by doing 'pio run -t downloadfs' (with optional '-e <environment>') from the commandline.
# output will be saved, by default, in the "unpacked_fs" of the project.
# this folder can be changed by writing 'custom_unpack_dir = some_other_dir' in the corresponding platformio.ini
# environment.

import re
import sys
from os.path import isfile, join, basename, isdir
from enum import Enum
import os
import tasmotapiolib
import subprocess
import shutil
import json
from colorama import Fore, Back, Style

Import("env")
platform = env.PioPlatform()
board = env.BoardConfig()
mcu = board.get("build.mcu", "esp32")
IS_WINDOWS = sys.platform.startswith("win")

# --- Helper function to find a tool within PlatformIO packages ---
def _find_pio_tool(tool_name, package_name):
    """Finds a tool executable within a PlatformIO package directory."""
    tool_path = None
    try:
        package_dir = platform.get_package_dir(package_name)
        if not package_dir:
            # Fallback for older structures or potential issues
            package_dir = env.PioPlatform().get_package_dir(package_name)

        if not package_dir or not isdir(package_dir):
             raise ValueError(f"Could not find package directory for '{package_name}'.")

        # Common tool locations (check root and bin/)
        possible_paths = [
            join(package_dir, tool_name),
            join(package_dir, "bin", tool_name)
        ]
        # Add .exe for Windows
        if IS_WINDOWS:
            possible_paths.extend([p + ".exe" for p in possible_paths])

        for p in possible_paths:
            if isfile(p):
                tool_path = p
                break

        if not tool_path:
             raise ValueError(f"'{tool_name}' not found in package '{package_name}' at expected locations.")

        return tool_path

    except Exception as e:
        print(Fore.RED + f"Error finding tool '{tool_name}': {e}")
        env.Exit(1) # Exit if the tool cannot be found

# --- Locate essential tools once ---
try:
    ESPTOOL_PATH = _find_pio_tool("esptool.py", "tool-esptoolpy")
    # MKFSTOOL_NAME is needed for FS_Info, find it here too
    MKFSTOOL_NAME = env.get("MKFSTOOL") # Get the tool name from the environment
    if not MKFSTOOL_NAME:
        print(Fore.RED + "Error: MKFSTOOL environment variable not set.")
        env.Exit(1)
    MKFSTOOL_PATH = _find_pio_tool(MKFSTOOL_NAME, "tool-mklittlefs")
except Exception as e:
    # Error message already printed in _find_pio_tool, just ensure exit
    env.Exit(1)

# --- Python Executable ---
PYTHON_EXE = env.subst("$PYTHONEXE")
if not PYTHON_EXE or not isfile(PYTHON_EXE):
     print(Fore.RED + f"Error: Python executable not found at '{PYTHON_EXE}'. Check PlatformIO installation.")
     env.Exit(1)


class FSType(Enum):
    LITTLEFS="littlefs"
    FATFS="fatfs"

class FSInfo:
    def __init__(self, fs_type, start, length, page_size, block_size):
        self.fs_type = fs_type
        self.start = start
        self.length = length
        self.page_size = page_size
        self.block_size = block_size
    def __repr__(self):
        return f"FS type {self.fs_type} Start {hex(self.start)} Len {self.length} Page size {self.page_size} Block size {self.block_size}"
    # extract command supposed to be implemented by subclasses
    def get_extract_cmd(self, input_file, output_dir):
        raise NotImplementedError()

class FS_Info(FSInfo):
    def __init__(self, start, length, page_size, block_size):
        # Use the globally found MKFSTOOL_PATH
        self.tool = MKFSTOOL_PATH
        super().__init__(FSType.LITTLEFS, start, length, page_size, block_size)
    def __repr__(self):
        return f"{self.fs_type} Start {hex(self.start)} Len {hex(self.length)} Page size {hex(self.page_size)} Block size {hex(self.block_size)}"
    def get_extract_cmd(self, input_file, output_dir):
        # Ensure paths with spaces are quoted for shell execution
        # Use the full path to the tool
        return f'"{self.tool}" -b {self.block_size} -s {self.length} -p {self.page_size} --unpack "{output_dir}" "{input_file}"'

# SPIFFS helpers copied from ESP32, https://github.com/platformio/platform-espressif32/blob/develop/builder/main.py
# Copyright 2014-present PlatformIO <contact@platformio.org>
# Licensed under the Apache License, Version 2.0 (the "License");

def _parse_size(value):
    if isinstance(value, int):
        return value
    # Check if value is a string before attempting string operations
    if not isinstance(value, str):
        # Handle cases where value might not be a string as expected
        print(Fore.YELLOW + f"Warning: Unexpected type for size value: {type(value)}, value: {value}")
        return 0 # Or raise an error, depending on desired behavior
    if value.isdigit():
        return int(value)
    elif value.startswith("0x"):
        return int(value, 16)
    elif value.upper().endswith(("K", "M")): # Use endswith for safety
        base = 1024 if value.upper().endswith("K") else 1024 * 1024
        # Ensure the part before K/M is actually a number
        numeric_part = value[:-1]
        if numeric_part.isdigit():
            return int(numeric_part) * base
        else:
            print(Fore.RED + f"Error: Invalid size format '{value}'")
            env.Exit(1)
    else:
        print(Fore.RED + f"Error: Could not parse size value '{value}'")
        env.Exit(1) # Exit on unparseable size

## FS helpers for ESP8266
# copied from https://github.com/platformio/platform-espressif8266/blob/develop/builder/main.py
# Copyright 2014-present PlatformIO <contact@platformio.org>
# Licensed under the Apache License, Version 2.0 (the "License");

def _parse_ld_sizes(ldscript_path):
    if not ldscript_path or not isfile(ldscript_path):
        print(Fore.RED + f"Error: Linker script not found at '{ldscript_path}'")
        env.Exit(1)
    result = {}
    # get flash size from LD script path
    match = re.search(r"\.flash\.(\d+[mk]).*\.ld", ldscript_path, re.I) # Case-insensitive search
    if match:
        result['flash_size'] = _parse_size(match.group(1))

    # Determine the correct prefix based on framework
    fs_prefix = "FS" if "arduino" in env.subst("$PIOFRAMEWORK") else "SPIFFS"

    appsize_re = re.compile(
        r"irom0_0_seg\s*:.+len\s*=\s*(0x[\da-f]+|\d+)", flags=re.I) # Allow decimal len too
    filesystem_re = re.compile(
        r"PROVIDE\s*\(\s*_%s_(\w+)\s*=\s*(0x[\da-f]+|\d+)\s*\)" % fs_prefix,
        flags=re.I,
    )
    try:
        with open(ldscript_path) as fp:
            for line in fp: # Iterate directly over lines
                line = line.strip()
                if not line or line.startswith("/*"):
                    continue
                match = appsize_re.search(line)
                if match:
                    result['app_size'] = _parse_size(match.group(1))
                    continue # Optimization: move to next line once found
                match = filesystem_re.search(line)
                if match:
                    # Store with lowercase key for consistency
                    result['fs_%s' % match.group(1).lower()] = _parse_size(match.group(2))
    except Exception as e:
        print(Fore.RED + f"Error reading or parsing linker script '{ldscript_path}': {e}")
        env.Exit(1)

    # Basic validation
    if 'flash_size' not in result:
         print(Fore.YELLOW + f"Warning: Could not determine flash size from linker script name '{ldscript_path}'")
    if 'app_size' not in result:
         print(Fore.YELLOW + f"Warning: Could not determine app size from linker script '{ldscript_path}'")
    if not any(key.startswith('fs_') for key in result):
         print(Fore.YELLOW + f"Warning: Could not determine filesystem parameters from linker script '{ldscript_path}'")

    return result

def esp8266_fetch_fs_size(env):
    ld_script = env.GetActualLDScript()
    ldsizes = _parse_ld_sizes(ld_script)
    for key in ldsizes:
        # Use uppercase keys in env for compatibility with existing checks
        env[key.upper()] = ldsizes[key]

    # Check for required FS parameters
    required_fs_keys = ["FS_START", "FS_END", "FS_PAGE", "FS_BLOCK"]
    missing_keys = [k for k in required_fs_keys if k not in env]
    if missing_keys:
        print(Fore.RED + f"Error: Missing required filesystem parameters in linker script '{ld_script}': {', '.join(missing_keys)}")
        env.Exit(1)

    # esptool flash starts from 0
    # This address translation logic seems specific and potentially fragile.
    # Consider adding comments explaining the origin/necessity of these corrections.
    for k in ("FS_START", "FS_END"):
        _value = env[k]
        if _value < 0x40300000:
            _value = _value & 0xFFFFF
        elif _value < 0x411FB000:
            _value = (_value & 0xFFFFFF) - 0x200000  # correction
        else:
            _value = (_value & 0xFFFFFF) + 0xE00000  # correction
        env[k] = _value

## Script interface functions
def parse_partition_table(content):
    # Partition table parsing logic
    found_fs = False
    # Split by magic bytes, filter empty entries
    entries = [e for e in content.split(b'\xaa\x50') if len(e) > 0]
    #print("Partition data:") # Debug print
    for entry in entries:
        if len(entry) < 10: # Basic sanity check for entry length
            continue
        magic = entry[0] # Should be 0x50 if split correctly, but check anyway
        type = entry[1]
        subtype = entry[2] # Often used for specific FS types like SPIFFS/LittleFS
        # Check for App (0x00), Data (0x01), OTA (0x10) types
        # Subtypes for Data: SPIFFS (0x82), LittleFS (0x83), FAT (0x01)
        if type == 0x01 and subtype in [0x82, 0x83]: # Data partition, SPIFFS or LittleFS
            try:
                offset = int.from_bytes(entry[4:8], byteorder='little', signed=False) # 4 bytes offset
                size = int.from_bytes(entry[8:12], byteorder='little', signed=False)   # 4 bytes size
                # Label is often useful: label = entry[12:28].split(b'\x00', 1)[0].decode('ascii', errors='ignore')
                # print(f"Found FS Partition: Type={hex(type)}, Subtype={hex(subtype)}, Offset={hex(offset)}, Size={hex(size)}, Label={label}") # Debug
                env["FS_START"] = offset
                env["FS_SIZE"] = size
                # These are typical defaults for ESP32, might need adjustment based on actual partition table or config
                env["FS_PAGE"] = int("0x100", 16) # 256
                env["FS_BLOCK"] = int("0x1000", 16) # 4096 (standard block size for SPI flash)
                found_fs = True
                break # Assume only one FS partition is relevant for download
            except (IndexError, ValueError) as e:
                print(Fore.YELLOW + f"Warning: Could not parse partition entry: {e}, entry data: {entry.hex()}")
                continue
    if not found_fs:
        print(Fore.RED + "Error: Could not find a LittleFS or SPIFFS data partition in the partition table.")
        env.Exit(1)


def get_partition_table():
    # --- Configuration ---
    upload_port = env.get("UPLOAD_PORT", None)
    # Use a specific download speed setting if available, otherwise fallback to upload speed or default
    download_speed = env.subst(env.get("DOWNLOAD_SPEED", env.subst("$UPLOAD_SPEED")))
    if not download_speed:
        download_speed = str(board.get("download.speed", "115200")) # Board default

    # --- Port Auto-detection ---
    if not upload_port or "none" in upload_port.lower():
        print("Upload port not specified, attempting auto-detection...")
        env.AutodetectUploadPort()
        upload_port = env.get("UPLOAD_PORT", None)
        if not upload_port or "none" in upload_port.lower():
            print(Fore.RED + "Auto-detection failed. Please specify upload_port.")
            env.Exit(1)
        else:
            print(f"Detected upload port: {upload_port}")

    # --- File Path ---
    # Use build_dir for temporary files
    partition_table_file = join(env.subst("$BUILD_DIR"), "partition_table_from_flash.bin")

    # --- esptool Command ---
    # Use the globally found ESPTOOL_PATH
    esptoolpy_flags = [
            "--chip", mcu,
            "--port", upload_port,
            "--baud", download_speed,
            "--before", "default_reset", # Try to reset before connecting
            "--after", "hard_reset",    # Reset after operation
            "read_flash",
            "0x8000", # Standard offset for partition table on ESP32
            "0x1000", # Standard size to read (covers default and larger tables)
            partition_table_file
    ]
    # Use the globally found PYTHON_EXE
    esptoolpy_cmd = [PYTHON_EXE, ESPTOOL_PATH] + esptoolpy_flags

    # --- Execution ---
    print(f"Attempting to read partition table from {mcu} via {upload_port}...")
    try:
        # Use check_call for better error handling
        subprocess.check_call(esptoolpy_cmd, shell=False)
        print(Fore.GREEN + "Partition table read successfully.")
    except subprocess.CalledProcessError as e:
        print(Fore.RED + f"Error reading partition table: esptool.py exited with code {e.returncode}.")
        env.Exit(1)
    except FileNotFoundError:
        # This error is less likely now with PYTHON_EXE and ESPTOOL_PATH checked earlier
        print(Fore.RED + f"Error: Could not execute command. Check Python ('{PYTHON_EXE}') and esptool ('{ESPTOOL_PATH}') paths.")
        env.Exit(1)
    except Exception as e:
        print(Fore.RED + f"An unexpected error occurred during partition table read: {e}")
        env.Exit(1)

    # --- Parsing ---
    if not isfile(partition_table_file):
        print(Fore.RED + f"Error: Partition table file '{partition_table_file}' not found after read attempt.")
        env.Exit(1)

    try:
        with open(partition_table_file, mode="rb") as file:
            content = file.read()
        parse_partition_table(content)
    except Exception as e:
        print(Fore.RED + f"Error parsing partition table file '{partition_table_file}': {e}")
        env.Exit(1)
    finally:
        # Clean up the temporary file
        try:
            if isfile(partition_table_file):
                os.remove(partition_table_file)
        except OSError as e:
            print(Fore.YELLOW + f"Warning: Could not remove temporary partition table file '{partition_table_file}': {e}")


def get_fs_type_start_and_length():
    platform_name = env["PIOPLATFORM"]
    fs_info = None
    if platform_name == "espressif32":
        print(f"Retrieving filesystem info for {mcu} (ESP32 platform).")
        # Ensure partition table is read and parsed first
        get_partition_table()
        # Check if FS parameters were set by get_partition_table
        if all(k in env for k in ["FS_START", "FS_SIZE", "FS_PAGE", "FS_BLOCK"]):
             # Assuming LittleFS based on Tasmota's usage, might need refinement
             # if SPIFFS support is also needed here.
             print(f"Using LittleFS info from partition table: Start={hex(env['FS_START'])}, Size={hex(env['FS_SIZE'])}")
             fs_info = FS_Info(env["FS_START"], env["FS_SIZE"], env["FS_PAGE"], env["FS_BLOCK"])
        else:
             print(Fore.RED + "Error: Filesystem parameters not found after reading partition table.")
             env.Exit(1)

    elif platform_name == "espressif8266":
        print(f"Retrieving filesystem info for {mcu} (ESP8266 platform).")
        filesystem = board.get("build.filesystem", "littlefs")
        if filesystem != "littlefs":
            # Tasmota primarily uses LittleFS now. Exit if configured otherwise for download.
            print(Fore.RED + f"Error: Filesystem download currently only supports 'littlefs' for ESP8266, but found '{filesystem}'.")
            env.Exit(1)

        # Fetch sizes from linker script for ESP8266
        esp8266_fetch_fs_size(env)
        fs_start = env["FS_START"]
        fs_end = env["FS_END"]
        fs_page = env["FS_PAGE"]
        fs_block = env["FS_BLOCK"]
        fs_size = fs_end - fs_start

        if fs_size <= 0:
             print(Fore.RED + f"Error: Invalid filesystem size calculated from linker script (Start: {hex(fs_start)}, End: {hex(fs_end)}).")
             env.Exit(1)

        print(f"Using LittleFS info from linker script: Start={hex(fs_start)}, Size={hex(fs_size)}")
        fs_info = FS_Info(fs_start, fs_size, fs_page, fs_block)
    else:
        print(Fore.RED + f"Error: Unsupported platform '{platform_name}' for filesystem download.")
        env.Exit(1)

    if not fs_info:
         # This case should ideally be caught by earlier checks
         print(Fore.RED + "Error: Failed to determine filesystem information.")
         env.Exit(1)

    return fs_info


def download_fs(fs_info: FSInfo):
    print(f"Preparing to download filesystem: {fs_info}")

    # --- Configuration ---
    upload_port = env.get("UPLOAD_PORT", None)
    download_speed = env.subst(env.get("DOWNLOAD_SPEED", env.subst("$UPLOAD_SPEED")))
    if not download_speed:
        download_speed = str(board.get("download.speed", "115200"))

    # --- Port Auto-detection ---
    if not upload_port or "none" in upload_port.lower():
        print("Upload port not specified, attempting auto-detection...")
        env.AutodetectUploadPort()
        upload_port = env.get("UPLOAD_PORT", None)
        if not upload_port or "none" in upload_port.lower():
            print(Fore.RED + "Auto-detection failed. Please specify upload_port.")
            env.Exit(1)
        else:
            print(f"Detected upload port: {upload_port}")

    # --- File Path ---
    # Place downloaded image in the build directory
    fs_file = join(env.subst("$BUILD_DIR"), f"downloaded_{fs_info.fs_type.value}_{hex(fs_info.start)}_{hex(fs_info.length)}.bin")

    # --- esptool Command ---
    # Use the globally found ESPTOOL_PATH
    esptoolpy_flags = [
            "--chip", mcu,
            "--port", upload_port,
            "--baud", download_speed,
            "--before", "default_reset",
            "--after", "hard_reset",
            "read_flash",
            hex(fs_info.start),
            hex(fs_info.length),
            fs_file
    ]
    # Use the globally found PYTHON_EXE
    esptoolpy_cmd = [PYTHON_EXE, ESPTOOL_PATH] + esptoolpy_flags

    # --- Execution ---
    print(f"Attempting to download filesystem image to '{fs_file}'...")
    try:
        subprocess.check_call(esptoolpy_cmd, shell=False)
        print(Fore.GREEN + "Filesystem image downloaded successfully.")
        return (True, fs_file)
    except subprocess.CalledProcessError as e:
        print(Fore.RED + f"Error downloading filesystem: esptool.py exited with code {e.returncode}.")
        # Consider adding advice about baud rate if failure occurs
        print(Fore.YELLOW + "Tip: If download fails, try reducing 'download_speed' / 'upload_speed' in platformio.ini or override.")
        return (False, "")
    except FileNotFoundError:
        print(Fore.RED + f"Error: Could not execute command. Check Python ('{PYTHON_EXE}') and esptool ('{ESPTOOL_PATH}') paths.")
        return (False, "")
    except Exception as e:
        print(Fore.RED + f"An unexpected error occurred during filesystem download: {e}")
        return (False, "")


def unpack_fs(fs_info: FSInfo, downloaded_file: str):
    # Default unpack directory relative to project root
    default_unpack_dir = "unpacked_fs"
    # Allow override via platformio.ini
    unpack_dir_rel = env.GetProjectOption("custom_unpack_dir", default_unpack_dir)
    unpack_dir = join(env.subst("$PROJECT_DIR"), unpack_dir_rel)

    if not isfile(downloaded_file):
        print(Fore.RED + f"Error: Downloaded filesystem image '{downloaded_file}' not found. Download may have failed.")
        # Suggest checking download speed again
        print(Fore.YELLOW + "Tip: Check if the download step completed successfully and consider lowering the baud rate.")
        return (False, "") # Indicate failure clearly

    # --- Prepare Unpack Directory ---
    try:
        if os.path.exists(unpack_dir):
            print(f"Removing existing unpack directory: '{unpack_dir}'")
            shutil.rmtree(unpack_dir)
        print(f"Creating unpack directory: '{unpack_dir}'")
        os.makedirs(unpack_dir, exist_ok=True) # exist_ok=True handles race condition if dir is created between check and makedirs
    except Exception as e:
        print(Fore.RED + f"Error managing unpack directory '{unpack_dir}': {e}")
        return (False, "")

    # --- Get and Execute Unpack Command ---
    try:
        cmd = fs_info.get_extract_cmd(downloaded_file, unpack_dir)
        print(f"Attempting to unpack files using command: {cmd}")
        # Use subprocess.check_call for better error handling and output capture if needed
        # Set cwd if the tool expects to be run from a specific directory (usually not needed)
        subprocess.check_call(cmd, shell=True) # shell=True might be needed if the command uses shell features like quotes
        print(Fore.GREEN + f"Filesystem successfully unpacked to '{unpack_dir}'.")
        return (True, unpack_dir)
    except NotImplementedError:
         print(Fore.RED + f"Error: Unpack command not implemented for filesystem type {fs_info.fs_type}.")
         return (False, "")
    except subprocess.CalledProcessError as e:
        print(Fore.RED + f"Error unpacking filesystem: Command exited with code {e.returncode}.")
        # Optionally print stdout/stderr from the command if available:
        # if e.stdout: print("Stdout:", e.stdout)
        # if e.stderr: print("Stderr:", e.stderr)
        return (False, "")
    except Exception as e:
        print(Fore.RED + f"An unexpected error occurred during filesystem unpacking: {e}")
        return (False, "")


def display_fs(extracted_dir):
    if not os.path.isdir(extracted_dir):
        print(Fore.YELLOW + f"Warning: Extracted directory '{extracted_dir}' not found, cannot display summary.")
        return

    try:
        file_count = 0
        total_size = 0
        for root, dirs, files in os.walk(extracted_dir):
            file_count += len(files)
            for f in files:
                try:
                    total_size += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass # Ignore files that might disappear during walk

        print(f"Summary: Extracted {file_count} file(s) totaling {total_size} bytes into '{extracted_dir}'.")
    except Exception as e:
        print(Fore.YELLOW + f"Warning: Could not completely analyze extracted directory '{extracted_dir}': {e}")


def command_download_fs(*args, **kwargs):
    try:
        info = get_fs_type_start_and_length()
        if not info: # Should be caught earlier, but double-check
            print(Fore.RED + "Failed to get filesystem info.")
            env.Exit(1)

        download_ok, downloaded_file = download_fs(info)
        if not download_ok:
            print(Fore.RED + "Filesystem download failed. Aborting.")
            env.Exit(1)

        unpack_ok, unpacked_dir = unpack_fs(info, downloaded_file)
        if not unpack_ok:
            print(Fore.RED + "Filesystem unpacking failed. Aborting.")
            env.Exit(1)

        # Display summary only if unpacking was successful
        display_fs(unpacked_dir)
        print(Fore.GREEN + "Filesystem download and unpack process completed successfully.")

    except Exception as e:
        # Catch any unexpected errors during the overall process
        print(Fore.RED + f"An error occurred during the downloadfs command: {e}")
        env.Exit(1)

# --- Start of Updated upload_factory function ---
def upload_factory(*args, **kwargs):
    # --- Configuration Retrieval ---
    # Use env.subst to ensure we get the final resolved value from the environment
    upload_speed = env.subst("$UPLOAD_SPEED")
    # Provide a default if $UPLOAD_SPEED is not defined in the environment
    if not upload_speed:
        upload_speed = str(board.get("upload.speed", "115200")) # Default from board config

    upload_port = env.get("UPLOAD_PORT", None) # Use None as default for easier checking

    # --- Target Firmware Path ---
    try:
        # Ensure tasmotapiolib is accessible and the function works
        base_firmware_path = tasmotapiolib.get_final_bin_path(env)
        if not base_firmware_path:
             raise ValueError("tasmotapiolib.get_final_bin_path returned an empty path.")

        suffix = ".bin" if mcu == "esp8266" else ".factory.bin"
        target_firm_path = base_firmware_path.with_suffix(suffix)
        # Construct the full path using the project directory
        target_firm = join(env.subst("$PROJECT_DIR"), str(target_firm_path))

        if not isfile(target_firm):
             raise FileNotFoundError(f"Target factory firmware file not found: {target_firm}")

    except (AttributeError, FileNotFoundError, ValueError, Exception) as e:
         print(Fore.RED + f"Error determining target factory firmware path: {e}")
         # Provide more context if possible
         print(Fore.YELLOW + f"  MCU: {mcu}, Base Path Attempt: {base_firmware_path if 'base_firmware_path' in locals() else 'N/A'}")
         env.Exit(1)

    # --- Port Auto-detection ---
    if not upload_port or "none" in upload_port.lower(): # Check for None or "none"
        print("Upload port not specified, attempting auto-detection...")
        try:
            env.AutodetectUploadPort()
            upload_port = env.get("UPLOAD_PORT", None) # Re-fetch after detection
        except Exception as e:
             print(Fore.YELLOW + f"Warning: Error during port auto-detection: {e}")
             upload_port = None # Ensure it's None if detection fails

        if not upload_port or "none" in upload_port.lower():
            print(Fore.RED + "Auto-detection failed. Please specify upload_port in platformio.ini or environment.")
            env.Exit(1)
        else:
            print(f"Detected upload port: {upload_port}")

    # --- Construct esptool Command ---
    # Use the globally found ESPTOOL_PATH
    esptoolpy_flags = [
            "--chip", mcu,
            "--port", upload_port,
            "--baud", upload_speed, # Use the resolved upload_speed
            # Add common flashing options for reliability
            "--before", "default_reset", # Reset before flashing
            "--after", "hard_reset",    # Reset after flashing
            "write_flash",
            # Using '0x0' is standard for factory images, especially ESP32 .factory.bin
            "0x0",
            target_firm # The full path to the firmware file
    ]
    # Use the globally found PYTHON_EXE
    esptoolpy_cmd = [PYTHON_EXE, ESPTOOL_PATH] + esptoolpy_flags

    # --- Execute Flashing Command with Error Handling ---
    print(f"Attempting to flash factory firmware '{basename(target_firm)}' to {mcu} at address 0x0...")
    print(f"Using command: {' '.join(esptoolpy_cmd)}") # Show the command being run
    try:
        # Use subprocess.check_call to raise an error on failure
        subprocess.check_call(esptoolpy_cmd, shell=False)
        print(Fore.GREEN + "Factory firmware flashed successfully.")
    except subprocess.CalledProcessError as e:
        print(Fore.RED + f"Error during factory flashing: esptool.py exited with code {e.returncode}.")
        print(Fore.YELLOW + "Check device connection, ensure it's in bootloader mode, and verify the correct port.")
        env.Exit(1) # Exit PlatformIO script execution with an error code
    except FileNotFoundError:
        # This error usually means python_exe or esptoolpy path is wrong
        print(Fore.RED + f"Error: Could not execute command. Check Python ('{PYTHON_EXE}') and esptool ('{ESPTOOL_PATH}') paths.")
        env.Exit(1)
    except Exception as e:
        # Catch any other unexpected exceptions during the subprocess call
        print(Fore.RED + f"An unexpected error occurred during factory flashing: {e}")
        env.Exit(1)
# --- End of Updated upload_factory function ---

# --- Start of esp32_use_external_crashreport function ---
def esp32_use_external_crashreport(*args, **kwargs):
    crash_report_str = None
    try:
        # Get the raw string first
        crash_report_str = env.GetProjectOption("custom_crash_report")
        if not crash_report_str:
             print(Fore.RED + "Error: 'custom_crash_report' option is defined but empty in the environment.")
             env.Exit(1)
        # Attempt to parse as JSON
        crash_report = json.loads(crash_report_str)
    except KeyError:
        # GetProjectOption raises KeyError if the option doesn't exist
        print(Fore.RED + "Error: 'custom_crash_report' option not found in the current PlatformIO environment.")
        print(Fore.YELLOW + "Define it in platformio.ini under your [env:...] section, e.g.:")
        print(Fore.YELLOW + "custom_crash_report = '{\"StatusSTK\": {...}}'") # Show example
        env.Exit(1)
        return # Redundant after Exit, but good practice
    except json.JSONDecodeError as e:
        print(Fore.RED + f"Error: Invalid JSON in 'custom_crash_report': {e}")
        print(Fore.YELLOW + "Please use the exact JSON output from Tasmota's 'Status 12' command.")
        # Optionally print the problematic string for debugging:
        # print(Fore.YELLOW + f"Received string: {crash_report_str}")
        env.Exit(1)
        return
    except Exception as e:
         print(Fore.RED + f"An unexpected error occurred reading 'custom_crash_report': {e}")
         env.Exit(1)
         return

    print(Fore.GREEN + "Using external crash report (Status 12) for debugging:")
    # Pretty print the validated JSON
    print(Fore.CYAN + json.dumps(crash_report, sort_keys=True, indent=4))

    # --- Extract necessary info ---
    try:
        epc = crash_report['StatusSTK']['EPC']
        callchain = crash_report['StatusSTK']['CallChain']
        # Convert EPC to hex string if it's not already
        epc_hex = epc if isinstance(epc, str) and epc.startswith('0x') else hex(int(epc))
        # Convert callchain addresses to hex strings
        callchain_hex = [addr if isinstance(addr, str) and addr.startswith('0x') else hex(int(addr)) for addr in callchain]
    except (KeyError, TypeError, ValueError) as e:
        print(Fore.RED + f"Error: Could not extract required EPC or CallChain from JSON: {e}")
        print(Fore.YELLOW + "Ensure the JSON structure matches the 'Status 12' output.")
        env.Exit(1)
        return

    # --- Find addr2line ---
    addr2line = None
    toolchain_dir = None
    try:
        # Find the toolchain package directory more reliably
        # Use board.get("build.mcu", mcu) to handle cases where build.mcu might not be explicitly set
        pkg = platform.get_package("toolchain-" + board.get("build.mcu", mcu))
        if pkg:
            toolchain_dir = pkg.path
            bin_dir = join(toolchain_dir, "bin")
            if os.path.isdir(bin_dir):
                # Iterate through files in bin directory to find addr2line
                for f in os.listdir(bin_dir):
                    # Match common addr2line executable names (case-insensitive check might be safer)
                    if "addr2line" in f.lower() and not f.lower().endswith((".py", ".pyc", ".pyo")): # Avoid scripts
                        addr2line = join(bin_dir, f)
                        break # Found one

        if not addr2line:
             # Try a fallback using platform.get_tool_dir if the package method fails
             try:
                 tool_dir = platform.get_tool_dir("xtensa-%s-elf" % ("lx106" if mcu == "esp8266" else mcu)) # Adjust based on MCU if needed
                 addr2line_path_attempt = join(tool_dir, "bin", "xtensa-%s-elf-addr2line" % ("lx106" if mcu == "esp8266" else mcu))
                 if IS_WINDOWS:
                     addr2line_path_attempt += ".exe"
                 if isfile(addr2line_path_attempt):
                     addr2line = addr2line_path_attempt
                 else:
                     raise FileNotFoundError # Trigger the outer exception handler
             except: # Catch potential errors in fallback
                 raise FileNotFoundError("Could not find addr2line executable in toolchain package or via get_tool_dir.")


    except FileNotFoundError as e:
        print(Fore.RED + f"Error finding addr2line: {e}")
        print(Fore.YELLOW + f"Searched in toolchain directory: {toolchain_dir if toolchain_dir else 'Not Found'}")
        env.Exit(1)
        return
    except Exception as e:
         print(Fore.RED + f"An unexpected error occurred while searching for addr2line: {e}")
         env.Exit(1)
         return

    # --- Find ELF file ---
    try:
        # Construct path relative to build_dir
        elf_file = join(env.subst("$BUILD_DIR"), env.subst("${PROGNAME}.elf"))
        if not isfile(elf_file):
            raise FileNotFoundError(f"Firmware ELF file not found at '{elf_file}'.")
    except FileNotFoundError as e:
        print(Fore.RED + str(e))
        print(Fore.YELLOW + "Please build the current environment first (e.g., 'pio run').")
        env.Exit(1)
        return
    except Exception as e:
         print(Fore.RED + f"An unexpected error occurred finding the ELF file: {e}")
         env.Exit(1)
         return

    # --- Decode addresses ---
    print(Fore.MAGENTA + f"\nDecoding using: {addr2line}")
    print(Fore.MAGENTA + f"ELF file: {elf_file}\n")

    # Determine system encoding
    enc = sys.getdefaultencoding() if not IS_WINDOWS else "mbcs" # Use default system encoding

    try:
        # Decode EPC
        print(Fore.GREEN + "Crash location (EPC):")
        cmd_epc = [addr2line, "-e", elf_file, "-fCi", "-a", epc_hex] # Use -i for inline frames
        output_epc = subprocess.check_output(cmd_epc).decode(enc).strip()
        print(Fore.YELLOW + output_epc)

        # Decode Callchain
        print(Fore.GREEN + "\nCall Chain:")
        if not callchain_hex:
            print(Fore.YELLOW + "(Call chain is empty)")
        else:
            # Process addresses in batches for efficiency if the list is very long
            # For typical call chains, processing one by one is fine.
            cmd_callchain = [addr2line, "-e", elf_file, "-fCi", "-a"] + callchain_hex
            output_callchain = subprocess.check_output(cmd_callchain).decode(enc).strip()
            # Output is interleaved (address, function, file:line), split and format
            lines = output_callchain.splitlines()
            for i in range(0, len(lines), 3):
                 if i+2 < len(lines):
                      print(f"{Fore.YELLOW}{lines[i]}:\n  {lines[i+1]}\n  {lines[i+2]}")
                 elif i+1 < len(lines): # Handle potential incomplete triplets
                      print(f"{Fore.YELLOW}{lines[i]}:\n  {lines[i+1]}")
                 elif i < len(lines):
                      print(f"{Fore.YELLOW}{lines[i]}")


        print(Fore.CYAN + "\nNote: Decoded information is based on the current ELF file.")
        print(Fore.CYAN + "Ensure the firmware built matches the firmware that produced the crash report.")

    except subprocess.CalledProcessError as e:
        print(Fore.RED + f"Error running addr2line: Exited with code {e.returncode}")
        # Print command output if available
        if e.output: print(Fore.YELLOW + "Output:", e.output.decode(enc, errors='ignore'))
        env.Exit(1)
    except FileNotFoundError:
         print(Fore.RED + f"Error: Could not execute addr2line command. Is '{addr2line}' path correct?")
         env.Exit(1)
    except Exception as e:
        print(Fore.RED + f"An unexpected error occurred during address decoding: {e}")
        env.Exit(1)
# --- End of esp32_use_external_crashreport function ---

# --- Start of reset_target function ---
def reset_target(*args, **kwargs):
    # --- Configuration ---
    upload_port = env.get("UPLOAD_PORT", None)

    # --- Port Auto-detection ---
    if not upload_port or "none" in upload_port.lower():
        print("Upload port not specified, attempting auto-detection...")
        try:
            env.AutodetectUploadPort()
            upload_port = env.get("UPLOAD_PORT", None)
        except Exception as e:
             print(Fore.YELLOW + f"Warning: Error during port auto-detection: {e}")
             upload_port = None
        if not upload_port or "none" in upload_port.lower():
            print(Fore.RED + "Auto-detection failed. Please specify upload_port.")
            env.Exit(1)
        else:
            print(f"Detected upload port: {upload_port}")

    # --- esptool Command ---
    # Use the globally found ESPTOOL_PATH
    # Using 'flash_id' or 'chip_id' with '--no-stub' and '--after hard_reset' is a reliable way
    # to trigger the reset sequence without uploading a stub. Using flash_id as original.
    esptoolpy_flags = [
        "--no-stub",
        "--chip", mcu,
        "--port", upload_port,
        "--before", "no_reset", # Don't reset before connecting
        "--after", "hard_reset", # Hard reset after the command finishes
        "flash_id" # Use flash_id command (or chip_id if preferred)
    ]
    # Use the globally found PYTHON_EXE
    esptoolpy_cmd = [PYTHON_EXE, ESPTOOL_PATH] + esptoolpy_flags

    # --- Execution (Blocking) ---
    print(f"Attempting to reset device {mcu} via {upload_port}...")
    try:
        # Use subprocess.check_call (waits for completion) for consistency and error reporting.
        subprocess.check_call(esptoolpy_cmd, shell=False)
        print(Fore.GREEN + "Device reset command sent successfully.")
    except subprocess.CalledProcessError as e:
        # A non-zero exit code might occur if connection fails, but reset might still happen
        print(Fore.YELLOW + f"Warning: esptool.py exited with code {e.returncode} during reset attempt.")
        print(Fore.YELLOW + "Device may or may not have reset. Check device status.")
        # Don't exit here, as the goal was just to trigger a reset.
    except FileNotFoundError:
        # Handle error if python or esptool.py cannot be executed
        print(Fore.RED + f"Error: Could not execute command. Check Python ('{PYTHON_EXE}') and esptool ('{ESPTOOL_PATH}') paths.")
        env.Exit(1)
    except Exception as e:
        # Handle any other errors during process launch
        print(Fore.RED + f"An unexpected error occurred during device reset: {e}")
        env.Exit(1)
# --- End of reset_target function ---


# --- Custom Target Definitions ---

# Reset Target
env.AddCustomTarget(
    name="reset_target",
    dependencies=None, # No build dependencies needed
    actions=[
        reset_target # Use the standard blocking function
    ],
    title="Reset Target",
    description="Resets the target device using esptool.py",
)

# Download Filesystem
env.AddCustomTarget(
    name="downloadfs",
    dependencies=None, # No build dependencies needed
    actions=[
        command_download_fs # Function to execute
    ],
    title="Download Filesystem",
    description="Downloads, unpacks, and displays files from the target filesystem"
)

# Flash Factory Firmware
env.AddCustomTarget(
    name="factory_flash",
    dependencies=None,
    actions=[
        upload_factory # Use the updated function
    ],
    title="Flash Factory Firmware",
    description="Flashes the appropriate factory firmware (.bin or .factory.bin) at address 0x0"
)

# Decode External Crash Report
env.AddCustomTarget(
    name="external_crashreport",
    dependencies=None, # Does depend on the ELF file existing, but checked internally
    actions=[
        esp32_use_external_crashreport # Function to execute
    ],
    title="Decode External Crash Report",
    description="Decodes ESP32 crash info using 'Status 12' JSON output and the current ELF file"
)
