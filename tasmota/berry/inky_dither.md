# Inky Impression JPEG dithering

[inky_dither.be](./inky_dither.be) converts a JPEG image for the 7.3-inch Inky Impression display with the E673 controller. It applies Floyd–Steinberg dithering to the six colors used by the Inky E673 Python driver, then saves the result as a JPEG.

## Requirements

## Inky Impression 7.3-inch display

- `Inky_Impression_7_3_display.ini` supports the 800x480 Inky Impression 7.3-inch Spectra 6
display with the E673 controller. It uses the universal uDisplay SPI driver and expects
the display reset pin and the active-low BUSY signal to be configured. A full color refresh takes about 32 seconds.

### Tasmota GPIO configuration and wiring

The Inky's `BUSY` signal is a separate panel status output; it is not SPI MISO data. The current uDisplay descriptor uses the Tasmota `SPI MISO` GPIO as the input for this signal, so connect Inky `BUSY` to the ESP GPIO configured as `SPI MISO`. The driver reads that pin as a GPIO while waiting for the panel; it does not read display data over MISO.

Configure the Tasmota GPIO functions to match the signals you wired:

| Inky E673 signal | Raspberry Pi header pin | Tasmota GPIO function |
| --- | --- | --- |
| `CS` / `CS0` | pin 24 | `SPI CS` |
| `SCLK` | pin 23 | `SPI CLK` |
| `MOSI` / `DIN` | pin 19 | `SPI MOSI` |
| `D/C` | pin 15 | `SPI DC` |
| `RESET` | pin 13 | `Display Rst` |
| `BUSY` | pin 11 | `SPI MISO` |
| `3V3` | pin 1 | `3V3` |
| `5V` | pin 2 | `5V` |
| `GND` | pin 6 | `GND` |

Assign each Tasmota function to the ESP GPIO physically wired to that Inky signal, using **Configure Module** (or the equivalent GPIO configuration for your device). The middle column documents the Raspberry Pi 40-pin header locations; these are not ESP32 GPIO numbers. Choose suitable GPIOs for your ESP32 wiring and assign the Tasmota functions accordingly. In particular, ensure that `SPI MISO` is assigned even though the panel has no MISO data output.

- An ESP32 Tasmota build with Berry and `USE_BERRY_IMAGE` enabled. The Berry `img` class is provided by that feature. For a custom build, define `USE_BERRY_IMAGE` in `my_user_config.h` and rebuild and flash Tasmota; this is a compile-time option and cannot be enabled by loading the script.
- JPEG display support (`JPEG_PICTS`) must also be enabled in the ESP32 Tasmota build. The script uses the universal display driver to render the saved JPEG and refresh the panel.
- PSRAM is required for the decoded 800 × 480 RGB image buffer. The buffer uses about 1.15 MiB, in addition to memory needed by JPEG decoding and encoding.
- The source must be a JPEG that decodes to exactly 800 × 480 pixels.
- Berry's `bytes()` limit restricts the compressed source JPEG to 512 KiB on PSRAM builds and 32 KiB without PSRAM. In practice, PSRAM is required for this workflow.

Upload [inky_dither.be](./inky_dither.be) and the source JPEG to the Tasmota filesystem. The examples below assume both files are in the filesystem root.

## Run from the Berry console

Load the script, then call `inky_dither()` with the input and output paths:

```berry
load("inky_dither.be")
var result = inky_dither("/image.jpg", "/image-dithered.jpg")
print(result)
```

After the output file is written successfully, the script renders it at the top-left corner of the active universal display and refreshes the panel. The Inky refresh takes about 32 seconds. The output JPEG remains in the Tasmota filesystem; retrieve it using the device's filesystem access method.

Dithering is performed by the native InkyDither.dither class for optimal performance.

If `load("inky_dither.be")` fails with `img undeclared`, the running firmware does not provide the Berry `img` class. Confirm that it was built with `USE_BERRY_IMAGE` enabled, then rebuild and flash it. The failure occurs while Berry compiles the script, before `inky_dither()` runs.

## Parameters

```berry
inky_dither(input_path, output_path, saturation, jpeg_quality)
```

- `input_path`: path to the source JPEG on the Tasmota filesystem.
- `output_path`: destination path for the dithered JPEG. It may be the same as the input path.
- `saturation`: palette blend from `0.0` to `1.0`. `0.5` matches the Python driver's default. Lower values use the desaturated palette; higher values increase saturation.
- `jpeg_quality`: software JPEG encoder quality from `1` to `100`. Higher values preserve more image detail and generally produce larger files. The default is `85`.

Berry does not support default values in function declarations. Omit the optional arguments or pass `nil` to use the defaults. For example, `inky_dither("/image.jpg", "/image-dithered.jpg", nil, 90)` uses the default saturation and JPEG quality `90`.

For example, use a more saturated palette and a smaller, more compressed JPEG:

```berry
var result = inky_dither("/image.jpg", "/image-dithered.jpg", 0.75, 70)
print(result)
```

The function returns a map with the output `path`, `width`, `height`, and encoded file size in `bytes`. JPEG is lossy, so the saved file can contain slight color changes from the six dither palette colors. Higher `jpeg_quality` values reduce these changes at the cost of a larger file.
