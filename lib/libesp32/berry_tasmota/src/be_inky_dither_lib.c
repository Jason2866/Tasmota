/********************************************************************
 * Berry class `inky_dither`
 * 
 * Floyd-Steinberg dithering for Inky Impression 7.3 (E673 / Spectra 6).
 * Optimized C implementation for performance.
 *******************************************************************/
#include "be_constobj.h"
#include "be_mem.h"
#include "be_exec.h"
#include "be_byteslib.h"

#ifdef USE_BERRY_IMAGE

// Helper function to clamp value to 0-255 range
static inline int32_t clamp_byte(int32_t value) {
    if (value < 0) return 0;
    if (value > 255) return 255;
    return value;
}

// Helper function to compute absolute value
static inline int32_t abs_value(int32_t value) {
    return value < 0 ? -value : value;
}

// Helper function to compute squared distance
static inline int32_t squared_distance(int32_t r1, int32_t g1, int32_t b1,
                                       int32_t r2, int32_t g2, int32_t b2) {
    int32_t dr = r1 - r2;
    int32_t dg = g1 - g2;
    int32_t db = b1 - b2;
    return dr * dr + dg * dg + db * db;
}

// Find the closest palette color to the given RGB value
static void find_closest_color(int32_t red, int32_t green, int32_t blue,
                                const int32_t *palette,
                                int32_t *best_r, int32_t *best_g, int32_t *best_b,
                                int32_t *id_r, int32_t *id_g, int32_t *id_b) {
    int32_t best_d = squared_distance(red, green, blue, palette[0], palette[1], palette[2]);
    *best_r = palette[0];
    *best_g = palette[1];
    *best_b = palette[2];
    *id_r = 0;
    *id_g = 0;
    *id_b = 0;

    // Check against each palette color
    for (int i = 1; i < 6; i++) {
        int32_t d = squared_distance(red, green, blue,
                                     palette[i * 3], palette[i * 3 + 1], palette[i * 3 + 2]);
        if (d < best_d) {
            best_d = d;
            *best_r = palette[i * 3];
            *best_g = palette[i * 3 + 1];
            *best_b = palette[i * 3 + 2];
            // Set the ID color based on palette index
            if (i == 1) { *id_r = 255; *id_g = 255; *id_b = 255; }
            else if (i == 2) { *id_r = 255; *id_g = 255; *id_b = 0; }
            else if (i == 3) { *id_r = 255; *id_g = 0; *id_b = 0; }
            else if (i == 4) { *id_r = 0; *id_g = 0; *id_b = 255; }
            else if (i == 5) { *id_r = 0; *id_g = 255; *id_b = 0; }
        }
    }
}

