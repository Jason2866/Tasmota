/********************************************************************
 * Berry class `inky_dither`
 *
 * Serpentine Jarvis-Judice-Ninke error diffusion dithering for the
 * Inky 7.3" Pimoroni display palette.
 *******************************************************************/
#include "be_constobj.h"
#include "be_mem.h"
#include "be_exec.h"
#include "be_byteslib.h"
#include <stdint.h>
#include <string.h>

#ifdef USE_BERRY_IMAGE
#include "esp32-hal.h"

static inline int32_t clamp_fixed(int32_t value) {
    if (value < 0) return 0;
    if (value > 255 * 16) return 255 * 16;
    return value;
}

static inline int32_t divide_round_48(int32_t value) {
    return value < 0 ? -((-value + 24) / 48) : (value + 24) / 48;
}

static int find_closest_color(const int32_t *color, const int32_t *palette) {
    int best = 0;
    int32_t best_distance = INT32_MAX;
    for (int index = 0; index < 6; index++) {
        int32_t red = color[0] - palette[index * 3] * 16;
        int32_t green = color[1] - palette[index * 3 + 1] * 16;
        int32_t blue = color[2] - palette[index * 3 + 2] * 16;
        int32_t distance = red * red + green * green + blue * blue;
        if (distance < best_distance) {
            best_distance = distance;
            best = index;
        }
    }
    return best;
}

