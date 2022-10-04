import site
from os.path import join, isfile

Import("env")

env = DefaultEnvironment()
platform = env.PioPlatform()

project_dir = join(env.subst("$PROJECT_DIR"))
platforms_dir = join(env.subst("$PROJECT_CORE_DIR"), "platforms")

patchflag_path = join(platforms_dir, "espressif32", "builder", ".patching-done")
original_file = join(platforms_dir, "espressif32", "builder", "main.py")
patched_file = join(project_dir, "pio-tools", "patches", "1-platformio-esp32-offset.patch")
#print("original_file", original_file)
#print("patched_file", patched_file)

# patch file only if we didn't do it before
if not isfile(patchflag_path):
    isfile(original_file) and isfile(patched_file)
    env.Execute("patch %s %s" % (original_file, patched_file))
    # env.Execute("touch " + patchflag_path)


    def _touch(path):
        with open(path, "w") as fp:
            fp.write("")

    env.Execute(lambda *args, **kwargs: _touch(patchflag_path))
