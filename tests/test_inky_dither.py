#!/usr/bin/env python3
"""Exercise the native Inky dithering implementation with a minimal Berry API."""

import ctypes
from pathlib import Path
import random
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "lib/libesp32/berry_tasmota/src/be_inky_dither_lib.c"
PALETTE = ((0, 0, 0), (255, 255, 255), (255, 255, 0),
           (255, 0, 0), (0, 0, 255), (0, 255, 0))
PANEL = ((0, 0, 0), (161, 164, 165), (208, 190, 71),
         (156, 72, 75), (61, 59, 94), (58, 91, 70))

HEADER = r"""
#include <stddef.h>
#include <stdint.h>
typedef struct bvm bvm;
int be_top(bvm *vm);
int be_isbytes(bvm *vm, int index);
int be_isint(bvm *vm, int index);
int be_isnumber(bvm *vm, int index);
int be_isnil(bvm *vm, int index);
float be_toreal(bvm *vm, int index);
int32_t be_toint(bvm *vm, int index);
void *be_tobytes(bvm *vm, int index, size_t *size);
void be_raise(bvm *vm, const char *type, const char *message);
void *be_os_malloc(size_t size);
void be_os_free(void *ptr);
void yield(void);
#define be_return_nil(vm) return 0
"""

HARNESS = r"""
#include <setjmp.h>
#include <stdlib.h>
#include <string.h>
#include "be_constobj.h"
struct bvm {
    uint8_t *pixels;
    size_t size;
    int32_t width, height;
    float saturation;
    int fail_alloc;
    const char *error;
    jmp_buf jump;
};
int be_top(bvm *vm) { (void)vm; return 4; }
int be_isbytes(bvm *vm, int index) { (void)vm; return index == 1; }
int be_isint(bvm *vm, int index) { (void)vm; return index == 2 || index == 3; }
int be_isnumber(bvm *vm, int index) { (void)vm; return index == 4; }
int be_isnil(bvm *vm, int index) { (void)vm; (void)index; return 0; }
float be_toreal(bvm *vm, int index) { (void)index; return vm->saturation; }
int32_t be_toint(bvm *vm, int index) { return index == 2 ? vm->width : vm->height; }
void *be_tobytes(bvm *vm, int index, size_t *size) {
    (void)index; *size = vm->size; return vm->pixels;
}
void be_raise(bvm *vm, const char *type, const char *message) {
    (void)message; vm->error = type; longjmp(vm->jump, 1);
}
static int fail_allocation;
void *be_os_malloc(size_t size) { return fail_allocation ? NULL : malloc(size); }
void be_os_free(void *ptr) { free(ptr); }
void yield(void) {}
int m_inky_dither_dither(bvm *vm);
int run_dither(uint8_t *pixels, size_t size, int width, int height,
               float saturation, int fail_alloc) {
    bvm vm = { .pixels = pixels, .size = size, .width = width, .height = height,
               .saturation = saturation, .fail_alloc = fail_alloc, .error = NULL };
    fail_allocation = vm.fail_alloc;
    if (setjmp(vm.jump)) return strcmp(vm.error, "memory_error") == 0 ? 2 : 1;
    m_inky_dither_dither(&vm);
    return 0;
}
"""


def reference(pixels, width, height, saturation):
    palette = [tuple(int(panel * saturation + pure * (1 - saturation))
                     for panel, pure in zip(measured, identifier))
               for measured, identifier in zip(PANEL, PALETTE)]
    result = bytearray(pixels)
    errors = [[[0, 0, 0] for _ in range(width)] for _ in range(height)]
    for row in range(height):
        direction = 1 if row % 2 == 0 else -1
        for column in range(0, width) if direction == 1 else range(width - 1, -1, -1):
            index = (row * width + column) * 3
            color = []
            for channel in range(3):
                value = errors[row][column][channel]
                rounded = (abs(value) + 8) // 16 * (-1 if value < 0 else 1)
                color.append(max(0, min(4080, pixels[index + channel] * 16 + rounded)))
            best = min(range(6), key=lambda candidate: sum(
                (color[channel] - palette[candidate][channel] * 16) ** 2
                for channel in range(3)))
            result[index:index + 3] = bytes(PALETTE[best])
            for channel in range(3):
                error = color[channel] - palette[best][channel] * 16
                for next_row, next_column, weight in (
                    (row, column + direction, 7),
                    (row + 1, column - direction, 3),
                    (row + 1, column, 5),
                    (row + 1, column + direction, 1),
                ):
                    if next_row < height and 0 <= next_column < width:
                        errors[next_row][next_column][channel] += error * weight
    return result


class InkyDitherTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tempdir = tempfile.TemporaryDirectory()
        directory = Path(cls.tempdir.name)
        (directory / "be_constobj.h").write_text(HEADER)
        for name in ("be_mem.h", "be_exec.h", "be_byteslib.h", "esp32-hal.h",
                     "be_fixed_be_class_inky_dither.h"):
            (directory / name).write_text("")
        (directory / "harness.c").write_text(HARNESS)
        library = directory / "dither.so"
        subprocess.run(["cc", "-std=c99", "-Wall", "-Wextra", "-Werror", "-shared",
                        "-fPIC", "-DUSE_BERRY_IMAGE", "-I", str(directory), str(SOURCE),
                        str(directory / "harness.c"), "-o", str(library)], check=True)
        cls.lib = ctypes.CDLL(str(library))
        cls.lib.run_dither.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t,
                                       ctypes.c_int, ctypes.c_int, ctypes.c_float, ctypes.c_int]
        cls.lib.run_dither.restype = ctypes.c_int

    @classmethod
    def tearDownClass(cls):
        cls.tempdir.cleanup()

    def run_dither(self, data, width, height, saturation=0.5, size=None, fail_alloc=False):
        storage = (ctypes.c_uint8 * (len(data) + 2))(*([91] + list(data) + [173]))
        pixels = ctypes.cast(ctypes.byref(storage, 1), ctypes.POINTER(ctypes.c_uint8))
        status = self.lib.run_dither(pixels, len(data) if size is None else size,
                                     width, height, saturation, fail_alloc)
        self.assertEqual((storage[0], storage[-1]), (91, 173))
        return status, bytearray(storage[1:-1])

    def test_reference_and_edges(self):
        generator = random.Random(1601)
        for width, height in ((1, 1), (1, 17), (17, 1), (2, 2), (2, 13),
                              (13, 2), (7, 9), (24, 19)):
            for saturation in (0.0, 0.5, 1.0):
                for _ in range(8):
                    data = bytearray(generator.randrange(256) for _ in range(width * height * 3))
                    status, actual = self.run_dither(data, width, height, saturation)
                    self.assertEqual(status, 0)
                    self.assertEqual(actual, reference(data, width, height, saturation))

    def test_palette_and_flat_gray(self):
        for measured, identifier in zip(PANEL, PALETTE):
            status, actual = self.run_dither(bytes(measured), 1, 1, 1.0)
            self.assertEqual((status, actual), (0, bytearray(identifier)))
        width, height = 128, 128
        status, actual = self.run_dither(bytes([128, 128, 128]) * width * height,
                                         width, height, 0.0)
        self.assertEqual(status, 0)
        for channel in range(3):
            self.assertLess(abs(sum(actual[channel::3]) / (width * height) - 128), 2)

    def test_validation_and_allocation_failure_leave_pixels_unchanged(self):
        data = bytearray(range(12))
        for width, height, saturation, size, fail_alloc, expected in (
            (0, 2, 0.5, None, False, 1), (2, -1, 0.5, None, False, 1),
            (2, 2, -0.1, None, False, 1), (2, 2, 1.1, None, False, 1),
            (2, 2, float("nan"), None, False, 1), (2, 2, 0.5, 11, False, 1),
            (2, 2, 0.5, None, True, 2),
        ):
            status, actual = self.run_dither(data, width, height, saturation, size, fail_alloc)
            self.assertEqual(status, expected)
            self.assertEqual(actual, data)


if __name__ == "__main__":
    unittest.main()
