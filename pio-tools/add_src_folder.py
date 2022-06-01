import site
from os.path import join, isfile

Import("env")
env = DefaultEnvironment()

project_dir = join(env.subst("$PROJECT_DIR"))
sitepackages_dir = "".join(site.getsitepackages())
patchflag_path = join(sitepackages_dir, "platformio", "builder", "tools", ".patching-done")
original_file = join(sitepackages_dir, "platformio", "builder", "tools", "pioino.py")
patched_file = join(project_dir, "pio-tools", "patches", "1-platformio-ino-folders.patch")
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
