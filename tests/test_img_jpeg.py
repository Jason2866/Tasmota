#!/usr/bin/env python3
"""Exercise the memory-conscious JPEG decode and file output paths."""

import ctypes
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_img_resize import reference


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tasmota/tasmota_xdrv_driver/xdrv_52_3_berry_img.ino"
JPEGDEC = ROOT / "lib/libesp32/JPEGDEC/src"
FIXTURE = ROOT / "lib/libesp32/JPEGDEC/examples/M5Stack/ncc1701.jpg"

HARNESS = r"""
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <algorithm>
#include "JPEGDEC.h"
#include "be_img_resize.h"

struct DecodeContext { uint8_t *pixels; int width; int bpp; };
static int draw(JPEGDRAW *block) {
    auto *ctx = (DecodeContext *)block->pUser;
    for (int row = 0; row < block->iHeight; ++row) {
        auto *src = (const uint8_t *)block->pPixels + row * block->iWidth * ctx->bpp;
        auto *dst = ctx->pixels + ((block->y + row) * ctx->width + block->x) * ctx->bpp;
        memcpy(dst, src, block->iWidthUsed * ctx->bpp);
    }
    return 1;
}
extern "C" int dimensions(uint8_t *data, int size, int *width, int *height) {
    JPEGDEC jpeg;
    if (!jpeg.openRAM(data, size, draw)) return 0;
    *width = jpeg.getWidth(); *height = jpeg.getHeight(); jpeg.close(); return 1;
}
extern "C" int decode(uint8_t *data, int size, uint8_t *pixels, int width, int bpp) {
    JPEGDEC jpeg;
    DecodeContext ctx = {pixels, width, bpp};
    if (!jpeg.openRAM(data, size, draw)) return 0;
    jpeg.setUserPointer(&ctx);
    jpeg.setPixelType(bpp == 2 ? RGB565_BIG_ENDIAN : RGB8888);
    int ok = jpeg.decode(0, 0, 0);
    jpeg.close(); return ok;
}
extern "C" int decode_compact(uint8_t *data, int size, uint8_t *pixels,
                              int width, int height, int target_width, int target_height) {
    if (!decode(data, size, pixels, width, 2)) return 0;
    return be_img_resize_rgb565_inplace(pixels, width, height, target_width, target_height, nullptr);
}

#define USE_UFILESYS
#define MALLOC_CAP_INTERNAL 1
#define MALLOC_CAP_SPIRAM 2
#define MALLOC_CAP_8BIT 4
#define LOG_LEVEL_INFO 1
#define PSTR(value) value
static size_t heap_caps_get_free_size(int) { return 1000000; }
static size_t heap_caps_get_largest_free_block(int) { return 500000; }
static void AddLog(int, const char *, ...) {}
enum { PIXFORMAT_RGB888 = 5 };
struct image_t { uint8_t *buf; size_t len; int format, bpp; uint16_t width, height; };
struct bvm { image_t *image; int quality, result; };
static int mode, closed;
static uint8_t file_data[32];
static size_t file_size;
static int be_top(bvm *) { return 3; }
static bool be_isstring(bvm *, int) { return true; }
static bool be_isint(bvm *, int) { return true; }
static int be_toint(bvm *vm, int) { return vm->quality; }
static const char *be_tostring(bvm *, int) { return "/preview.tmp"; }
static image_t *be_get_image_instance(bvm *vm) { return vm->image; }
static void be_raise(bvm *, const char *type, const char *) { throw !strcmp(type, "io_error") ? 1 : 2; }
static void be_pushint(bvm *vm, int value) { vm->result = value; }
#define be_return_nil(vm) return 0
#define be_return(vm) return 0
static void *be_fopen(const char *, const char *) { return mode == 1 ? nullptr : file_data; }
static int be_fclose(void *) { ++closed; return 0; }
static size_t be_fwrite(void *, const void *data, size_t size) {
    if (mode == 2 && size) return size - 1;
    memcpy(file_data + file_size, data, size); file_size += size; return size;
}
struct be_img_util {
    static void rgb888_swap_red_blue(uint8_t *data, size_t size) {
        for (size_t index = 0; index < size; index += 3) std::swap(data[index], data[index + 2]);
    }
};
#include "callback.inc"
static bool fmt2jpg_cb(uint8_t *data, size_t, uint16_t, uint16_t, int, int,
                       size_t (*callback)(void *, size_t, const void *, size_t), void *ctx) {
    if (data[0] != 3 || data[1] != 2 || data[2] != 1) return false;
    if (mode == 3) return false;
    if (mode == 4) return true;
    const uint8_t first[] = {7, 8, 9};
    const uint8_t second[] = {10, 11};
    size_t written = callback(ctx, 0, first, sizeof(first));
    callback(ctx, mode == 5 ? 7 : written, second, sizeof(second));
    return true;
}
#include "binding.inc"
extern "C" int save(uint8_t *pixels, size_t length, int quality, int test_mode,
                    int *encoded_size, int *close_count, uint8_t *output) {
    image_t image = {pixels, length, PIXFORMAT_RGB888, 3, 2, 2};
    bvm vm = {&image, quality, 0};
    mode = test_mode; closed = 0; file_size = 0;
    int status = 0;
    try { be_img_save_jpg(&vm); } catch (int error) { status = error; }
    *encoded_size = vm.result; *close_count = closed;
    memcpy(output, file_data, file_size);
    return status;
}
"""


class ImageJpegTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tempdir = tempfile.TemporaryDirectory()
        directory = Path(cls.tempdir.name)
        source = SOURCE.read_text()
        start = source.index("typedef struct {\n    void *file;")
        end = source.index("#endif", start)
        (directory / "callback.inc").write_text(source[start:end])
        start = source.index("  int be_img_save_jpg(struct bvm *vm);")
        end = source.index("  /**", start)
        (directory / "binding.inc").write_text(source[start:end])
        (directory / "harness.cpp").write_text(HARNESS)
        (directory / "jpegdec_scalar.cpp").write_text(
            '#include "JPEGDEC.h"\n#undef HAS_NEON\n#include "JPEGDEC.cpp"\n')
        library = directory / "jpeg.so"
        subprocess.run(["c++", "-std=c++11", "-O2", "-shared", "-fPIC", "-DNO_SIMD", "-I", str(directory),
                        "-I", str(JPEGDEC), "-I", str(ROOT / "lib/libesp32/berry_tasmota/src"),
                        str(directory / "harness.cpp"),
                        str(directory / "jpegdec_scalar.cpp"), "-o", str(library)], check=True)
        cls.lib = ctypes.CDLL(str(library))
        byte_pointer = ctypes.POINTER(ctypes.c_uint8)
        int_pointer = ctypes.POINTER(ctypes.c_int)
        cls.lib.dimensions.argtypes = [byte_pointer, ctypes.c_int, int_pointer, int_pointer]
        cls.lib.decode.argtypes = [byte_pointer, ctypes.c_int, byte_pointer, ctypes.c_int, ctypes.c_int]
        cls.lib.decode_compact.argtypes = [byte_pointer, ctypes.c_int, byte_pointer] + [ctypes.c_int] * 4
        cls.lib.save.argtypes = [byte_pointer, ctypes.c_size_t, ctypes.c_int, ctypes.c_int,
                                 int_pointer, int_pointer, byte_pointer]

    @classmethod
    def tearDownClass(cls):
        cls.tempdir.cleanup()

    def test_jpegdec_rgb565_matches_rgb888_channels(self):
        data = FIXTURE.read_bytes()
        jpeg = (ctypes.c_uint8 * len(data)).from_buffer_copy(data)
        width, height = ctypes.c_int(), ctypes.c_int()
        self.assertEqual(self.lib.dimensions(jpeg, len(data), ctypes.byref(width), ctypes.byref(height)), 1)
        count = width.value * height.value
        rgb565 = (ctypes.c_uint8 * (count * 2))()
        rgba = (ctypes.c_uint8 * (count * 4))()
        self.assertEqual(self.lib.decode(jpeg, len(data), rgb565, width.value, 2), 1)
        self.assertEqual(self.lib.decode(jpeg, len(data), rgba, width.value, 4), 1)
        for index in range(count):
            color = rgb565[index * 2] << 8 | rgb565[index * 2 + 1]
            self.assertEqual((color >> 11, (color >> 5) & 63, color & 31),
                             (rgba[index * 4] >> 3, rgba[index * 4 + 1] >> 2,
                              rgba[index * 4 + 2] >> 3))

    def test_full_resolution_compact_decode_and_resize(self):
        data = FIXTURE.read_bytes()
        jpeg = (ctypes.c_uint8 * len(data)).from_buffer_copy(data)
        width, height = ctypes.c_int(), ctypes.c_int()
        self.assertEqual(self.lib.dimensions(jpeg, len(data), ctypes.byref(width), ctypes.byref(height)), 1)
        target_width, target_height = 120, 38
        count = width.value * height.value
        rgba = (ctypes.c_uint8 * (count * 4))()
        self.assertEqual(self.lib.decode(jpeg, len(data), rgba, width.value, 4), 1)
        rgb = bytearray(channel for index in range(count) for channel in rgba[index * 4:index * 4 + 3])
        expected = reference(rgb, width.value, height.value, target_width, target_height)
        capacity = max(count * 2, target_width * target_height * 3)
        output = (ctypes.c_uint8 * capacity)()
        self.assertEqual(self.lib.decode_compact(jpeg, len(data), output, width.value, height.value,
                                                 target_width, target_height), 1)
        self.assertLessEqual(max(abs(actual - wanted) for actual, wanted in zip(output, expected)), 12)

    def test_streamed_jpeg_and_failures(self):
        original = bytes([1, 2, 3] * 4)
        for mode, quality, length, expected, closes in (
            (0, 85, 12, 0, 1), (1, 85, 12, 1, 0), (2, 85, 12, 1, 1),
            (3, 85, 12, 2, 1), (4, 85, 12, 2, 1), (5, 85, 12, 1, 1),
            (0, 0, 12, 2, 0), (0, 85, 11, 2, 0),
        ):
            pixels = (ctypes.c_uint8 * len(original)).from_buffer_copy(original)
            output = (ctypes.c_uint8 * 32)()
            size, closed = ctypes.c_int(), ctypes.c_int()
            status = self.lib.save(pixels, length, quality, mode, ctypes.byref(size),
                                   ctypes.byref(closed), output)
            self.assertEqual((status, closed.value), (expected, closes))
            self.assertEqual(bytes(pixels), original)
            if not status:
                self.assertEqual((size.value, bytes(output[:size.value])), (5, bytes([7, 8, 9, 10, 11])))


if __name__ == "__main__":
    unittest.main()
