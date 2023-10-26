Import("env")
env = DefaultEnvironment()
platform = env.PioPlatform()


import glob
import os
import shutil
from os.path import join

def FindInoNodes(env):
    src_dir = glob.escape(env.subst("$PROJECT_SRC_DIR"))
    return env.Glob(os.path.join(src_dir, "*.ino")) + env.Glob(
        os.path.join(src_dir, "tasmota_*", "*.ino")
    )

env.AddMethod(FindInoNodes)

# Pass flashmode at build time to macro
tasmota_flash_mode = "-DCONFIG_TASMOTA_FLASHMODE_" + (env.BoardConfig().get("build.flash_mode", "dio")).upper()
env.Append(CXXFLAGS=[tasmota_flash_mode])
print(tasmota_flash_mode)

if env["PIOPLATFORM"] == "espressif32":
    # Copy pins_arduino.h to variants folder
    board_config = env.BoardConfig()
    mcu_build_variant = board_config.get("build.variant", "").lower()
    variants_dir = board_config.get("build.variants_dir", "")
    FRAMEWORK_DIR = platform.get_package_dir("framework-arduinoespressif32")
    mcu_build_variant_path = join(FRAMEWORK_DIR, "variants", mcu_build_variant, "pins_arduino.h")
    custom_variant_build = join(env.subst("$PROJECT_DIR"), variants_dir , mcu_build_variant, "pins_arduino.h")
    print("mcu_build_variant_path: ", mcu_build_variant_path)
    print("custom_variant_build: ", custom_variant_build)
    shutil.copy(mcu_build_variant_path, custom_variant_build)