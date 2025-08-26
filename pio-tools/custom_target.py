# Written by Maximilian Gerhardt <maximilian.gerhardt@rub.de>
# 29th December 2020
# and Christian Baars, Johann Obermeier
# 2023 / 2024
# License: Apache
#
# Expanded from functionality provided by PlatformIO's espressif32 and espressif8266 platforms
#
# This script provides functions to download the filesystem (LittleFS) from a running ESP32 / ESP8266
# over the serial bootloader using esptool.py, and mklittlefs for extracting.
#
# Run by either using the VSCode task:
#   "Custom" -> "Download Filesystem"
# or by doing:
#   pio run -t downloadfs
# (with optional '-e <environment>') from the commandline.
#
# Output will be saved, by default, in the "unpacked_fs" directory of the project.
# This folder can be changed by writing:
#   custom_unpack_dir = some_other_dir
# in the corresponding platformio.ini environment.

import re
import sys
from pathlib import Path
from enum import Enum
import tasmotapiolib
import subprocess
import shutil
import json
from colorama import Fore, Style
from platformio.compat import IS_WINDOWS
from platformio.project.config import ProjectConfig

Import("env")  # Load PlatformIO build environment

platform = env["PIOPLATFORM"]
board = env.BoardConfig()
mcu = board.get("build.mcu", "esp32").lower()


class FSType(Enum):
    LITTLEFS = "littlefs"
    FATFS = "fatfs"


class FSInfo:
    """
    Base class for filesystem info storage.
    """

    def __init__(self, fs_type, start, length, page_size, block_size):
        self.fs_type = fs_type
        self.start = start
        self.length = length
        self.page_size = page_size
        self.block_size = block_size

    def __repr__(self):
        return (
            f"FS type {self.fs_type} Start {hex(self.start)} "
            f"Len {self.length} Page size {self.page_size} Block size {self.block_size}"
        )

    # Extract command supposed to be implemented by subclasses
    def get_extract_cmd(self, input_file, output_dir):
        raise NotImplementedError()


class FS_Info(FSInfo):
    """
    Filesystem info for LittleFS, includes mklittlefs tool path and extract command
    """

    def __init__(self, start, length, page_size, block_size):
        self.tool = env["MKFSTOOL"]
        packages_dir = Path(ProjectConfig.get_instance().get("platformio", "packages_dir"))
        self.tool = packages_dir / "tool-mklittlefs" / self.tool
        super().__init__(FSType.LITTLEFS, start, length, page_size, block_size)

    def __repr__(self):
        return (
            f"{self.fs_type} Start {hex(self.start)} Len {hex(self.length)} "
            f"Page size {hex(self.page_size)} Block size {hex(self.block_size)}"
        )

    def get_extract_cmd(self, input_file, output_dir):
        return (
            f'"{self.tool}" -b {self.block_size} -s {self.length} '
            f'-p {self.page_size} --unpack "{output_dir}" "{input_file}"'
        )


def _parse_size(value):
    """
    Convert size strings like "4K", "2M", "0x1000" into integer sizes.
    """
    if isinstance(value, int):
        return value
    elif value.isdigit():
        return int(value)
    elif value.startswith("0x"):
        return int(value, 16)
    elif value[-1].upper() in ("K", "M"):
        base = 1024 if value[-1].upper() == "K" else 1024 * 1024
        return int(value[:-1]) * base
    return value


def _parse_ld_sizes(ldscript_path):
    """
    Parse the linker script (.ld) to extract flash size, app size and FS regions.
    """
    ld_path = Path(ldscript_path)
    result = {}

    # Get flash size from LD script filename
    match = re.search(r"\.flash\.(\d+[mk]).*\.ld", ld_path.name)
    if match:
        result["flash_size"] = _parse_size(match.group(1))

    appsize_re = re.compile(r"irom0_0_seg\s*:.+len\s*=\s*(0x[\da-f]+)", flags=re.I)

    # Arduino linker script defines PROVIDE(_FS_start=...)
    filesystem_re = re.compile(
        r"PROVIDE\s*\(\s*_%s_(\w+)\s*=\s*(0x[\da-f]+)\s*\)" % "FS"
        if "arduino" in env.subst("$PIOFRAMEWORK")
        else "SPIFFS",
        flags=re.I,
    )

    with ld_path.open() as fp:
        for line in fp:
            line = line.strip()
            if not line or line.startswith("/*"):
                continue
            m = appsize_re.search(line)
            if m:
                result["app_size"] = _parse_size(m.group(1))
                continue
            m = filesystem_re.search(line)
            if m:
                result[f"fs_{m.group(1)}"] = _parse_size(m.group(2))

    return result


