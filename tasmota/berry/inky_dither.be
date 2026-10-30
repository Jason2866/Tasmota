# Floyd-Steinberg quantization for Inky Impression 7.3 (E673 / Spectra 6).
# Load this file in the Berry console, then call:
#   inky_dither("/image.jpg", "/image-dithered.jpg")
# Optional arguments are saturation (0.0..1.0, default 0.5) and JPEG quality
# (default 85, range 1..100; higher values preserve more detail).

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

  var info = image.info()
  if info["width"] != 800 || info["height"] != 480 || info["bpp"] != 3
    raise "value_error", "input image must decode to 800x480 RGB888"
  end

  # The first six entries of the Inky palettes are the quantization colors.
  # The last white entry in the Python driver is not included in quantize(6).
  var saturated = [0, 0, 0, 161, 164, 165, 208, 190, 71,
                   156, 72, 75, 61, 59, 94, 58, 91, 70]
  # Store the panel's ideal RGB colors in the JPEG. EPDPanel maps RGB565 to
  # these same six colors, while the blended palette above is only for
  # selecting colors and calculating the dithering error.
  var desaturated = [0, 0, 0, 255, 255, 255, 255, 255, 0,
                     255, 0, 0, 0, 0, 255, 0, 255, 0]
  var inv_sat = 1.0 - saturation
  var pal0r = int(saturated[0] * saturation + desaturated[0] * inv_sat)
  var pal0g = int(saturated[1] * saturation + desaturated[1] * inv_sat)
  var pal0b = int(saturated[2] * saturation + desaturated[2] * inv_sat)
  var pal1r = int(saturated[3] * saturation + desaturated[3] * inv_sat)
  var pal1g = int(saturated[4] * saturation + desaturated[4] * inv_sat)
  var pal1b = int(saturated[5] * saturation + desaturated[5] * inv_sat)
  var pal2r = int(saturated[6] * saturation + desaturated[6] * inv_sat)
  var pal2g = int(saturated[7] * saturation + desaturated[7] * inv_sat)
  var pal2b = int(saturated[8] * saturation + desaturated[8] * inv_sat)
  var pal3r = int(saturated[9] * saturation + desaturated[9] * inv_sat)
  var pal3g = int(saturated[10] * saturation + desaturated[10] * inv_sat)
  var pal3b = int(saturated[11] * saturation + desaturated[11] * inv_sat)
  var pal4r = int(saturated[12] * saturation + desaturated[12] * inv_sat)
  var pal4g = int(saturated[13] * saturation + desaturated[13] * inv_sat)
  var pal4b = int(saturated[14] * saturation + desaturated[14] * inv_sat)
  var pal5r = int(saturated[15] * saturation + desaturated[15] * inv_sat)
  var pal5g = int(saturated[16] * saturation + desaturated[16] * inv_sat)
  var pal5b = int(saturated[17] * saturation + desaturated[17] * inv_sat)

  # Map the native RGB888 image buffer instead of copying its 1.15 MiB payload.
  import introspect
  var pixels = bytes(introspect.toptr(info["buf_addr"]), info["size"])
  var width = info["width"]
  var height = info["height"]
  var stride = width * 3
  var last_x = width - 1
  var last_y = height - 1

  # Reused by the pixel loop. Declared here so the inner loop has no `var`.
  var packed = 0
  var red = 0
  var green = 0
  var blue = 0
  var dr = 0
  var dg = 0
  var db = 0
  var d = 0
  var best_d = 0
  var pal_r = 0
  var pal_g = 0
  var pal_b = 0
  var id_r = 0
  var id_g = 0
  var id_b = 0
  var error_red = 0
  var error_green = 0
  var error_blue = 0
  var ar = 0
  var ag = 0
  var ab = 0
  var e7r = 0
  var e5r = 0
  var e3r = 0
  var e1r = 0
  var e7g = 0
  var e5g = 0
  var e3g = 0
  var e1g = 0
  var e7b = 0
  var e5b = 0
  var e3b = 0
  var e1b = 0
  var r = 0
  var g = 0
  var b = 0
  var next = 0
  var down = 0

  var y = 0
  var index = 0
  while y < height
    var x = 0
    while x < width
      packed = pixels.get(index, 3)
      red = packed & 0xFF
      green = (packed >> 8) & 0xFF
      blue = packed >> 16

      dr = red - pal0r
      dg = green - pal0g
      db = blue - pal0b
      best_d = dr * dr + dg * dg + db * db
      pal_r = pal0r
      pal_g = pal0g
      pal_b = pal0b
      id_r = 0
      id_g = 0
      id_b = 0

      dr = red - pal1r
      dg = green - pal1g
      db = blue - pal1b
      d = dr * dr + dg * dg + db * db
      if d < best_d
        best_d = d
        pal_r = pal1r
        pal_g = pal1g
        pal_b = pal1b
        id_r = 255
        id_g = 255
        id_b = 255
      end

      dr = red - pal2r
      dg = green - pal2g
      db = blue - pal2b
      d = dr * dr + dg * dg + db * db
      if d < best_d
        best_d = d
        pal_r = pal2r
        pal_g = pal2g
        pal_b = pal2b
        id_r = 255
        id_g = 255
        id_b = 0
      end

      dr = red - pal3r
      dg = green - pal3g
      db = blue - pal3b
      d = dr * dr + dg * dg + db * db
      if d < best_d
        best_d = d
        pal_r = pal3r
        pal_g = pal3g
        pal_b = pal3b
        id_r = 255
        id_g = 0
        id_b = 0
      end

      dr = red - pal4r
      dg = green - pal4g
      db = blue - pal4b
      d = dr * dr + dg * dg + db * db
      if d < best_d
        best_d = d
        pal_r = pal4r
        pal_g = pal4g
        pal_b = pal4b
        id_r = 0
        id_g = 0
        id_b = 255
      end

      dr = red - pal5r
      dg = green - pal5g
      db = blue - pal5b
      d = dr * dr + dg * dg + db * db
      if d < best_d
        pal_r = pal5r
        pal_g = pal5g
        pal_b = pal5b
        id_r = 0
        id_g = 255
        id_b = 0
      end

      error_red = red - pal_r
      error_green = green - pal_g
      error_blue = blue - pal_b
      pixels.set(index, id_r | (id_g << 8) | (id_b << 16), 3)

      # Toward-zero int(error * n / 16) without software floats.
      ar = error_red < 0 ? -error_red : error_red
      ag = error_green < 0 ? -error_green : error_green
      ab = error_blue < 0 ? -error_blue : error_blue
      e7r = (ar * 7) >> 4
      e5r = (ar * 5) >> 4
      e3r = (ar * 3) >> 4
      e1r = ar >> 4
      e7g = (ag * 7) >> 4
      e5g = (ag * 5) >> 4
      e3g = (ag * 3) >> 4
      e1g = ag >> 4
      e7b = (ab * 7) >> 4
      e5b = (ab * 5) >> 4
      e3b = (ab * 3) >> 4
      e1b = ab >> 4
      if error_red < 0
        e7r = -e7r
        e5r = -e5r
        e3r = -e3r
        e1r = -e1r
      end
      if error_green < 0
        e7g = -e7g
        e5g = -e5g
        e3g = -e3g
        e1g = -e1g
      end
      if error_blue < 0
        e7b = -e7b
        e5b = -e5b
        e3b = -e3b
        e1b = -e1b
      end

      # Floyd-Steinberg weights: right 7/16, down-left 3/16,
      # down 5/16, down-right 1/16. Clamp propagated RGB values.
      if y < last_y && x > 0 && x < last_x
        next = index + 3
        packed = pixels.get(next, 3)
        r = (packed & 0xFF) + e7r
        g = ((packed >> 8) & 0xFF) + e7g
        b = (packed >> 16) + e7b
        pixels.set(next, (r < 0 ? 0 : (r > 255 ? 255 : r)) | ((g < 0 ? 0 : (g > 255 ? 255 : g)) << 8) | ((b < 0 ? 0 : (b > 255 ? 255 : b)) << 16), 3)

        next = index + stride - 3
        packed = pixels.get(next, 3)
        r = (packed & 0xFF) + e3r
        g = ((packed >> 8) & 0xFF) + e3g
        b = (packed >> 16) + e3b
        pixels.set(next, (r < 0 ? 0 : (r > 255 ? 255 : r)) | ((g < 0 ? 0 : (g > 255 ? 255 : g)) << 8) | ((b < 0 ? 0 : (b > 255 ? 255 : b)) << 16), 3)

        next = index + stride
        packed = pixels.get(next, 3)
        r = (packed & 0xFF) + e5r
        g = ((packed >> 8) & 0xFF) + e5g
        b = (packed >> 16) + e5b
        pixels.set(next, (r < 0 ? 0 : (r > 255 ? 255 : r)) | ((g < 0 ? 0 : (g > 255 ? 255 : g)) << 8) | ((b < 0 ? 0 : (b > 255 ? 255 : b)) << 16), 3)

        next = index + stride + 3
        packed = pixels.get(next, 3)
        r = (packed & 0xFF) + e1r
        g = ((packed >> 8) & 0xFF) + e1g
        b = (packed >> 16) + e1b
        pixels.set(next, (r < 0 ? 0 : (r > 255 ? 255 : r)) | ((g < 0 ? 0 : (g > 255 ? 255 : g)) << 8) | ((b < 0 ? 0 : (b > 255 ? 255 : b)) << 16), 3)
      else
        if x < last_x
          next = index + 3
          packed = pixels.get(next, 3)
          r = (packed & 0xFF) + e7r
          g = ((packed >> 8) & 0xFF) + e7g
          b = (packed >> 16) + e7b
          pixels.set(next, (r < 0 ? 0 : (r > 255 ? 255 : r)) | ((g < 0 ? 0 : (g > 255 ? 255 : g)) << 8) | ((b < 0 ? 0 : (b > 255 ? 255 : b)) << 16), 3)
        end

        if y < last_y
          down = index + stride
          if x > 0
            next = down - 3
            packed = pixels.get(next, 3)
            r = (packed & 0xFF) + e3r
            g = ((packed >> 8) & 0xFF) + e3g
            b = (packed >> 16) + e3b
            pixels.set(next, (r < 0 ? 0 : (r > 255 ? 255 : r)) | ((g < 0 ? 0 : (g > 255 ? 255 : g)) << 8) | ((b < 0 ? 0 : (b > 255 ? 255 : b)) << 16), 3)
          end

          packed = pixels.get(down, 3)
          r = (packed & 0xFF) + e5r
          g = ((packed >> 8) & 0xFF) + e5g
          b = (packed >> 16) + e5b
          pixels.set(down, (r < 0 ? 0 : (r > 255 ? 255 : r)) | ((g < 0 ? 0 : (g > 255 ? 255 : g)) << 8) | ((b < 0 ? 0 : (b > 255 ? 255 : b)) << 16), 3)

          if x < last_x
            next = down + 3
            packed = pixels.get(next, 3)
            r = (packed & 0xFF) + e1r
            g = ((packed >> 8) & 0xFF) + e1g
            b = (packed >> 16) + e1b
            pixels.set(next, (r < 0 ? 0 : (r > 255 ? 255 : r)) | ((g < 0 ? 0 : (g > 255 ? 255 : g)) << 8) | ((b < 0 ? 0 : (b > 255 ? 255 : b)) << 16), 3)
          end
        end
      end

      index += 3
      x += 1
    end
    tasmota.yield()
    y += 1
    if y % 16 == 0 || y == height
      print("Inky dithering: " + str(y) + "/" + str(height) + " rows")
    end
  end

  # JPEG conversion replaces the RGB buffer with the encoded data.
  image.convert_to(jpeg_format, jpeg_quality)
  info = image.info()
  var encoded = bytes(introspect.toptr(info["buf_addr"]), info["size"])
  var temp_path = output_path + ".tmp"
  var backup_path = temp_path + ".bak"
  import path
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
  import gc
  gc.collect()

  import display
  if !display.draw_jpg(output_path)
    raise "display_error", "could not display the dithered JPEG"
  end

  return {"width": info["width"], "height": info["height"],
          "bytes": info["size"], "path": output_path}
end
