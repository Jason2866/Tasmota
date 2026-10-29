# Floyd-Steinberg quantization for Inky Impression 7.3 (E673 / Spectra 6).
# Load this file in the Berry console, then call:
#   inky_dither("/image.jpg", "/image-dithered.jpg")
# Optional arguments are saturation (0.0..1.0, default 0.5) and JPEG quality
# (default 12, matching the native img encoder; ESP32 camera scale 0..63).

def inky_dither(input_path, output_path, saturation=0.5, jpeg_quality=12)
  if saturation < 0.0 || saturation > 1.0
    raise "value_error", "saturation must be between 0.0 and 1.0"
  end
  if jpeg_quality < 0 || jpeg_quality > 63
    raise "value_error", "JPEG quality must be between 0 and 63"
  end

  var input = open(input_path, "rb")
  if input == nil
    raise "io_error", "could not open input JPEG"
  end
  var input_size = input.size()
  if input_size <= 0
    input.close()
    raise "io_error", "input JPEG is empty"
  end
  # Berry limits bytes() to 512 KiB on PSRAM builds and 32 KiB otherwise.
  if input_size > 512 * 1024
    input.close()
    raise "memory_error", "JPEG exceeds Berry's 512 KiB bytes limit"
  end

  var jpeg_data = nil
  try
    jpeg_data = input.readbytes()
  except .. as err, msg
    input.close()
    raise err, msg
  end
  input.close()
  if size(jpeg_data) != input_size
    raise "io_error", "could not read complete input JPEG"
  end

  var rgb_format = img.RGB888
  var jpeg_format = img.JPEG
  var image = img()
  image.from_jpg(jpeg_data, rgb_format)
  jpeg_data = nil

  var info = image.info()
  if info["width"] != 800 || info["height"] != 480 || info["bpp"] != 3
    raise "value_error", "input image must decode to 800x480 RGB888"
  end

  # The first six entries of the Inky palettes are the quantization colors.
  # The last white entry in the Python driver is not included in quantize(6).
  var saturated = [0, 0, 0, 161, 164, 165, 208, 190, 71,
                   156, 72, 75, 61, 59, 94, 58, 91, 70]
  var desaturated = [0, 0, 0, 255, 255, 255, 255, 255, 0,
                     255, 0, 0, 0, 0, 255, 0, 255, 0]
  var palette = list()
  var p = 0
  while p < 18
    palette.push(int(saturated[p] * saturation + desaturated[p] * (1.0 - saturation)))
    p += 1
  end

  # Map the native RGB888 image buffer instead of copying its 1.15 MiB payload.
  import introspect
  var pixels = bytes(introspect.toptr(info["buf_addr"]), info["size"])
  var width = info["width"]
  var height = info["height"]
  var stride = width * 3
  var next = 0
  var value = 0
  var y = 0
  while y < height
    var x = 0
    while x < width
      var index = y * stride + x * 3
      var red = pixels[index]
      var green = pixels[index + 1]
      var blue = pixels[index + 2]

      var best = 0
      var best_distance = 2147483647
      var color = 0
      while color < 18
        var dr = red - palette[color]
        var dg = green - palette[color + 1]
        var db = blue - palette[color + 2]
        var distance = dr * dr + dg * dg + db * db
        if distance < best_distance
          best_distance = distance
          best = color
        end
        color += 3
      end

      var error_red = red - palette[best]
      var error_green = green - palette[best + 1]
      var error_blue = blue - palette[best + 2]
      pixels[index] = palette[best]
      pixels[index + 1] = palette[best + 1]
      pixels[index + 2] = palette[best + 2]

      # Floyd-Steinberg weights: right 7/16, down-left 3/16,
      # down 5/16, down-right 1/16. Clamp propagated RGB values.
      if x + 1 < width
        next = index + 3
        value = pixels[next] + int(error_red * 7 / 16)
        value = value < 0 ? 0 : (value > 255 ? 255 : value)
        pixels[next] = value
        value = pixels[next + 1] + int(error_green * 7 / 16)
        value = value < 0 ? 0 : (value > 255 ? 255 : value)
        pixels[next + 1] = value
        value = pixels[next + 2] + int(error_blue * 7 / 16)
        value = value < 0 ? 0 : (value > 255 ? 255 : value)
        pixels[next + 2] = value
      end

      if y + 1 < height
        if x > 0
          next = index + stride - 3
          value = pixels[next] + int(error_red * 3 / 16)
          value = value < 0 ? 0 : (value > 255 ? 255 : value)
          pixels[next] = value
          value = pixels[next + 1] + int(error_green * 3 / 16)
          value = value < 0 ? 0 : (value > 255 ? 255 : value)
          pixels[next + 1] = value
          value = pixels[next + 2] + int(error_blue * 3 / 16)
          value = value < 0 ? 0 : (value > 255 ? 255 : value)
          pixels[next + 2] = value
        end

        next = index + stride
        value = pixels[next] + int(error_red * 5 / 16)
        value = value < 0 ? 0 : (value > 255 ? 255 : value)
        pixels[next] = value
        value = pixels[next + 1] + int(error_green * 5 / 16)
        value = value < 0 ? 0 : (value > 255 ? 255 : value)
        pixels[next + 1] = value
        value = pixels[next + 2] + int(error_blue * 5 / 16)
        value = value < 0 ? 0 : (value > 255 ? 255 : value)
        pixels[next + 2] = value

        if x + 1 < width
          next = index + stride + 3
          value = pixels[next] + int(error_red / 16)
          value = value < 0 ? 0 : (value > 255 ? 255 : value)
          pixels[next] = value
          value = pixels[next + 1] + int(error_green / 16)
          value = value < 0 ? 0 : (value > 255 ? 255 : value)
          pixels[next + 1] = value
          value = pixels[next + 2] + int(error_blue / 16)
          value = value < 0 ? 0 : (value > 255 ? 255 : value)
          pixels[next + 2] = value
        end
      end
      x += 1
    end
    y += 1
  end

  # JPEG conversion replaces the RGB buffer with the encoded data.
  image.convert_to(jpeg_format, jpeg_quality)
  info = image.info()
  var encoded = bytes(introspect.toptr(info["buf_addr"]), info["size"])
  var output = open(output_path, "wb")
  if output == nil
    raise "io_error", "could not open output JPEG"
  end
  try
    output.write(encoded)
  except .. as err, msg
    output.close()
    raise err, msg
  end
  output.close()

  return {"width": info["width"], "height": info["height"],
          "bytes": info["size"], "path": output_path}
end