def esp8266_fetch_fs_size(env):
    """
    Extract filesystem region (start, end, page, block) for ESP8266
    by parsing the actual linker script used.
    """
    ldsizes = _parse_ld_sizes(env.GetActualLDScript())
    for key in ldsizes:
        if key.startswith("fs_"):
            env[key.upper()] = ldsizes[key]

    assert all(k in env for k in ["FS_START", "FS_END", "FS_PAGE", "FS_BLOCK"])

    # esptool flash addresses start from 0.
    # Apply corrections based on memory regions.
    for k in ("FS_START", "FS_END"):
        if env[k] < 0x40300000:
            env[k] = env[k] & 0xFFFFF
        elif env[k] < 0x411FB000:
            env[k] = (env[k] & 0xFFFFFF) - 0x200000
        else:
            env[k] = (env[k] & 0xFFFFFF) + 0xE00000


def switch_off_ldf():
    """
    Configure `lib_ldf_mode = off` for pre-script execution.
    This avoids the time consuming library dependency resolution phase
    when one of the optimized custom targets is run.
    """
    optimized_targets = ["reset_target", "downloadfs", "factory_flash", "metrics-only"]
    argv_string = " ".join(sys.argv)
    is_optimized_targets = any(target in argv_string for target in optimized_targets)

    if is_optimized_targets:
        projectconfig = env.GetProjectConfig()
        env_section = "env:" + env["PIOENV"]
        if not projectconfig.has_section(env_section):
            projectconfig.add_section(env_section)
        projectconfig.set(env_section, "lib_ldf_mode", "off")


switch_off_ldf()


def parse_partition_table(content):
    """
    Parse binary partition table data (ESP32) and extract FS offsets.
    """
    entries = [e for e in content.split(b"\xaaP") if len(e) > 0]
    for entry in entries:
        type = entry[1]
        if type in [0x82, 0x83]:
            offset = int.from_bytes(entry[2:5], "little", signed=False)
            size = int.from_bytes(entry[6:9], "little", signed=False)
            env["FS_START"] = offset
            env["FS_SIZE"] = size
            env["FS_PAGE"] = 0x100
            env["FS_BLOCK"] = 0x1000


def get_partition_table():
    """
    Download the partition table (ESP32) via esptool and extract FS region.
    """
    upload_port = env.get("UPLOAD_PORT", "none")
    download_speed = str(board.get("download.speed", "115200"))

    # Autodetect port if not set
    if "none" in upload_port:
        env.AutodetectUploadPort()
        upload_port = env.get("UPLOAD_PORT", "none")
        build_dir = Path(env.subst("$BUILD_DIR"))
        build_dir.mkdir(parents=True, exist_ok=True)

    fs_file = Path(env.subst("$BUILD_DIR")) / "partition_table_from_flash.bin"

    esptool_flags = [
        "--chip",
        mcu,
        "--port",
        upload_port,
        "--baud",
        download_speed,
        "--before",
        "default-reset",
        "--after",
        "hard-reset",
        "read-flash",
        "0x8000",
        "0x1000",
        str(fs_file),
    ]
    ESPTOOL_EXE = env.get("ERASETOOL") if platform == "espressif8266" else env.get("OBJCOPY")
    esptool_cmd = [ESPTOOL_EXE] + esptool_flags
    try:
        subprocess.call(esptool_cmd, shell=False)
    except subprocess.CalledProcessError as exc:
        print("Downloading failed with " + str(exc))

    parse_partition_table(fs_file.read_bytes())


