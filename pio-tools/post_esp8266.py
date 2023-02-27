
env = DefaultEnvironment()
platform = env.PioPlatform()

from genericpath import exists
import os

from os.path import join
import requests
import shutil
import subprocess


FRAMEWORK_DIR = platform.get_package_dir("framework-arduinoespressif8266")


def esp8266_build_filesystem(fs_size):
    files = env.GetProjectOption("custom_files_upload").splitlines()
    filesystem_dir = join(env.subst("$BUILD_DIR"),"littlefs_data")
    if not os.path.exists(filesystem_dir):
        os.makedirs(filesystem_dir)
    print("Creating filesystem with content:")
    for file in files:
        if "no_files" in file:
            continue
        if "http" and "://" in file:
            response = requests.get(file)
            if response.ok:
                target = join(filesystem_dir,file.split(os.path.sep)[-1])
                open(target, "wb").write(response.content)
            else:
                print("Failed to download: ",file)
            continue
        shutil.copy(file, filesystem_dir)
    if not os.listdir(filesystem_dir):
        print("No files added -> will NOT create littlefs.bin and NOT overwrite fs partition!")
        return False
    env.Replace( MKSPIFFSTOOL=platform.get_package_dir("tool-mklittlefs") + '/mklittlefs' )
    tool = env.subst(env["MKSPIFFSTOOL"])
    cmd = (tool,"-c",filesystem_dir,"-s",fs_size,join(env.subst("$BUILD_DIR"),"littlefs.bin"))
    returncode = subprocess.call(cmd, shell=False)
    # print(returncode)
    return True


env.AddPostAction("$BUILD_DIR/${PROGNAME}.bin", esp8266_build_filesystem)
