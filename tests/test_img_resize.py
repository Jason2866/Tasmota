#!/usr/bin/env python3
"""Test the native RGB888 resampler against an independent exact reference."""

import ctypes
from fractions import Fraction
from pathlib import Path
import random
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "lib/libesp32/berry_tasmota/src/be_img_resize.h"
IMAGE_SOURCE = ROOT / "tasmota/tasmota_xdrv_driver/xdrv_52_3_berry_img.ino"
HARNESS = r"""
#include "be_img_resize.h"
#include <cstdlib>
#include <cstring>
static unsigned int service_calls;
static void service() { ++service_calls; }
extern "C" int resize(const uint8_t *input, uint16_t source_width, uint16_t source_height,
                      uint8_t *output, uint16_t target_width, uint16_t target_height) {
    service_calls = 0;
    return be_img_resize_rgb888(input, source_width, source_height,
                                output, target_width, target_height, service);
}
extern "C" unsigned int services() { return service_calls; }
extern "C" int decode_scale(uint16_t width, uint16_t height, uint8_t bpp,
                            size_t free_memory, size_t largest_block,
                            uint16_t target_width, uint16_t target_height) {
    return be_img_decode_scale(width, height, bpp, free_memory, largest_block,
                               target_width, target_height);
}
extern "C" size_t compact_decode_size(uint16_t width, uint16_t height,
                                      uint16_t target_width, uint16_t target_height,
                                      size_t free_memory, size_t largest_block) {
    return be_img_compact_decode_size(width, height, target_width, target_height,
                                      free_memory, largest_block);
}
extern "C" int resize_compact(uint8_t *pixels, uint16_t source_width, uint16_t source_height,
                              uint16_t target_width, uint16_t target_height) {
    return be_img_resize_rgb565_inplace(pixels, source_width, source_height,
                                       target_width, target_height, service);
}

enum { PIXFORMAT_RGB888 = 5, MALLOC_CAP_SPIRAM = 1, MALLOC_CAP_8BIT = 2 };
struct image_t {
    uint8_t *buf;
    size_t len;
    uint16_t width, height;
    uint8_t bpp;
    int format;
};
struct bvm {
    image_t *image;
    int32_t target_width, target_height;
};
static bool fail_allocation;
static int allocations;
static int be_top(bvm *) { return 3; }
static bool be_isint(bvm *, int) { return true; }
static int32_t be_toint(bvm *vm, int index) {
    return index == 2 ? vm->target_width : vm->target_height;
}
static image_t *be_get_image_instance(bvm *vm) { return vm->image; }
static void be_raise(bvm *, const char *, const char *) { throw 1; }
static void *heap_caps_malloc(size_t size, int) {
    ++allocations;
    return fail_allocation ? nullptr : malloc(size);
}
static void *heap_caps_realloc(void *ptr, size_t size, int) {
    return fail_allocation ? nullptr : realloc(ptr, size);
}
static void BrTimeoutYield() { ++service_calls; }
static void OsWatchLoop() {}
static void yield() {}
#define be_return_nil(vm) return 0
#include "binding.inc"

extern "C" int resize_binding(uint8_t *data, size_t capacity, size_t declared_size,
                              uint16_t source_width, uint16_t source_height,
                              int target_width, int target_height, int format, int bpp,
                              int fail, size_t *result_size, int *result_width,
                              int *result_height, int *allocation_count) {
    uint8_t *pixels = (uint8_t *)malloc(capacity);
    if (!pixels) return -1;
    memcpy(pixels, data, capacity);
    image_t image = { pixels, declared_size, source_width, source_height,
                      (uint8_t)bpp, format };
    bvm vm = { &image, target_width, target_height };
    fail_allocation = fail;
    allocations = 0;
    service_calls = 0;
    int status = 0;
    try { be_img_resize(&vm); } catch (int) { status = 1; }
    *result_size = image.len;
    *result_width = image.width;
    *result_height = image.height;
    *allocation_count = allocations;
    size_t copy_size = image.len < capacity ? image.len : capacity;
    memcpy(data, image.buf, copy_size);
    free(image.buf);
    return status;
}
"""


def weights(position, source_size, target_size):
    if source_size > target_size:
        left = Fraction(position * source_size, target_size)
        right = Fraction((position + 1) * source_size, target_size)
        return [(index, max(Fraction(0), min(right, index + 1) - max(left, index)) /
                 (right - left)) for index in range(source_size)
                if min(right, index + 1) > max(left, index)]
    coordinate = Fraction((2 * position + 1) * source_size - target_size, 2 * target_size)
    coordinate = max(Fraction(0), min(Fraction(source_size - 1), coordinate))
    first = coordinate.numerator // coordinate.denominator
    fraction = coordinate - first
    return [(first, 1 - fraction), (min(first + 1, source_size - 1), fraction)]