def get_fs_type_start_and_length():
    """
    Determine filesystem type, start and length for ESP32 / ESP8266 devices.
    """
    if platform == "espressif32":
        print(f"Retrieving filesystem info for {mcu}.")
        get_partition_table()
        return FS_Info(env["FS_START"], env["FS_SIZE"], env["FS_PAGE"], env["FS_BLOCK"])
    elif platform == "espressif8266":
        print("Retrieving filesystem info for ESP8266.")
        filesystem = board.get("build.filesystem", "littlefs")
        if filesystem not in ("littlefs"):
            print(f"Unrecognized board_build.filesystem option '{filesystem}'.")
            env.Exit(1)
        esp8266_fetch_fs_size(env)
        if filesystem == "littlefs":
            print("Recognized LittleFS filesystem.")
            return FS_Info(env["FS_START"], env["FS_END"] - env["FS_START"], env["FS_PAGE"], env["FS_BLOCK"])


def download_fs(fs_info: FSInfo):
    """
    Download the filesystem binary image from the device using esptool.
    """
    print(fs_info)
    upload_port = env.get("UPLOAD_PORT", "none")
    download_speed = str(board.get("download.speed", "115200"))
    if "none" in upload_port:
        env.AutodetectUploadPort()
        upload_port = env.get("UPLOAD_PORT", "none")

    fs_file = Path(env.subst("$BUILD_DIR")) / f"downloaded_fs_{hex(fs_info.start)}_{hex(fs_info.length)}.bin"
    esptool_flags = [
        "--chip",
        mcu,
        "--port",
        upload_port,
        "--baud",
        download_speed,
        "--before",
        "default-reset",
        "--after",
        "hard-reset",
        "read-flash",
        hex(fs_info.start),
        hex(fs_info.length),
        str(fs_file),
    ]
    ESPTOOL_EXE = env.get("ERASETOOL") if platform == "espressif8266" else env.get("OBJCOPY")
    esptool_cmd = [ESPTOOL_EXE] + esptool_flags
    print("Download filesystem image")
    try:
        subprocess.call(esptool_cmd, shell=False)
        return (True, fs_file)
    except subprocess.CalledProcessError as exc:
        print("Downloading failed with " + str(exc))
        return (False, "")


def unpack_fs(fs_info: FSInfo, downloaded_file: Path):
    """
    Unpack the filesystem binary into a folder using mklittlefs.
    """
    unpack_dir = Path(env.GetProjectOption("custom_unpack_dir", "unpacked_fs"))
    current_build_dir = Path(env.subst("$BUILD_DIR"))
    filename = f"downloaded_fs_{hex(fs_info.start)}_{hex(fs_info.length)}.bin"
    downloaded_file = current_build_dir / filename

    if not downloaded_file.exists():
        print(f"ERROR: {downloaded_file} not found, maybe download failed due to speed.")
        env.Exit(1)

    # Clean and recreate unpack_dir
    if unpack_dir.exists():
        shutil.rmtree(unpack_dir)
    unpack_dir.mkdir(parents=True, exist_ok=True)

    cmd = fs_info.get_extract_cmd(downloaded_file, unpack_dir)
    print("Unpack files from filesystem image")
    try:
        subprocess.call(cmd, shell=True)
        return (True, unpack_dir)
    except subprocess.CalledProcessError as exc:
        print("Unpacking filesystem failed with " + str(exc))
        return (False, "")


def display_fs(extracted_dir: Path):
    """
    Display a summary of number of files extracted.
    """
    file_count = sum(len(files) for _, _, files in os.walk(extracted_dir))
    print(f"Extracted {file_count} file(s) from filesystem.")


def command_download_fs(*args, **kwargs):
    """
    Command target: download filesystem, unpack it and display summary.
    """
    info = get_fs_type_start_and_length()
    download_ok, downloaded_file = download_fs(info)
    if download_ok:
        unpack_ok, unpacked_dir = unpack_fs(info, downloaded_file)
        if unpack_ok:
            display_fs(unpacked_dir)


