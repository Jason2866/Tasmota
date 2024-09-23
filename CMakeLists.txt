cmake_minimum_required(VERSION 3.16.0)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)

project(tasmota)

include(gcc)

set(CMAKE_AR ${_CMAKE_TOOLCHAIN_PREFIX}gcc-ar)
set(CMAKE_RANLIB ${_CMAKE_TOOLCHAIN_PREFIX}gcc-ranlib)

# Add
set(app_lto_components tasmota)
# Add
set(idf_lto_components spi_flash esp_partition mbedtls wpa_supplicant esp_adc esp_eth http_parser esp_ringbuf esp_driver_gptimer esp_driver_usb_serial_jtag driver lwip wpa_supplicant nvs_flash)
# Add
set(lto_depends fatfs nvs_flash app_update bootloader_support bt esp_hid usb esp_psram)

# Add
cu_gcc_lto_set(COMPONENTS ${app_lto_components} ${idf_lto_components} 
               DEPENDS ${lto_depends})

cu_gcc_string_1byte_align(COMPONENTS ${app_lto_components} ${idf_lto_components} 
                          DEPENDS ${lto_depends})

if(CONFIG_IDF_TARGET_ESP32C2)
    include(relinker)
endif()
