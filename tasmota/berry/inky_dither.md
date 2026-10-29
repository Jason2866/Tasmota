# Inky Impression JPEG dithering

[inky_dither.be](./inky_dither.be) converts a JPEG image for the 7.3-inch Inky Impression display with the E673 controller. It applies Floyd–Steinberg dithering to the six colors used by the Inky E673 Python driver, then saves the result as a JPEG.

## Requirements

- An ESP32 Tasmota build with Berry and `USE_BERRY_IMAGE` enabled. The Berry `img` class is provided by that feature.
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

The output file is written to the Tasmota filesystem. Retrieve it using the device's filesystem access method.

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
