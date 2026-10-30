# Inky Impression JPEG dithering

[inky_dither.be](./inky_dither.be) converts a JPEG image for the 7.3-inch Inky Impression display with the E673 controller. It applies Floyd–Steinberg dithering to the six colors used by the Inky E673 Python driver, then saves the result as a JPEG.

## Requirements

## Inky Impression 7.3-inch display

- `Inky_Impression_7_3_display.ini` supports the 800x480 Inky Impression 7.3-inch Spectra 6
display with the E673 controller. It uses the universal uDisplay SPI driver and expects
the display reset pin and the active-low BUSY signal on SPI MISO to be configured. A full color refresh takes about 32 seconds.

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

Dithering runs in Berry and can take a while on an ESP32. The script yields every 128 pixels and at each row boundary so Tasmota's Berry execution timeout does not interrupt the pixel loop. It prints progress after each 16 rows; wait until it reports 480 rows and returns the output map.

If `load("inky_dither.be")` fails with `img undeclared`, the running firmware does not provide the Berry `img` class. Confirm that it was built with `USE_BERRY_IMAGE` enabled, then rebuild and flash it. The failure occurs while Berry compiles the script, before `inky_dither()` runs.

## Parameters

```berry
inky_dither(input_path, output_path, saturation, jpeg_quality)
```

- `input_path`: path to the source JPEG on the Tasmota filesystem.
- `output_path`: destination path for the dithered JPEG. It may be the same as the input path.
- `saturation`: palette blend from `0.0` to `1.0`. `0.5` matches the Python driver's default. Lower values use the desaturated palette; higher values increase saturation.
- `jpeg_quality`: ESP32 camera encoder quality from `0` to `63`. Lower values retain more JPEG quality; the default `12` matches the Tasmota image encoder default.

Berry does not support default values in function declarations. Omit the optional arguments or pass `nil` to use the defaults. For example, `inky_dither("/image.jpg", "/image-dithered.jpg", nil, 30)` uses the default saturation and JPEG quality `30`.

For example, use a more saturated palette and a smaller, more compressed JPEG:

```berry
var result = inky_dither("/image.jpg", "/image-dithered.jpg", 0.75, 30)
print(result)
```

The function returns a map with the output `path`, `width`, `height`, and encoded file size in `bytes`. JPEG is lossy, so the saved file can contain slight color changes from the six dither palette colors.
