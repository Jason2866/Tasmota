Import("env")
platform = env.PioPlatform()

import shutil
import pathlib
import tasmotapiolib
from os.path import join


def bin_map_copy(source, target, env):
    firsttarget = pathlib.Path(target[0].path)

    # get locations and file names based on variant
    map_file = tasmotapiolib.get_final_map_path(env)
    bin_file = tasmotapiolib.get_final_bin_path(env)

    if env["PIOPLATFORM"] == "espressif32":
        factory_tmp = pathlib.Path(firsttarget).with_suffix("")
        factory = factory_tmp.with_suffix(factory_tmp.suffix + ".factory.bin")
        one_bin_tmp = pathlib.Path(bin_file).with_suffix("")
        one_bin_file = one_bin_tmp.with_suffix(one_bin_tmp.suffix + ".factory.bin")

    # check if new target files exist and remove if necessary
    for f in [map_file, bin_file]:
        if f.is_file():
            f.unlink()

    # copy firmware.bin and map to final destination
    shutil.copy(firsttarget, bin_file)
    shutil.move(tasmotapiolib.get_source_map_path(env), map_file)
    if env["PIOPLATFORM"] == "espressif32":
        shutil.copy(factory, one_bin_file)

        board = env.BoardConfig()
        upload_speed = join(str(board.get("upload.speed", "115200")))
        mcu = board.get("build.mcu", "esp32")
        env.AutodetectUploadPort()
        upload_port = join(env.get("UPLOAD_PORT"))
        python_exe = join(env["PYTHONEXE"])
        esptool = join(platform.get_package_dir("tool-esptoolpy") or "", "esptool.py")
        factory_image = join(one_bin_file)
        cmd_factory_flash = python_exe + " " + esptool + " --chip " + mcu + " --port " + upload_port + " --baud " + upload_speed + " write_flash 0x0 " + factory_image
        print ("UploadCmd: ", cmd_factory_flash)
        env["INTEGRATION_EXTRA_DATA"].update({"cmd_factory_flash": cmd_factory_flash})
        #integr_data = env.get("INTEGRATION_EXTRA_DATA")
        #cmd_flash_data = integr_data.get("cmd_factory_flash", "")
        cmd_flash_data = env.get("INTEGRATION_EXTRA_DATA").get("cmd_factory_flash", "")
        print ("INTEGRATION_EXTRA_DATA: ", cmd_flash_data)

env.AddCustomTarget(
    name="pioenv",
    dependencies=None,
    actions=[
        env.get("INTEGRATION_EXTRA_DATA").get("cmd_factory_flash", "")
    ],
    title="Core Env",
    description="Show PlatformIO Core and Python versions"
)

env.AddPostAction("$BUILD_DIR/${PROGNAME}.bin", bin_map_copy)
