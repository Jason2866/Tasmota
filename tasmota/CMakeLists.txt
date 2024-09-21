FILE(GLOB_RECURSE app_sources ${CMAKE_SOURCE_DIR}/tasmota/*.*)

# Compare to "ar" and "ranlib", "gcc-ar" and "gcc-ranlib" integrate GCC LTO plugin
set(CMAKE_AR ${_CMAKE_TOOLCHAIN_PREFIX}gcc-ar)
set(CMAKE_RANLIB ${_CMAKE_TOOLCHAIN_PREFIX}gcc-ranlib)

unset(compile_options)
unset(c_compile_options)
unset(cxx_compile_options)
set(compile_options                 "-ffat-lto-objects"
                                    "-flto-compression-level=9"
                                    "-flto=auto"
                                    "-ffunction-sections"
                                    "-fdata-sections"
                                    # warning-related flags
                                    # "-Wall"
                                    # "-Werror"
                                    "-Wno-error=unused-function"
                                    "-Wno-error=unused-variable"
                                    "-Wno-error=unused-but-set-variable"
                                    "-Wno-error=deprecated-declarations"
                                    # "-Wextra"
                                    "-Wno-error=extra"
                                    "-Wno-unused-parameter"
                                    "-Wno-sign-compare"
                                    # ignore multiple enum conversion warnings since gcc 11
                                    # TODO: IDF-5163
                                    "-Wno-enum-conversion"
                                    # Default is dwarf-5 since GCC 11, fallback to dwarf-4 because of binary size
                                    # TODO: IDF-5160
                                    "-gdwarf-4")
# list(REMOVE_DUPLICATES compile_options)
# list(SORT compile_options)

list(APPEND CMAKE_EXE_LINKER_FLAGS "-flto -fuse-linker-plugin -ffat-lto-objects -flto-partition=max")

idf_component_register(SRCS ${app_sources})
