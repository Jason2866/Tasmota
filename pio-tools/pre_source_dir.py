Import("env")

import glob
import os
from os.path import join
import shutil

def FindInoNodes(env):
    src_dir = glob.escape(env.subst("$PROJECT_SRC_DIR"))
    return env.Glob(os.path.join(src_dir, "*.ino")) + env.Glob(
        os.path.join(src_dir, "tasmota_*", "*.ino")
    )

env.AddMethod(FindInoNodes)

def HandleArduinoIDFbuild(env):
    print("IDF build!!!, removing LTO")
    new_build_flags = [f for f in env["BUILD_FLAGS"] if "-flto=auto" not in f]
    # new_build_flags.append("-mtext-section-literals") # TODO C2 fails
    env["BUILD_FLAGS"] = new_build_flags
    print(new_build_flags)

    platform = env.PioPlatform()
    board = env.BoardConfig()
    mcu = board.get("build.mcu", "esp32")
    sdkconfig_src = join(platform.get_package_dir("framework-arduinoespressif32"),"tools","esp32-arduino-libs",mcu,"sdkconfig")

    def get_flag(line):
        if line.startswith("#") and "is not set" in line:
            return line.split(" ")[1]
        elif not line.startswith("#") and len(line.split("=")) > 1:
            return line.split("=")[0]
        else:
            return None

    idf_config_flags = env.GetProjectOption("custom_sdkconfig").splitlines()
    with open(sdkconfig_src) as src:
        sdkconfig_dst = join(env.subst("$PROJECT_DIR"),"sdkconfig.defaults")
        dst = open(sdkconfig_dst,"w")
        while line := src.readline():
            flag = get_flag(line)
            # print(flag)
            if flag is None:
                dst.write(line)
            else:
                no_match = True
                for item in idf_config_flags:
                    if flag in item:
                        dst.write(item+"\n")
                        no_match = False
                        print("Replace:",line," with: ",item)
                if no_match:
                    dst.write(line)
        dst.close()

    print("Use sdkconfig from Arduino libs as default")
    print(sdkconfig_src,sdkconfig_dst)
    # shutil.copy(sdkconfig_src,sdkconfig_dst) # TODO: maybe no rude overwrite
    # assert(0)

# Pass flashmode at build time to macro
memory_type = env.BoardConfig().get("build.arduino.memory_type", "").upper()
flash_mode = env.BoardConfig().get("build.flash_mode", "dio").upper()
if "OPI_" in memory_type:
    flash_mode = "OPI"

tasmota_flash_mode = "-DCONFIG_TASMOTA_FLASHMODE_" + flash_mode
env.Append(CXXFLAGS=[tasmota_flash_mode])
print(tasmota_flash_mode)

try:
    if env.GetProjectOption("custom_sdkconfig").splitlines():
        env["PIOFRAMEWORK"].append("espidf")
        HandleArduinoIDFbuild(env)
except:
    pass