// InkyDither.dither(pixels:bytes(), width:int, height:int, saturation:float) -> nil
//
// Perform Floyd-Steinberg dithering on the RGB888 pixel buffer in-place.
// pixels: bytes object containing RGB888 data (3 bytes per pixel)
// width: image width in pixels (must be 800)
// height: image height in pixels (must be 480)
// saturation: saturation value between 0.0 and 1.0 (default 0.5)
int m_inky_dither_dither(bvm *vm);
int m_inky_dither_dither(bvm *vm) {
    int32_t argc = be_top(vm);
    
    // Check arguments
    if (argc < 4 || !be_isbytes(vm, 2) || !be_isint(vm, 3) || !be_isint(vm, 4)) {
        be_raise(vm, "value_error", "Expected bytes, width, height as arguments");
    }
    
    // Get saturation (optional, default 0.5)
    float saturation = 0.5f;
    if (argc >= 5) {
        if (be_isnumber(vm, 5)) {
            saturation = be_toreal(vm, 5);
            if (saturation < 0.0f || saturation > 1.0f) {
                be_raise(vm, "value_error", "saturation must be between 0.0 and 1.0");
            }
        } else if (!be_isnil(vm, 5)) {
            be_raise(vm, "value_error", "saturation must be a number or nil");
        }
    }
    
    // Get width and height
    int32_t width = be_toint(vm, 3);
    int32_t height = be_toint(vm, 4);
    
    if (width != 800 || height != 480) {
        be_raise(vm, "value_error", "image must be 800x480");
    }
    
    // Get pixel buffer
    size_t pixel_size = 0;
    uint8_t *pixels = (uint8_t *) be_tobytes(vm, 2, &pixel_size);
    if (!pixels || pixel_size != width * height * 3) {
        be_raise(vm, "value_error", "invalid pixel buffer size");
    }
    
    // Calculate palette based on saturation
    const int32_t saturated[18] = {
        0, 0, 0, 161, 164, 165, 208, 190, 71,
        156, 72, 75, 61, 59, 94, 58, 91, 70
    };
    const int32_t desaturated[18] = {
        0, 0, 0, 255, 255, 255, 255, 255, 0,
        255, 0, 0, 0, 0, 255, 0, 255, 0
    };
    
    float inv_sat = 1.0f - saturation;
    int32_t palette[18];
    for (int i = 0; i < 18; i++) {
        palette[i] = (int32_t)(saturated[i] * saturation + desaturated[i] * inv_sat);
    }
    
    int32_t stride = width * 3;
    int32_t last_x = width - 1;
    int32_t last_y = height - 1;
    
    // Floyd-Steinberg dithering loop
    for (int32_t y = 0; y < height; y++) {
        for (int32_t x = 0; x < width; x++) {
            int32_t index = y * stride + x * 3;
            
            // Get current pixel
            int32_t red = pixels[index];
            int32_t green = pixels[index + 1];
            int32_t blue = pixels[index + 2];
            
            // Find closest palette color
            int32_t pal_r, pal_g, pal_b;
            int32_t id_r, id_g, id_b;
            find_closest_color(red, green, blue, palette,
                             &pal_r, &pal_g, &pal_b,
                             &id_r, &id_g, &id_b);
            
            // Write the quantized color (ID color)
            pixels[index] = id_r;
            pixels[index + 1] = id_g;
            pixels[index + 2] = id_b;
            
            // Calculate error
            int32_t error_red = red - pal_r;
            int32_t error_green = green - pal_g;
            int32_t error_blue = blue - pal_b;
            
            // Calculate Floyd-Steinberg weights (without floats)
            int32_t ar = abs_value(error_red);
            int32_t ag = abs_value(error_green);
            int32_t ab = abs_value(error_blue);
            
            int32_t e7r = (ar * 7) >> 4;
            int32_t e5r = (ar * 5) >> 4;
            int32_t e3r = (ar * 3) >> 4;
            int32_t e1r = ar >> 4;
            
            int32_t e7g = (ag * 7) >> 4;
            int32_t e5g = (ag * 5) >> 4;
            int32_t e3g = (ag * 3) >> 4;
            int32_t e1g = ag >> 4;
            
            int32_t e7b = (ab * 7) >> 4;
            int32_t e5b = (ab * 5) >> 4;
            int32_t e3b = (ab * 3) >> 4;
            int32_t e1b = ab >> 4;
            
            if (error_red < 0) {
                e7r = -e7r; e5r = -e5r; e3r = -e3r; e1r = -e1r;
            }
            if (error_green < 0) {
                e7g = -e7g; e5g = -e5g; e3g = -e3g; e1g = -e1g;
            }
            if (error_blue < 0) {
                e7b = -e7b; e5b = -e5b; e3b = -e3b; e1b = -e1b;
            }
            
            // Distribute error to neighboring pixels
            int32_t next, down;
            int32_t r, g, b;
            
            if (y < last_y && x > 0 && x < last_x) {
                // Right pixel (7/16)
                next = index + 3;
                r = clamp_byte(pixels[next] + e7r);
                g = clamp_byte(pixels[next + 1] + e7g);
                b = clamp_byte(pixels[next + 2] + e7b);
                pixels[next] = r;
                pixels[next + 1] = g;
                pixels[next + 2] = b;
                
                // Down-left pixel (3/16)
                next = index + stride - 3;
                r = clamp_byte(pixels[next] + e3r);
                g = clamp_byte(pixels[next + 1] + e3g);
                b = clamp_byte(pixels[next + 2] + e3b);
                pixels[next] = r;
                pixels[next + 1] = g;
                pixels[next + 2] = b;
                
                // Down pixel (5/16)
                next = index + stride;
                r = clamp_byte(pixels[next] + e5r);
                g = clamp_byte(pixels[next + 1] + e5g);
                b = clamp_byte(pixels[next + 2] + e5b);
                pixels[next] = r;
                pixels[next + 1] = g;
                pixels[next + 2] = b;
                
                // Down-right pixel (1/16)
                next = index + stride + 3;
                r = clamp_byte(pixels[next] + e1r);
                g = clamp_byte(pixels[next + 1] + e1g);
                b = clamp_byte(pixels[next + 2] + e1b);
                pixels[next] = r;
                pixels[next + 1] = g;
                pixels[next + 2] = b;
            } else {
                // Edge cases
                if (x < last_x) {
                    // Right pixel (7/16)
                    next = index + 3;
                    r = clamp_byte(pixels[next] + e7r);
                    g = clamp_byte(pixels[next + 1] + e7g);
                    b = clamp_byte(pixels[next + 2] + e7b);
                    pixels[next] = r;
                    pixels[next + 1] = g;
                    pixels[next + 2] = b;
                }
                
                if (y < last_y) {
                    down = index + stride;
                    if (x > 0) {
                        // Down-left pixel (3/16)
                        next = down - 3;
                        r = clamp_byte(pixels[next] + e3r);
                        g = clamp_byte(pixels[next + 1] + e3g);
                        b = clamp_byte(pixels[next + 2] + e3b);
                        pixels[next] = r;
                        pixels[next + 1] = g;
                        pixels[next + 2] = b;
                    }
                    
                    // Down pixel (5/16)
                    r = clamp_byte(pixels[down] + e5r);
                    g = clamp_byte(pixels[down + 1] + e5g);
                    b = clamp_byte(pixels[down + 2] + e5b);
                    pixels[down] = r;
                    pixels[down + 1] = g;
                    pixels[down + 2] = b;
                    
                    if (x < last_x) {
                        // Down-right pixel (1/16)
                        next = down + 3;
                        r = clamp_byte(pixels[next] + e1r);
                        g = clamp_byte(pixels[next + 1] + e1g);
                        b = clamp_byte(pixels[next + 2] + e1b);
                        pixels[next] = r;
                        pixels[next + 1] = g;
                        pixels[next + 2] = b;
                    }
                }
            }
        }
        
        // Yield every 16 rows to allow other tasks to run
        if (y % 16 == 0) {
            yield();
        }
    }
    
    be_return_nil(vm);
}

#include "be_fixed_be_class_inky_dither.h"

/* @const_object_info_begin
class be_class_inky_dither (scope: global, name: InkyDither) {
    dither, func(m_inky_dither_dither)
}
@const_object_info_end */

#endif // USE_BERRY_IMAGE
