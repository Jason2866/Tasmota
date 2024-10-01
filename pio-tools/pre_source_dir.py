Import("env")

import glob
import os
import os.path
from os.path import join
import shutil

platform = env.PioPlatform()
board = env.BoardConfig()

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
