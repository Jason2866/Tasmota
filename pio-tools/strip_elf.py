Import("env")
platform = env.PioPlatform()

board = env.BoardConfig()
mcu = board.get("build.mcu", "esp32")

# name of strip tool, differs per ESP32 type
strip_tool = "%s-elf-strip" % ("riscv32-esp" if mcu in ("esp32c2", "esp32c3", "esp32c6", "esp32h2") else ("xtensa-%s" % mcu))

# add post action to ELF
env.AddPostAction(
    "$BUILD_DIR/${PROGNAME}.elf",
    env.VerboseAction(" ".join([
        strip_tool, "$BUILD_DIR/${PROGNAME}.elf"
    ]), "Stripping $BUILD_DIR/${PROGNAME}.elf")
)