// InkyDither.dither(pixels:bytes(), width:int, height:int, saturation:float, strength:float) -> nil
//
// Perform Serpentine Jarvis-Judice-Ninke error diffusion dithering on the RGB888
// pixel buffer in-place.
// pixels: bytes object containing RGB888 data (3 bytes per pixel)
// width: image width in pixels
// height: image height in pixels
// saturation: saturation value between 0.0 and 1.0 (default 0.5)
// strength: error diffusion strength between 0.0 and 1.0 (default 1.0)
int m_inky_dither_dither(bvm *vm);
int m_inky_dither_dither(bvm *vm) {
    int32_t argc = be_top(vm);

    // Check arguments
    if (argc < 3 || !be_isbytes(vm, 1) || !be_isint(vm, 2) || !be_isint(vm, 3)) {
        be_raise(vm, "value_error", "Expected bytes, width, height as arguments");
    }

    // Get saturation (optional, default 0.5)
    float saturation = 0.5f;
    if (argc >= 4) {
        if (be_isnumber(vm, 4)) {
            saturation = be_toreal(vm, 4);
            if (!(saturation >= 0.0f && saturation <= 1.0f)) {
                be_raise(vm, "value_error", "saturation must be between 0.0 and 1.0");
            }
        } else if (!be_isnil(vm, 4)) {
            be_raise(vm, "value_error", "saturation must be a number or nil");
        }
    }

    float strength = 1.0f;
    if (argc >= 5) {
        if (be_isnumber(vm, 5)) {
            strength = be_toreal(vm, 5);
            if (!(strength >= 0.0f && strength <= 1.0f)) {
                be_raise(vm, "value_error", "strength must be between 0.0 and 1.0");
            }
        } else if (!be_isnil(vm, 5)) {
            be_raise(vm, "value_error", "strength must be a number or nil");
        }
    }
    int32_t strength_fixed = (int32_t)(strength * 256.0f + 0.5f);

    // Get width and height
    int32_t width = be_toint(vm, 2);
    int32_t height = be_toint(vm, 3);

    if (width <= 0 || height <= 0) {
        be_raise(vm, "value_error", "image dimensions must be positive");
    }
    if ((size_t)width > SIZE_MAX / 3 / (size_t)height) {
        be_raise(vm, "value_error", "image dimensions too large");
    }
    if ((size_t)width > SIZE_MAX / (9 * sizeof(int32_t))) {
        be_raise(vm, "value_error", "image dimensions too large");
    }

    // Get pixel buffer
    size_t pixel_size = 0;
    uint8_t *pixels = (uint8_t *) be_tobytes(vm, 1, &pixel_size);
    if (!pixels) {
        be_raise(vm, "value_error", "invalid pixel buffer");
    }
    // The passed size may be the JPEG encoded size, so we calculate expected size from dimensions
    size_t expected_size = (size_t)width * (size_t)height * 3;
    if (pixel_size < expected_size) {
        be_raise(vm, "value_error", "pixel buffer too small");
    }

    // Calculate palette based on saturation
    static const int32_t saturated[18] = {
        0, 0, 0, 161, 164, 165, 208, 190, 71,
        156, 72, 75, 61, 59, 94, 58, 91, 70
    };
    static const int32_t desaturated[18] = {
        0, 0, 0, 255, 255, 255, 255, 255, 0,
        255, 0, 0, 0, 0, 255, 0, 255, 0
    };

    float inv_sat = 1.0f - saturation;
    int32_t palette[18];
    for (int i = 0; i < 18; i++) {
        palette[i] = (int32_t)(saturated[i] * saturation + desaturated[i] * inv_sat);
    }

    size_t stride = (size_t)width * 3;
    size_t error_row_size = stride * sizeof(int32_t);
    int32_t *error_buffer = be_os_malloc(error_row_size * 3);
    if (!error_buffer) {
        be_raise(vm, "memory_error", "cannot allocate dither error buffer");
    }
    memset(error_buffer, 0, error_row_size * 3);
    int32_t *row0_errors = error_buffer;
    int32_t *row1_errors = error_buffer + stride;
    int32_t *row2_errors = error_buffer + stride * 2;

    for (int32_t y = 0; y < height; y++) {
        int direction = (y & 1) ? -1 : 1;
        for (int32_t offset = 0; offset < width; offset++) {
            int32_t x = direction > 0 ? offset : width - 1 - offset;
            size_t column = (size_t)x * 3;
            size_t index = (size_t)y * stride + column;
            int32_t color[3];
            for (int channel = 0; channel < 3; channel++) {
                color[channel] = clamp_fixed((int32_t)pixels[index + channel] * 16 +
                                             divide_round_48(row0_errors[column + channel]));
            }
            int best = find_closest_color(color, palette);
            for (int channel = 0; channel < 3; channel++) {
                int32_t error = color[channel] - palette[best * 3 + channel] * 16;
                pixels[index + channel] = (uint8_t)desaturated[best * 3 + channel];
                if (strength_fixed != 256) {
                    error = error * strength_fixed / 256;
                }
                if (offset + 1 < width) {
                    row0_errors[(size_t)(x + direction) * 3 + channel] += error * 7;
                    if (offset + 2 < width) {
                        row0_errors[(size_t)(x + 2 * direction) * 3 + channel] += error * 5;
                    }
                }
                if (y + 1 < height) {
                    if (x >= 2) row1_errors[(size_t)(x - 2) * 3 + channel] += error * 3;
                    if (x >= 1) row1_errors[(size_t)(x - 1) * 3 + channel] += error * 5;
                    row1_errors[column + channel] += error * 7;
                    if (x + 1 < width) row1_errors[(size_t)(x + 1) * 3 + channel] += error * 5;
                    if (x + 2 < width) row1_errors[(size_t)(x + 2) * 3 + channel] += error * 3;
                }
                if (y + 2 < height) {
                    if (x >= 2) row2_errors[(size_t)(x - 2) * 3 + channel] += error * 1;
                    if (x >= 1) row2_errors[(size_t)(x - 1) * 3 + channel] += error * 3;
                    row2_errors[column + channel] += error * 5;
                    if (x + 1 < width) row2_errors[(size_t)(x + 1) * 3 + channel] += error * 3;
                    if (x + 2 < width) row2_errors[(size_t)(x + 2) * 3 + channel] += error * 1;
                }
            }
        }
        int32_t *temp = row0_errors;
        row0_errors = row1_errors;
        row1_errors = row2_errors;
        row2_errors = temp;
        memset(row2_errors, 0, error_row_size);
        if (y % 16 == 0) {
            yield();
        }
    }
    be_os_free(error_buffer);

    be_return_nil(vm);
}

#include "be_fixed_be_class_inky_dither.h"

/* @const_object_info_begin
class be_class_inky_dither (scope: global, name: InkyDither) {
    dither, static_func(m_inky_dither_dither)
}
@const_object_info_end */

#endif // USE_BERRY_IMAGE