def reference(data, source_width, source_height, target_width, target_height):
    result = bytearray()
    for y in range(target_height):
        for x in range(target_width):
            for channel in range(3):
                value = sum(data[(source_y * source_width + source_x) * 3 + channel] *
                            weight_x * weight_y
                            for source_y, weight_y in weights(y, source_height, target_height)
                            for source_x, weight_x in weights(x, source_width, target_width))
                result.append((value + Fraction(1, 2)).numerator //
                              (value + Fraction(1, 2)).denominator)
    return result


class ImageResizeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tempdir = tempfile.TemporaryDirectory()
        directory = Path(cls.tempdir.name)
        harness = directory / "harness.cpp"
        harness.write_text(HARNESS)
        source = IMAGE_SOURCE.read_text()
        start = source.index("  int be_img_resize(struct bvm *vm);")
        end = source.index("  /**", start)
        (directory / "binding.inc").write_text(source[start:end])
        library = directory / "resize.so"
        subprocess.run(["c++", "-std=c++11", "-Wall", "-Wextra", "-Werror", "-shared",
                        "-fPIC", "-I", str(HEADER.parent), str(harness), "-o", str(library)],
                       check=True)
        cls.lib = ctypes.CDLL(str(library))
        cls.lib.resize.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint16, ctypes.c_uint16,
                                   ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint16, ctypes.c_uint16]
        cls.lib.resize.restype = ctypes.c_int
        cls.lib.decode_scale.argtypes = [ctypes.c_uint16, ctypes.c_uint16, ctypes.c_uint8,
                                         ctypes.c_size_t, ctypes.c_size_t,
                                         ctypes.c_uint16, ctypes.c_uint16]
        cls.lib.decode_scale.restype = ctypes.c_int
        cls.lib.compact_decode_size.argtypes = [ctypes.c_uint16] * 4 + [ctypes.c_size_t] * 2
        cls.lib.compact_decode_size.restype = ctypes.c_size_t
        cls.lib.resize_compact.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint16] * 4
        cls.lib.resize_compact.restype = ctypes.c_int
        cls.lib.services.restype = ctypes.c_uint
        cls.lib.resize_binding.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t,
                                            ctypes.c_size_t, ctypes.c_uint16, ctypes.c_uint16,
                                            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                            ctypes.c_int, ctypes.POINTER(ctypes.c_size_t),
                                            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
                                            ctypes.POINTER(ctypes.c_int)]
        cls.lib.resize_binding.restype = ctypes.c_int

    @classmethod
    def tearDownClass(cls):
        cls.tempdir.cleanup()

    def resize(self, data, source_width, source_height, target_width, target_height):
        source = (ctypes.c_uint8 * len(data))(*data)
        storage = (ctypes.c_uint8 * (target_width * target_height * 3 + 2))()
        storage[0], storage[-1] = 83, 171
        output = ctypes.cast(ctypes.byref(storage, 1), ctypes.POINTER(ctypes.c_uint8))
        self.assertEqual(self.lib.resize(source, source_width, source_height, output,
                                         target_width, target_height), 1)
        self.assertEqual((storage[0], storage[-1]), (83, 171))
        self.assertEqual(bytearray(source), data)
        return bytearray(storage[1:-1])

    def test_exact_reference(self):
        generator = random.Random(2026)
        sizes = [(1, 1, 1, 1), (1, 7, 9, 3), (9, 1, 4, 8), (2, 2, 5, 5),
                 (3, 5, 8, 2), (7, 3, 2, 9), (8, 6, 3, 4), (5, 7, 5, 7)]
        sizes += [tuple(generator.randrange(1, 10) for _ in range(4)) for _ in range(35)]
        for source_width, source_height, target_width, target_height in sizes:
            data = bytearray(generator.randrange(256) for _ in range(source_width * source_height * 3))
            actual = self.resize(data, source_width, source_height, target_width, target_height)
            expected = reference(data, source_width, source_height, target_width, target_height)
            self.assertTrue(all(abs(a - b) <= 1 for a, b in zip(actual, expected)),
                            (source_width, source_height, target_width, target_height))

    def test_checkerboard_and_stripes(self):
        source = bytearray(channel for y in range(12) for x in range(12)
                           for channel in [255 * ((x + y) % 2)] * 3)
        self.assertEqual(self.resize(source, 12, 12, 3, 3), bytes([128] * 27))
        stripes = bytearray(channel for x in range(20) for channel in [255 * (x % 2)] * 3)
        self.assertEqual(self.resize(stripes, 20, 1, 1, 1), bytes([128, 128, 128]))

    def test_in_place_downscaling(self):
        generator = random.Random(2027)
        for source_width in range(1, 10):
            for source_height in range(1, 10):
                data = bytearray(generator.randrange(256) for _ in range(source_width * source_height * 3))
                for target_width in range(1, source_width + 1):
                    for target_height in range(1, source_height + 1):
                        expected = self.resize(data, source_width, source_height, target_width, target_height)
                        storage = (ctypes.c_uint8 * (len(data) + 2))(*([83] + list(data) + [171]))
                        pixels = ctypes.cast(ctypes.byref(storage, 1), ctypes.POINTER(ctypes.c_uint8))
                        self.assertEqual(self.lib.resize(pixels, source_width, source_height, pixels,
                                                         target_width, target_height), 1)
                        self.assertEqual(bytearray(storage[1:1 + len(expected)]), expected,
                                         (source_width, source_height, target_width, target_height))
                        self.assertEqual((storage[0], storage[-1]), (83, 171))

    def test_decode_scale_respects_resize_and_memory(self):
        scale = self.lib.decode_scale
        self.assertEqual(scale(600, 923, 3, 2400000, 2000000, 0, 0), 2)
        self.assertEqual(scale(600, 923, 3, 2400000, 2000000, 480, 800), 0)
        self.assertEqual(scale(600, 923, 3, 2400000, 1000000, 480, 800), 2)
        self.assertEqual(scale(600, 923, 3, 1900000, 1900000, 480, 800), 2)
        self.assertEqual(scale(600, 923, 3, 2400000, 2000000, 700, 800), 2)
        self.assertEqual(scale(1500, 1000, 3, 4000000, 4000000, 2000, 1000), -1)
        self.assertEqual(scale(600, 923, 3, 300000, 300000, 480, 800), -1)
        self.assertEqual(scale(65535, 65535, 3, 1000000, 1000000, 480, 800), -1)

    def test_compact_decode_selection(self):
        size = self.lib.compact_decode_size
        self.assertEqual(size(600, 923, 480, 800, 1600000, 1200000), 1152000)
        self.assertEqual(size(600, 923, 480, 800, 1400000, 1200000), 0)
        self.assertEqual(size(600, 923, 480, 800, 1600000, 1100000), 0)
        self.assertEqual(size(600, 923, 700, 800, 3000000, 3000000), 0)
        self.assertEqual(size(600, 923, 0, 800, 3000000, 3000000), 0)

    def test_compact_resize_against_reference(self):
        generator = random.Random(812)
        for source_width in range(1, 7):
            for source_height in range(1, 7):
                colors = [generator.randrange(65536) for _ in range(source_width * source_height)]
                source = bytearray(channel for color in colors for channel in (color >> 8, color & 255))
                for target_width in range(1, source_width + 1):
                    for target_height in range(1, source_height + 1):
                        length = max(len(source), target_width * target_height * 3)
                        storage = (ctypes.c_uint8 * (length + 2))()
                        storage[0], storage[-1] = 83, 171
                        storage[1:1 + len(source)] = source
                        pixels = ctypes.cast(ctypes.byref(storage, 1), ctypes.POINTER(ctypes.c_uint8))
                        self.assertEqual(self.lib.resize_compact(pixels, source_width, source_height,
                                                                 target_width, target_height), 1)
                        expected = bytearray()
                        for target_row in range(target_height):
                            for target_column in range(target_width):
                                values = []
                                for shift, mask in ((11, 31), (5, 63), (0, 31)):
                                    value = sum(((colors[sy * source_width + sx] >> shift) & mask) * wx * wy
                                                for sy, wy in weights(target_row, source_height, target_height)
                                                for sx, wx in weights(target_column, source_width, target_width))
                                    values.append((value + Fraction(1, 2)).numerator //
                                                  (value + Fraction(1, 2)).denominator)
                                expected.extend(((values[0] << 3) | (values[0] >> 2),
                                                 (values[1] << 2) | (values[1] >> 4),
                                                 (values[2] << 3) | (values[2] >> 2)))
                        self.assertEqual(bytes(storage[1:1 + len(expected)]), expected,
                                         (source_width, source_height, target_width, target_height))
                        self.assertEqual((storage[0], storage[-1]), (83, 171))

    def test_solid_colors_and_large_dimensions(self):
        for size in ((1, 1, 17, 15), (11, 9, 3, 2), (12, 3, 2, 12)):
            source_width, source_height, target_width, target_height = size
            data = bytearray([17, 123, 255] * source_width * source_height)
            self.assertEqual(self.resize(data, *size), bytes([17, 123, 255] * target_width * target_height))
        data = bytearray([17, 123, 255] * 65535)
        self.assertEqual(self.resize(data, 65535, 1, 1, 1), bytes([17, 123, 255]))
        self.assertGreater(self.lib.services(), 0)
        self.assertEqual(self.resize(data, 65535, 1, 65534, 1), bytes([17, 123, 255] * 65534))
        self.assertEqual(self.resize(data[:65534 * 3], 65534, 1, 65535, 1),
                         bytes([17, 123, 255] * 65535))
        self.assertEqual(self.resize(bytes([17, 123, 255]), 1, 1, 65535, 1),
                         bytes([17, 123, 255] * 65535))
        self.assertGreater(self.lib.services(), 0)

    def test_invalid_arguments(self):
        source = (ctypes.c_uint8 * 3)(1, 2, 3)
        output = (ctypes.c_uint8 * 3)(4, 5, 6)
        for args in ((None, 1, 1, output, 1, 1), (source, 0, 1, output, 1, 1),
                     (source, 1, 0, output, 1, 1), (source, 1, 1, None, 1, 1),
                     (source, 1, 1, output, 0, 1), (source, 1, 1, output, 1, 0)):
            self.assertEqual(self.lib.resize(*args), 0)
            self.assertEqual(bytes(output), bytes([4, 5, 6]))

    def test_binding_validation_and_transactionality(self):
        original = bytes(range(12))
        for declared_size, width, height, target_width, target_height, image_format, bpp, fail, status in (
            (12, 2, 2, 2, 2, 5, 3, 0, 0),
            (11, 2, 2, 2, 2, 5, 3, 0, 1),
            (11, 2, 2, 1, 1, 5, 3, 0, 1),
            (12, 2, 2, 3, 1, 5, 3, 1, 1),
            (12, 2, 2, 0, 1, 5, 3, 0, 1),
            (12, 2, 2, 65536, 1, 5, 3, 0, 1),
            (12, 2, 2, 1, 1, 1, 3, 0, 1),
            (12, 2, 2, 1, 1, 5, 2, 0, 1),
        ):
            data = (ctypes.c_uint8 * len(original))(*original)
            size, out_width, out_height, allocations = (ctypes.c_size_t(), ctypes.c_int(),
                                                         ctypes.c_int(), ctypes.c_int())
            result = self.lib.resize_binding(data, len(original), declared_size, width, height,
                                             target_width, target_height, image_format, bpp, fail,
                                             ctypes.byref(size), ctypes.byref(out_width),
                                             ctypes.byref(out_height), ctypes.byref(allocations))
            self.assertEqual(result, status)
            self.assertEqual((size.value, out_width.value, out_height.value),
                             (declared_size, width, height))
            self.assertEqual(bytes(data), original)
            self.assertEqual(allocations.value, int(bool(fail)))

        data = (ctypes.c_uint8 * len(original))(*original)
        size, width, height, allocations = ctypes.c_size_t(), ctypes.c_int(), ctypes.c_int(), ctypes.c_int()
        self.assertEqual(self.lib.resize_binding(data, len(original), 12, 2, 2, 1, 1, 5, 3, 0,
                                                 ctypes.byref(size), ctypes.byref(width),
                                                 ctypes.byref(height), ctypes.byref(allocations)), 0)
        self.assertEqual((size.value, width.value, height.value, allocations.value), (3, 1, 1, 0))
        self.assertEqual(bytes(data)[:3], bytes([5, 6, 7]))

        data = (ctypes.c_uint8 * len(original))(*original)
        self.assertEqual(self.lib.resize_binding(data, len(original), 12, 2, 2, 1, 1, 5, 3, 1,
                                                 ctypes.byref(size), ctypes.byref(width),
                                                 ctypes.byref(height), ctypes.byref(allocations)), 0)
        self.assertEqual((size.value, width.value, height.value, allocations.value), (3, 1, 1, 0))
        self.assertEqual(bytes(data)[:3], bytes([5, 6, 7]))

        data = (ctypes.c_uint8 * (128 * 128 * 3))(*([128] * (128 * 128 * 3)))
        self.assertEqual(self.lib.resize_binding(data, len(data), len(data), 128, 128, 64, 64, 5, 3, 0,
                                                 ctypes.byref(size), ctypes.byref(width),
                                                 ctypes.byref(height), ctypes.byref(allocations)), 0)
        self.assertGreater(self.lib.services(), 0)


if __name__ == "__main__":
    unittest.main()
