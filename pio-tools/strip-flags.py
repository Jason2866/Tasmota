Import('env')

link_flags = env['LINKFLAGS']
build_flags = " ".join(env['BUILD_FLAGS'])

link_flags = link_flags.replace("-u _printf_float", "")
link_flags = link_flags.replace("-u _scanf_float", "")

if "FIRMWARE_SAFEBOOT" in build_flags:
  # Crash Recorder is not included in safeboot firmware -> remove Linker wrap
  try:
    link_flags.pop(link_flags.index("-Wl,--wrap=panicHandler"))
  except:
    pass
  try:
    link_flags.pop(link_flags.index("-Wl,--wrap=xt_unhandled_exception"))
  except:
    pass
