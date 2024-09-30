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

print("Platform dir", os.path.join(env.subst("$PROJECT_CORE_DIR"), "platforms"))

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
#########################################################

def HandleArduinoIDFbuild(env, idf_config_flags):
    print("IDF build!")
    # Dump build environment (for debug)
    # print(env.Dump())
    if mcu in ("esp32", "esp32s2", "esp32s3"):
        env["BUILD_FLAGS"].append("-mtext-section-literals") # TODO

    #arduino_libs_mcu = join(FRAMEWORK_DIR,"tools","esp32-arduino-libs",mcu)
    #lib_backup_folder = "lib_backup"
    #if lib_backup_folder not in os.listdir(arduino_libs_mcu):
        #destination = shutil.copytree(join(arduino_libs_mcu,"lib"), join(arduino_libs_mcu,lib_backup_folder), copy_function = shutil.copy)

    sdkconfig_src = join(FRAMEWORK_DIR,"tools","esp32-arduino-libs",mcu,"sdkconfig")

    def get_flag(line):
        if line.startswith("#") and "is not set" in line:
            return line.split(" ")[1]
        elif not line.startswith("#") and len(line.split("=")) > 1:
            return line.split("=")[0]
        else:
            return None

    with open(sdkconfig_src) as src:
        sdkconfig_dst = join(env.subst("$PROJECT_DIR"),"sdkconfig.defaults")
        dst = open(sdkconfig_dst,"w")
        dst.write("# TASMOTA\n")
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

    # print("Use sdkconfig from Arduino libs as default")
    # print(sdkconfig_src,sdkconfig_dst)
    # shutil.copy(sdkconfig_src,sdkconfig_dst) # TODO: maybe no rude overwrite
    # assert(0)

    EXTRA_IMG_DIR = join(env.subst("$PROJECT_DIR"), "variants", "tasmota")
    env.Append(
        FLASH_EXTRA_IMAGES=[
            (offset, join(EXTRA_IMG_DIR, img)) for offset, img in board.get("upload.arduino.flash_extra_images", [])
        ]
    )

def esp32_copy_new_arduino_libs(target, source, env):
    print("Will copy new Arduino libs to .platformio")
    lib_src = join(env["PROJECT_BUILD_DIR"],env["PIOENV"],"esp-idf")
    lib_dst = join(FRAMEWORK_DIR,"tools","esp32-arduino-libs",mcu,"lib")
    src = [join(lib_src,x) for x in os.listdir(lib_src)]
    src = [folder for folder in src if not os.path.isfile(folder)] # folders only
    for folder in src:
        # print(folder)
        files = [join(folder,x) for x in os.listdir(folder)]
        for file in files:
            if file.strip().endswith(".a"):
                # print(file.split("/")[-1])
                shutil.copyfile(file,join(lib_dst,file.split("/")[-1]))
    if not bool(os.path.isfile(join(FRAMEWORK_DIR,"tools","esp32-arduino-libs",mcu,"sdkconfig.orig"))):
        shutil.move(join(FRAMEWORK_DIR,"tools","esp32-arduino-libs",mcu,"sdkconfig"),join(FRAMEWORK_DIR,"tools","esp32-arduino-libs",mcu,"sdkconfig.orig"))
    shutil.copyfile(join(env.subst("$PROJECT_DIR"),"sdkconfig."+env["PIOENV"]),join(FRAMEWORK_DIR,"tools","esp32-arduino-libs",mcu,"sdkconfig"))
    exit() # TODO Post action in pre script!


try:
    if idf_config_flags := env.GetProjectOption("custom_sdkconfig").splitlines():
        env["PIOFRAMEWORK"].append("espidf")
        HandleArduinoIDFbuild(env, idf_config_flags)
        env.AddPostAction("$BUILD_DIR/${PROGNAME}.bin", esp32_copy_new_arduino_libs) # TODO Post action in pre script!
except:
    pass
    # arduino_libs_mcu = join(FRAMEWORK_DIR,"tools","esp32-arduino-libs",mcu)
    # lib_backup_folder = "lib_backup"
    # if lib_backup_folder in os.listdir(arduino_libs_mcu):
    #     shutil.rmtree(join(arduino_libs_mcu,"lib"))
    #     destination = shutil.copytree(join(arduino_libs_mcu,lib_backup_folder),join(arduino_libs_mcu,"lib"), copy_function = shutil.copy)
    #     shutil.rmtree(join(arduino_libs_mcu,lib_backup_folder))