def upload_factory(*args, **kwargs):
    """
    Upload the factory firmware image directly to flash address 0x0.
    """
    upload_port = env.get("UPLOAD_PORT", "none")
    if "none" in upload_port:
        env.AutodetectUploadPort()
        upload_port = env.get("UPLOAD_PORT", "none")

    target_firm = Path(env.subst("$PROJECT_DIR")) / tasmotapiolib.get_final_bin_path(env)
    target_firm = target_firm.with_suffix(".bin" if mcu == "esp8266" else ".factory.bin")

    if "tasmota" in target_firm.name:
        esptool_flags = [
            "--chip",
            mcu,
            "--port",
            upload_port,
            "--baud",
            env.subst("$UPLOAD_SPEED"),
            "write-flash",
            "0x0",
            str(target_firm),
        ]
        ESPTOOL_EXE = env.get("ERASETOOL") if platform == "espressif8266" else env.get("OBJCOPY")
        esptool_cmd = [ESPTOOL_EXE] + esptool_flags
        print("Flash firmware at address 0x0")
        subprocess.call(esptool_cmd, shell=False)


def esp32_use_external_crashreport(*args, **kwargs):
    """
    Decode an external crash report (STATUS 12 output from Tasmota)
    using addr2line and the firmware ELF file.
    """
    try:
        crash_report = env.GetProjectOption("custom_crash_report")
    except:
        print(Fore.RED + "Did not find custom_crash_report section!!")
        return
    try:
        crash_report = json.loads(crash_report)
    except:
        print(Fore.RED + "No valid JSON, please use output of STATUS 12 in the console!!")
        return

    print(Fore.GREEN + "Use external crash report (STATUS 12) for debugging:\n" + json.dumps(crash_report, sort_keys=True, indent=4))
    epc = crash_report["StatusSTK"]["EPC"]
    callchain = crash_report["StatusSTK"]["CallChain"]

    # Locate addr2line tool from toolchain
    addr2line = ""
    for p in platform.get_installed_packages():
        if "toolchain" in p.path:
            bin_dir = Path(p.path) / "bin"
            for f in bin_dir.iterdir():
                if "addr2line" in f.name:
                    addr2line = str(f)

    elf_file = Path(env.subst("$BUILD_DIR")) / env.subst("${PROGNAME}.elf")
    if not elf_file.exists():
        print(Fore.RED + "Did not find firmware.elf ... build first!!")
        return

    enc = "mbcs" if IS_WINDOWS else "utf-8"
    output = (
        subprocess.check_output([addr2line, "-e", elf_file, "-fC", "-a", epc])
        .decode(enc)
        .strip()
        .splitlines()
    )
    print(Fore.YELLOW + "No way to check if this data is valid!!")
    print(Fore.GREEN + "Crash at:")
    print(Fore.YELLOW + f"{output[0]}:\n{output} in {output}")

    print(Fore.GREEN + "Callchain:")
    for call in callchain:
        output = (
            subprocess.check_output([addr2line, "-e", elf_file, "-fC", "-a", call])
            .decode(enc)
            .strip()
            .splitlines()
        )
        print(Fore.YELLOW + f"{output[0]}:\n{output} in {output}")


def reset_target(*args, **kwargs):
    """
    Reset the target device using esptool flash-id command.
    """
    upload_port = env.get("UPLOAD_PORT", "none")
    if "none" in upload_port:
        env.AutodetectUploadPort()
        upload_port = env.get("UPLOAD_PORT", "none")

    esptool_flags = ["--no-stub", "--chip", mcu, "--port", upload_port, "flash-id"]
    ESPTOOL_EXE = env.get("ERASETOOL") if platform == "espressif8266" else env.get("OBJCOPY")
    esptool_cmd = [ESPTOOL_EXE] + esptool_flags
    print("Try to reset device")
    subprocess.call(esptool_cmd, shell=False)


# Custom Target Definitions
# These targets can be run via `pio run -t <name>`.
env.AddCustomTarget(
    name="reset_target",
    dependencies=None,
    actions=[reset_target],
    title="Reset connected device",
    description="Reset the connected device via esptool",
)

env.AddCustomTarget(
    name="downloadfs",
    dependencies=None,
    actions=[command_download_fs],
    title="Download Filesystem",
    description="Download and display files from the ESP filesystem",
)

env.AddCustomTarget(
    name="factory_flash",
    dependencies=None,
    actions=[upload_factory],
    title="Flash factory",
    description="Flash factory firmware",
)

env.AddCustomTarget(
    name="external_crashreport",
    dependencies=None,
    actions=[esp32_use_external_crashreport],
    title="External crash report",
    description="Use external crashreport output from Tasmota (STATUS 12)",
)
