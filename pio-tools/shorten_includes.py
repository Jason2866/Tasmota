import os

from platformio import fs

Import("env")

platform = env.PioPlatform()

FRAMEWORK_DIR = fs.to_unix_path(
    platform.get_package_dir("framework-arduinoespressif32")
)

IS_INTEGRATION_DUMP = env.IsIntegrationDump()

def shorten_includes(env, node):
    if IS_INTEGRATION_DUMP:
       # Don't shorten include paths for IDE integrations
       return node
       
    includes = [fs.to_unix_path(inc) for inc in env.get("CPPPATH", [])]
    shortened_includes = []
    generic_includes = []
    for inc in includes:
        if inc.startswith(FRAMEWORK_DIR):
            shortened_includes.append(
                "-iwithprefix/"
                + fs.to_unix_path(os.path.relpath(inc, FRAMEWORK_DIR))
            )
        else:
            generic_includes.append(inc)
 
    return env.Object(
        node,
        CPPPATH=generic_includes,
        CCFLAGS=env["CCFLAGS"] + ["-iprefix", FRAMEWORK_DIR] + shortened_includes
    )

env.AddBuildMiddleware(shorten_includes)
