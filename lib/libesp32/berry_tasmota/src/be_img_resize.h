#ifndef BE_IMG_RESIZE_H
#define BE_IMG_RESIZE_H

#include <stddef.h>
#include <stdint.h>

static inline int be_img_decode_scale(uint16_t width, uint16_t height, uint8_t bpp,
                                      size_t free_psram, size_t largest_block,
                                      uint16_t target_width, uint16_t target_height) {
  const uint32_t divisors[] = {1, 2, 4, 8};
  for (size_t index = 0; index < sizeof(divisors) / sizeof(divisors[0]); ++index) {
    uint32_t divisor = divisors[index];
    uint32_t scaled_width = ((uint32_t)width + divisor - 1) / divisor;
    uint32_t scaled_height = ((uint32_t)height + divisor - 1) / divisor;
    bool has_target = target_width && target_height;
    bool in_place = has_target && scaled_width >= target_width && scaled_height >= target_height;
    uint64_t reserve = has_target ? 300000 : (free_psram < 3000000 ? 1300000 : 0);
    if (has_target && !in_place) reserve += (uint64_t)target_width * target_height * bpp;
    size_t max_allowed = free_psram > reserve ? free_psram - (size_t)reserve : (has_target ? 0 : 500000);
    if (max_allowed > largest_block) max_allowed = largest_block;
    if ((uint64_t)scaled_width * scaled_height * bpp <= max_allowed) {
      return divisor == 1 ? 0 : (int)divisor;
    }
  }
  return -1;
}

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

static inline size_t be_img_compact_decode_size(uint16_t source_width, uint16_t source_height,
                                                 uint16_t target_width, uint16_t target_height,
                                                 size_t free_psram, size_t largest_block) {
  if (!target_width || !target_height || source_width < target_width || source_height < target_height) return 0;
  uint64_t source_size = (uint64_t)source_width * source_height * 2;
  uint64_t output_size = (uint64_t)target_width * target_height * 3;
  uint64_t size = source_size > output_size ? source_size : output_size;
  return size <= largest_block && size + 300000 <= free_psram ? (size_t)size : 0;
}

static inline bool be_img_resize_rgb565_inplace(uint8_t *pixels, uint16_t source_width,
                                                uint16_t source_height, uint16_t target_width,
                                                uint16_t target_height, void (*service)(void)) {
  if (!pixels || !target_width || !target_height || source_width < target_width ||
      source_height < target_height || (size_t)source_width > SIZE_MAX / 2 / source_height ||
      (size_t)target_width > SIZE_MAX / 3 / target_height) return false;
  uint32_t samples = 0;
  for (uint32_t target_row = 0; target_row < target_height; ++target_row) {
    be_img_resize_span vertical = be_img_resize_get_span(target_row, source_height, target_height);
    for (uint32_t target_column = 0; target_column < target_width; ++target_column) {
      be_img_resize_span horizontal = be_img_resize_get_span(target_column, source_width, target_width);
      float result[3] = {0, 0, 0};
      for (uint32_t source_y = vertical.first; source_y <= vertical.last; ++source_y) {
        float row[3] = {0, 0, 0};
        for (uint32_t source_x = horizontal.first; source_x <= horizontal.last; ++source_x) {
          size_t offset = ((size_t)source_y * source_width + source_x) * 2;
          uint16_t color = ((uint16_t)pixels[offset] << 8) | pixels[offset + 1];
          uint32_t weight = be_img_resize_weight(horizontal, source_x);
          row[0] += ((color >> 11) & 31) * weight;
          row[1] += ((color >> 5) & 63) * weight;
          row[2] += (color & 31) * weight;
          if (service && (++samples & 0x3fff) == 0) service();
        }
        float weight = (float)be_img_resize_weight(vertical, source_y) / horizontal.total;
        for (int channel = 0; channel < 3; ++channel) result[channel] += row[channel] * weight;
      }
      uint16_t red = (uint16_t)(result[0] / vertical.total + 0.5f);
      uint16_t green = (uint16_t)(result[1] / vertical.total + 0.5f);
      uint16_t blue = (uint16_t)(result[2] / vertical.total + 0.5f);
      uint16_t color = (red << 11) | (green << 5) | blue;
      size_t offset = ((size_t)target_row * target_width + target_column) * 2;
      pixels[offset] = color >> 8;
      pixels[offset + 1] = color;
    }
  }
  for (size_t index = (size_t)target_width * target_height; index > 0;) {
    --index;
    uint16_t color = ((uint16_t)pixels[index * 2] << 8) | pixels[index * 2 + 1];
    uint8_t red = (color >> 11) & 31, green = (color >> 5) & 63, blue = color & 31;
    pixels[index * 3] = (red << 3) | (red >> 2);
    pixels[index * 3 + 1] = (green << 2) | (green >> 4);
    pixels[index * 3 + 2] = (blue << 3) | (blue >> 2);
    if (service && (index & 0x3fff) == 0) service();
  }
  return true;
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
