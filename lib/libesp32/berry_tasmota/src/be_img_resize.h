#ifndef BE_IMG_RESIZE_H
#define BE_IMG_RESIZE_H

#include <stddef.h>
#include <stdint.h>

struct be_img_resize_span {
  uint32_t first;
  uint32_t last;
  uint32_t first_weight;
  uint32_t last_weight;
  uint32_t unit;
  uint32_t total;
};

static inline be_img_resize_span be_img_resize_get_span(uint32_t position, uint32_t source_size,
                                                        uint32_t target_size) {
  if (source_size == target_size) {
    return { position, position, 1, 1, 1, 1 };
  }
  if (source_size == 1) {
    return { 0, 0, 1, 1, 1, 1 };
  }
  if (source_size > target_size) {
    uint32_t start = position * source_size;
    uint32_t end = (position + 1) * source_size;
    uint32_t first = start / target_size;
    uint32_t last = (end - 1) / target_size;
    return { first, last, (first + 1) * target_size - start,
             end - last * target_size, target_size, source_size };
  }

  uint32_t scaled_position = position * source_size;
  uint32_t first = scaled_position / target_size;
  int32_t fraction = (int32_t)((scaled_position % target_size) * 2 + source_size) -
                     (int32_t)target_size;
  uint32_t total = target_size * 2;
  if (fraction < 0) {
    if (first == 0) return { 0, 0, 1, 1, 1, 1 };
    --first;
    fraction += total;
  }
  if (first >= source_size - 1) {
    return { source_size - 1, source_size - 1, 1, 1, 1, 1 };
  }
  uint32_t last_weight = fraction;
  return { first, first + 1, total - last_weight, last_weight, 0, total };
}

static inline uint32_t be_img_resize_weight(const be_img_resize_span &span, uint32_t position) {
  if (span.first == span.last) return span.total;
  if (position == span.first) return span.first_weight;
  if (position == span.last) return span.last_weight;
  return span.unit;
}

static inline bool be_img_resize_rgb888(const uint8_t *source, uint16_t source_width,
                                         uint16_t source_height, uint8_t *output,
                                         uint16_t target_width, uint16_t target_height,
                                         void (*service)(void)) {
  if (!source || !output || !source_width || !source_height || !target_width || !target_height ||
      (size_t)source_width > SIZE_MAX / 3 / source_height ||
      (size_t)target_width > SIZE_MAX / 3 / target_height) {
    return false;
  }

  uint32_t samples = 0;
  for (uint32_t y = 0; y < target_height; ++y) {
    be_img_resize_span vertical = be_img_resize_get_span(y, source_height, target_height);
    for (uint32_t x = 0; x < target_width; ++x) {
      be_img_resize_span horizontal = be_img_resize_get_span(x, source_width, target_width);
      float result[3] = { 0, 0, 0 };
      float horizontal_scale = 1.0f / horizontal.total;
      for (uint32_t source_y = vertical.first; source_y <= vertical.last; ++source_y) {
        float row[3] = { 0, 0, 0 };
        for (uint32_t source_x = horizontal.first; source_x <= horizontal.last; ++source_x) {
          const uint8_t *pixel = source + ((size_t)source_y * source_width + source_x) * 3;
          uint32_t weight = be_img_resize_weight(horizontal, source_x);
          for (int channel = 0; channel < 3; ++channel) {
            row[channel] += pixel[channel] * weight;
          }
          if (service && (++samples & 0x3fff) == 0) service();
        }
        float weight = be_img_resize_weight(vertical, source_y) * horizontal_scale;
        for (int channel = 0; channel < 3; ++channel) {
          result[channel] += row[channel] * weight;
        }
      }
      size_t target_offset = ((size_t)y * target_width + x) * 3;
      for (int channel = 0; channel < 3; ++channel) {
        float value = result[channel] / vertical.total;
        if (value > 255.0f) value = 255.0f;
        output[target_offset + channel] = (uint8_t)(value + 0.5f);
      }
    }
  }
  return true;
}

#endif
