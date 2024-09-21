# Compare to "ar" and "ranlib", "gcc-ar" and "gcc-ranlib" integrate GCC LTO plugin
set(CMAKE_AR ${_CMAKE_TOOLCHAIN_PREFIX}gcc-ar)
set(CMAKE_RANLIB ${_CMAKE_TOOLCHAIN_PREFIX}gcc-ranlib)

list(APPEND compile_options "-ffat-lto-objects -flto-compression-level=9 -flto=auto")
list(APPEND CMAKE_EXE_LINKER_FLAGS "-flto -fuse-linker-plugin -ffat-lto-objects -flto-partition=max")
