# Floyd-Steinberg quantization for Inky Impression 7.3 (E673 / Spectra 6).
# Load this file in the Berry console, then call:
#   inky_dither("/image.jpg", "/image-dithered.jpg")
# Images are resized to the logical display dimensions from display.ini;
# uDisplay applies the configured panel rotation when drawing.
# Optional arguments are saturation (0.0..1.0, default 0.5) and JPEG quality
# (default 85, range 1..100; higher values preserve more detail).

import path
import introspect
import gc
import display

def inky_dither(input_path, output_path, saturation, jpeg_quality)
  if saturation == nil
    saturation = 0.5
  end
  if jpeg_quality == nil
    jpeg_quality = 85
  end

  if saturation < 0.0 || saturation > 1.0
    raise "value_error", "saturation must be between 0.0 and 1.0"
  end
  if jpeg_quality < 1 || jpeg_quality > 100
    raise "value_error", "JPEG quality must be between 1 and 100"
  end

  var input_file = open(input_path, "rb")
  if input_file == nil
    raise "io_error", "could not open input JPEG"
  end
  var input_size = input_file.size()
  if input_size <= 0
    input_file.close()
    raise "io_error", "input JPEG is empty"
  end
  # Berry limits bytes() to 512 KiB on PSRAM builds and 32 KiB otherwise.
  if input_size > 512 * 1024
    input_file.close()
    raise "memory_error", "JPEG exceeds Berry's 512 KiB bytes limit"
  end

  var jpeg_data = nil
  try
    jpeg_data = input_file.readbytes()
  except .. as err, msg
    input_file.close()
    raise err, msg
  end
  input_file.close()
  if size(jpeg_data) != input_size
    raise "io_error", "could not read complete input JPEG"
  end

  var rgb_format = img.RGB888
  var jpeg_format = img.JPEG
  var image = img()
  image.from_jpg(jpeg_data, rgb_format)
  jpeg_data = nil
  gc.collect()

  var info = image.info()
  if info["bpp"] != 3 || info["width"] <= 0 || info["height"] <= 0
    raise "value_error", "input JPEG must decode to RGB888"
  end

  # Use dimensions after the display.ini rotation. The native method keeps
  # the large resize buffer in PSRAM; uDisplay applies panel rotation on draw.
  var width = 0
  var height = 0
  try
    width = display.width()
    height = display.height()
  except .. as err, msg
    if err == "attribute_error"
      raise "feature_error", "Firmware is outdated: rebuild and flash Tasmota with display.width()/height() and the current InkyDither library for rotated display dimensions"
    end
    raise err, msg
  end
  if width <= 0 || height <= 0
    raise "display_error", "display is not initialized"
  end
  image.resize(width, height)
  info = image.info()
  if info["width"] != width || info["height"] != height || info["bpp"] != 3
    raise "value_error", "could not prepare image for the configured display dimensions"
  end

  # Map the native RGB888 image buffer instead of copying its 1.15 MiB payload.
  var pixels = bytes(introspect.toptr(info["buf_addr"]), info["size"])
  width = info["width"]
  height = info["height"]

  # Use the C implementation for Floyd-Steinberg dithering
  InkyDither.dither(pixels, width, height, saturation)
  print("Dithering: " + str(height) + "/" + str(height) + " rows")

  # JPEG conversion replaces the RGB buffer with the encoded data.
  image.convert_to(jpeg_format, jpeg_quality)
  info = image.info()
  var encoded = bytes(introspect.toptr(info["buf_addr"]), info["size"])
  var temp_path = output_path + ".tmp"
  var backup_path = temp_path + ".bak"
  while temp_path == input_path || backup_path == input_path || path.exists(temp_path) || path.exists(backup_path)
    temp_path += ".tmp"
    backup_path = temp_path + ".bak"
  end
  var output = open(temp_path, "wb")
  if output == nil
    raise "io_error", "could not open temporary output JPEG"
  end
  try
    output.write(encoded)
  except .. as err, msg
    output.close()
    path.remove(temp_path)
    raise err, msg
  end
  output.close()

  var has_previous_output = path.exists(output_path)
  if has_previous_output && !path.rename(output_path, backup_path)
    path.remove(temp_path)
    raise "io_error", "could not back up existing output JPEG"
  end
  if !path.rename(temp_path, output_path)
    if has_previous_output && !path.rename(backup_path, output_path)
      path.remove(temp_path)
      raise "io_error", "could not restore original output JPEG; backup is at " + backup_path
    end
    path.remove(temp_path)
    raise "io_error", "could not replace output JPEG"
  end
  if has_previous_output
    path.remove(backup_path)
  end

  # Release the decoded and encoded image buffers before JPEG rendering.
  pixels = nil
  encoded = nil
  image = nil
  gc.collect()

  if !display.draw_jpg(output_path)
    raise "display_error", "could not display the dithered JPEG"
  end

  return {"width": info["width"], "height": info["height"],
          "bytes": info["size"], "path": output_path}
end

return inky_dither
