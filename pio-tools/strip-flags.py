Import('env')

link_flags = env['LINKFLAGS']
build_flags = " ".join(env['BUILD_FLAGS'])

try:
  link_flags.pop(link_flags.index("-u _printf_float"))
  print("*** link flags:", link_flags)
except:
  pass
try:
  link_flags.pop(link_flags.index("-u _scanf_float"))
  print("*** link flags:", link_flags)
except:
  pass

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
