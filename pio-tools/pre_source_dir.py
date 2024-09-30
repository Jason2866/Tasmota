Import("env")

import glob
import os
import os.path
from os.path import join
import shutil

platform = env.PioPlatform()
board = env.BoardConfig()
mcu = board.get("build.mcu", "esp32")

extra_flags = ''.join([element.replace("-D", " ") for element in board.get("build.extra_flags", "")])
build_flags = ''.join([element.replace("-D", " ") for element in env.GetProjectOption("build_flags")])

if ("CORE32SOLO1" in extra_flags or "FRAMEWORK_ARDUINO_SOLO1" in build_flags):
    FRAMEWORK_DIR = platform.get_package_dir("framework-arduino-solo1")
elif ("CORE32ITEAD" in extra_flags or "FRAMEWORK_ARDUINO_ITEAD" in build_flags):
    FRAMEWORK_DIR = platform.get_package_dir("framework-arduino-ITEAD")
else:
    FRAMEWORK_DIR = platform.get_package_dir("framework-arduinoespressif32")

def FindInoNodes(env):
    src_dir = glob.escape(env.subst("$PROJECT_SRC_DIR"))
    return env.Glob(os.path.join(src_dir, "*.ino")) + env.Glob(
        os.path.join(src_dir, "tasmota_*", "*.ino")
    )

env.AddMethod(FindInoNodes)

# Pass flashmode at build time to macro
memory_type = board.get("build.arduino.memory_type", "").upper()
flash_mode = board.get("build.flash_mode", "dio").upper()
if "OPI_" in memory_type:
    flash_mode = "OPI"

tasmota_flash_mode = "-DCONFIG_TASMOTA_FLASHMODE_" + flash_mode
env.Append(CXXFLAGS=[tasmota_flash_mode])
print(tasmota_flash_mode)

#
# Arduino as an component compile
#
try:
    if env.GetProjectOption("custom_sdkconfig").splitlines():
        env["PIOFRAMEWORK"].append("espidf")
except:
    pass
