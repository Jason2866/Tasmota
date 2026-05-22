# Sitronix Reflective LCD (ST7305 / ST7306 / ST7302) — Packed Mono Support

This document covers the descriptor-driven *packed monochrome* support added
for Sitronix reflective LCD controllers in the uDisplay SPI panel driver,
how the `:F` descriptor field works, what changed in the code, the two new
display descriptors (ST7306 and ST7302), and which fields are verified
against vendor reference code versus which still require per-module
confirmation.

## Background

PR [arendst/Tasmota#24738](https://github.com/arendst/Tasmota/pull/24738)
added descriptor-driven 1 bpp packed-mono transfer support for the ST7305
RLCD via a new descriptor field:

```
:F,width,height,flags
```

For ST7305 the descriptor uses `:F,2,4,3` — a 2-column × 4-row pixel block
packed into one byte, with the polarity inverted and the Y scan reversed.
The low-level SPI panel driver intentionally contains **no** ST7305-specific
code. The controller-specific behavior lives in the descriptor.

ST7306 and ST7302 belong to the same Sitronix reflective TFT family and
use the same general RAMWR packed-pixel concept, but with different block
geometries — exactly what `:F` is designed to describe.

## What `:F` does

The packer iterates the framebuffer in blocks of `width × height` pixels.
For each block:

1. It walks the block row-major (row 0 col 0, row 0 col 1, … row N col M).
2. Each visited pixel contributes one bit to a packed byte stream, starting
   at bit 7 of the first byte and decrementing toward bit 0. When a byte
   fills, the cursor moves to the next byte (again starting at bit 7).
3. The trailing unused bits of the last byte (if the block isn't an exact
   multiple of 8 bits) stay 0.
4. The completed block (`ceil(width*height/8)` bytes) is then optionally
   bit-inverted as a whole if the `INVERT` flag is set.

### `flags` bits

| Bit | Name                       | Meaning                                       |
| --- | -------------------------- | --------------------------------------------- |
| 0   | `UDISP_MONO_PACK_INVERT`   | Bit-invert every output byte (white = 0).     |
| 1   | `UDISP_MONO_PACK_REVERSE_Y`| Walk rows bottom-to-top instead of top-down.  |

Flags combine. ST7305 uses `3` (invert + reverse-Y).

Definitions live in
[lib/lib_display/UDisplay/include/uDisplay_SPI_panel.h](../../lib/lib_display/UDisplay/include/uDisplay_SPI_panel.h)
(`enum UDisplayMonoPackFlags`).

### Block size limits

The packer caps `width * height` at **64 bits** (= 8 bytes per block). This
is enforced in `SPIPanel::hasPackedMono()`. Any combination that fits
inside that limit and produces whole-byte blocks works. Examples below.

| Controller | `:F` value     | Bytes/block | Verified                           |
| ---------- | -------------- | ----------- | ---------------------------------- |
| ST7305     | `:F,2,4,3`     | 1           | Yes — original PR #24738.          |
| ST7302     | `:F,2,12,0`    | 3           | Yes — see ST7302 section below.    |
| ST7306 (1bpp) | n/a         | n/a         | No 1 bpp vendor reference; see ST7306 section. |

## Code changes

### `lib/lib_display/UDisplay/src/uDisplay_SPI_panel.cpp`

Two changes in the packed-mono path.

#### `SPIPanel::hasPackedMono()`

Old gate:

```cpp
return fb_buffer && cfg.bpp == 1 && cfg.mono_pack_width && cfg.mono_pack_height &&
       (cfg.mono_pack_width * cfg.mono_pack_height <= 8);
```

New gate:

```cpp
return fb_buffer && cfg.bpp == 1 && cfg.mono_pack_width && cfg.mono_pack_height &&
       (uint16_t(cfg.mono_pack_width) * uint16_t(cfg.mono_pack_height) <= 64);
```

Raises the cap from 8 to 64 bits so blocks larger than one byte (e.g.
ST7302's 2×12 = 24-bit page) are accepted.

#### `SPIPanel::updateFramePackedMono()`

The single-byte accumulator was replaced with a small fixed-size byte
buffer (`uint8_t block_bytes[8]`) and a continuous bit cursor that rolls
over to the next byte when the current byte fills:

```cpp
for (uint8_t i = 0; i < bytes_per_block; i++) block_bytes[i] = 0;
uint16_t bit_index = 0;
for (uint8_t row = 0; row < cfg.mono_pack_height; row++) {
    int16_t sy = (cfg.mono_pack_flags & UDISP_MONO_PACK_REVERSE_Y)
                  ? height - 1 - y - row : y + row;
    for (uint8_t col = 0; col < cfg.mono_pack_width; col++) {
        if (getMonoPixel(x + col, sy)) {
            block_bytes[bit_index >> 3] |= uint8_t(0x80 >> (bit_index & 7));
        }
        bit_index++;
    }
}
for (uint8_t i = 0; i < bytes_per_block; i++) {
    uint8_t out = block_bytes[i];
    if (cfg.mono_pack_flags & UDISP_MONO_PACK_INVERT) out = ~out;
    spi->writeData8(out);
}
```

`bytes_per_block = (cfg.mono_pack_width * cfg.mono_pack_height + 7) >> 3`.

Behavior for the existing 8-bit case (`2*4 = 8`) is byte-identical to the
previous implementation: `bytes_per_block = 1`, `bit_index` 0..7 lights
up bit positions 7..0 in exactly the same order. The ST7305 descriptor
and hardware behavior are therefore unchanged.

## ST7302 — 250 × 122 (verified)

Descriptor:
[ST7302_RLCD_250x122_display.ini](ST7302_RLCD_250x122_display.ini).

### Source of truth

Cross-checked against the following public ST7302 implementations:

- [zhcong/ST7302-for-arduino](https://github.com/zhcong/ST7302-for-arduino)
- [imcort-nrf-drivers/st7302](https://github.com/imcort-nrf-drivers/st7302)
- [alm604/stm32-ST7302](https://github.com/alm604/stm32-ST7302)
- [Marspacecraft/st7302_4gray](https://github.com/Marspacecraft/st7302_4gray)
- [elulis/micropython_ST7302](https://github.com/elulis/micropython_ST7302)
- [0ut4t1m3/MPY_ST7302](https://github.com/0ut4t1m3/MPY_ST7302)
- [wangshujun-tj/FB_ST7302](https://github.com/wangshujun-tj/FB_ST7302)

The canonical Arduino driver from `zhcong/ST7302-for-arduino` is the most
fully commented and was used as the primary reference.

### Why `:F,2,12,0` is exactly right

The ST7302 RAMWR layout for `0x3A = 0x11` (1 bpp packed) is a
**2-column × 12-row block = 24 bits = 3 bytes**, with this bit ordering
(verbatim from `Marspacecraft/st7302_4gray/st7302.h` and the bit-interleave
kernel in `elulis/micropython_ST7302/st7302viper.py`):

```
Byte 0  D7 = col_A row 0   D6 = col_B row 0
        D5 = col_A row 1   D4 = col_B row 1
        D3 = col_A row 2   D2 = col_B row 2
        D1 = col_A row 3   D0 = col_B row 3

Byte 1  rows 4–7  (same MSB-first 2-col × 4-row pattern)

Byte 2  rows 8–11 (same pattern)
```

The new multi-byte `:F,2,12,X` packer produces *exactly* this sequence:
walking 12 rows × 2 cols row-major with a continuous MSB→LSB bit cursor
that rolls over every 8 bits. ST7302's per-byte layout is literally the
same 2×4 MSB-first pattern as ST7305, repeated three times — so 3 stacked
ST7305-style bytes cover one ST7302 page.

### Verified register values used in the descriptor

| Cmd  | Value(s)                                | Meaning                  | Source         |
| ---- | --------------------------------------- | ------------------------ | -------------- |
| 0x38 | (no params)                             | High Power Mode          | zhcong line 31 |
| 0xEB | 0x02                                    | Enable OTP               | zhcong line 33 |
| 0xD7 | 0x68                                    | OTP Load Control         | zhcong line 35 |
| 0xD1 | 0x01                                    | Auto Power Control       | zhcong line 37 |
| 0xC0 | 0x80                                    | Gate Voltage VGH=12V/VGL=-5V | zhcong line 39 |
| 0xC1 | 0x28, 0x28, 0x28, 0x28, 0x14, 0x00      | VSH                      | zhcong line 41 |
| 0xC2 | 0x00, 0x00, 0x00, 0x00                  | VSL                      | zhcong line 49 |
| 0xCB | 0x14                                    | VCOMH                    | zhcong line 55 |
| 0xB4 | E5, 77, F1, FF, FF, 4F, F1, FF, FF, 4F  | Gate EQ HPM/LPM          | zhcong line 57 |
| 0x11 | (sleep out) + 150 ms                    | Sleep Out                | zhcong line 69 |
| 0xC7 | 0xA6, 0xE9                              | OSC                      | zhcong line 73 |
| 0xB0 | 0x64                                    | Duty                     | zhcong line 75 |
| 0x36 | 0x20                                    | MADCTL (MY flip)         | zhcong line 77 |
| 0x3A | 0x11                                    | Data Format (1 bpp 24-bit page) | zhcong line 79 |
| 0xB9 | 0x23                                    | Source Setting           | zhcong line 81 |
| 0xB8 | 0x09                                    | Panel Setting            | zhcong line 83 |
| 0x2A | 0x05, 0x36                              | Full-panel CASET init    | zhcong line 85 |
| 0x2B | 0x00, 0xC7                              | Full-panel RASET init    | zhcong line 88 |
| 0xD0 | 0x1F                                    | Power timing             | zhcong line 91 |
| 0x29 | (display on)                            | Display On               | zhcong line 93 |
| 0xB9 | 0xE3 + 150 ms                           | Enable RAM clear         | zhcong line 95 |
| 0xB9 | 0x23                                    | Disable RAM clear        | zhcong line 98 |
| 0x72 | 0x00                                    | Destress Off             | zhcong line 100 |
| 0x39 | (LPM)                                   | Low Power Mode           | zhcong line 102 |
| 0x2A | 0x19, 0x23                              | **Working window CASET** | zhcong line 104 |
| 0x2B | 0x00, 0x7C                              | **Working window RASET** | zhcong line 106 |

The working window covers 11 CASET slots × 12 rows = 132 row positions
(122 physical + 10 padding) and 125 RASET slots × 2 cols = 250 cols.
The packer naturally emits exactly 11 × 3 = 33 bytes per column pair
when `:H` height is 122 with `:F,2,12,0` — `(122 + 11) / 12 = 11`
iterations of the y loop (last iteration's rows 120..131 read 0 from
the out-of-range framebuffer), × 3 bytes per block = 33 bytes per
column pair × 125 column pairs = 4125 bytes total. Matches the
controller window exactly.

### Why flags=0 (and not 3 like ST7305)

- INVERT: ST7302's `0x3A = 0x11` layout writes `1` for dark pixels in the
  unrotated default. No inversion needed in the packer.
- REVERSE_Y: orientation is handled by MADCTL `0x36 = 0x20` (MY bit set),
  so the controller flips Y in hardware. Doing it again in the packer
  would un-flip it.

If your panel is mounted differently, the first thing to try is
swapping MADCTL between `0x00` and `0x20` (both are observed in vendor
code), then if needed adding the INVERT or REVERSE_Y bit to the `:F`
flags.

## ST7306 — 300 × 400 (NOT functional with the current packer)

Descriptor:
[ST7306_RLCD_300x400_display.ini](ST7306_RLCD_300x400_display.ini).

### Source of truth

Verified against [musicaJack/ST73xx_Reflective_Lcd](https://github.com/musicaJack/ST73xx_Reflective_Lcd)
(`src/st73xx/st7306_driver.cpp`, `include/st73xx/st7306_driver.hpp`).
This is the only public driver with a complete init sequence and pixel
packer for ST7306.

### Why this descriptor cannot drive the panel today

ST7306 is **natively 2 bits per pixel** (4-level grayscale: white, light
gray, dark gray, black). The vendor init sequence sets:

- `0x3A = 0x11` — "3 writes for 24-bit data" (2 bpp packed)
- `0xB9 = 0x20` — Mono gamma curve

…and the pixel packer maps each 2-pixel-wide × 2-pixel-tall block to
**one byte holding four 2-bit pixels**:

```
One byte covers a 2×2 pixel block, 2 bits per pixel:

  pixel (x+0,y+0): bits 7, 5  (MSB pair)
  pixel (x+0,y+1): bits 6, 4
  pixel (x+1,y+0): bits 3, 1
  pixel (x+1,y+1): bits 2, 0
```

The `:F` packer is currently 1 bpp only (gated on `cfg.bpp == 1`). It
cannot emit two bits per source pixel, so this descriptor — which uses
the controller's only verified mode — is shipped as a **reference for
when 2 bpp support is added**, not as something that draws correctly
today.

There is no public ST7306 reference for the controller's 1 bpp fallback
mode (`0x3A = 0x10`, "4 writes for 24-bit data"). Guessing at it would
just produce another untested descriptor, so we did not.

### What's verified in the file anyway

The register values (`D6, D1, C0, C1, C2, C4, C5, D8, B2, B3, B0, C9,
36, 3A, B9, B8, 2A, 2B, BB`) come from `st7306_driver.cpp::initST7306()`
lines 77–215, with addressing for the documented working window
(50 CASET slots × 6 pixel cols = 300 cols, 200 RASET slots × 2 pixel
rows = 400 rows). When the 2 bpp packer eventually lands, only the
`:F` line and the framebuffer allocator should need changing.

### What is needed to make ST7306 functional

1. A 2 bpp framebuffer allocator in
   [uDisplay.cpp](../../lib/lib_display/UDisplay/src/uDisplay.cpp)
   (currently sizes 1 bpp as `gxs * ((gys + 7) / 8)`).
2. A `getGrayPixel(x, y) -> 0..3` accessor parallel to `getMonoPixel`.
3. An extended `:F` form (e.g. `:F,w,h,flags,bits_per_pixel`) and a
   packer that uses `bits_per_pixel` bits per pixel — for ST7306 that
   would be `:F,2,2,0,2` (2×2 block, 2 bpp).
4. Renderer-level changes so user/LVGL pixel writes can express
   grayscale instead of being clamped to mono.

That is a cross-cutting change to the Renderer contract and
intentionally **not** part of this work.

## What you must still verify per module

Even with vendor-verified register values, per-board adjustments are
common.

### 1. Pin map (`:H` line)

The `:H` line in both new descriptors uses CS=40, SCK=11, MOSI=12,
DC=5, RESET=41, no MISO, no backlight (Waveshare RLCD-4.2 layout
inherited from the ST7305 descriptor). **Change to match your wiring.**

### 2. MADCTL / orientation

ST7302 vendor code uses `0x20` (MY flip) or `0x00` (no flip) depending
on the module — both are valid. If the image is upside down, try
flipping that bit. The rotation table (`:0` … `:3`) is currently filled
with the rotation-0 MADCTL value for all four rotations, i.e. rotation
is effectively a no-op. Filling in real per-rotation MADCTL bits is
left for a follow-up if/when someone needs rotation on these panels.

### 3. Address window (`2A`, `2B`, `:A`)

These come straight from vendor code and are **panel-specific**: ST7302
working window `0x19..0x23 / 0x00..0x7C`, ST7306 `0x05..0x36 / 0x00..0xC7`.
Both are panel-internal byte/group addresses, not pixel coordinates,
and they assume the panel uses the standard Waveshare/heltec module
layout. A custom module with a different gate-driver tap point will
need a small offset adjustment.

### 4. Power / gamma values

`C0, C1, C2, C4, C5, D8, B4` are voltage and waveform trims and *can*
vary slightly between module vendors. Symptoms of wrong values:
washed-out, ghosting, or completely blank — not garbled pixels. The
ST7306 values match the musicaJack-reference panel; ST7302 values
match the zhcong-reference panel. If your specific module ships with a
different vendor init blob, prefer that.

### 5. Packing flags

- ST7305: `flags=3` (invert + reverse-Y). Verified by the upstream PR.
- ST7302: `flags=0`. Justified above; MADCTL handles orientation.
- ST7306: `flags=3` placeholder copied from ST7305; **not meaningful
  until 2 bpp support exists**.

If your display looks photonegative, set bit 0 (INVERT). If it's
upside down, set bit 1 (REVERSE_Y) — but consider flipping MADCTL
first since that's typically the controller's intended mechanism.

## Files touched

| File                                                                                    | Change                                                |
| --------------------------------------------------------------------------------------- | ----------------------------------------------------- |
| `lib/lib_display/UDisplay/src/uDisplay_SPI_panel.cpp`                                   | Multi-byte packed-mono blocks, cap raised to 64 bits. |
| `tasmota/displaydesc/ST7302_RLCD_250x122_display.ini`                                   | **New.** Vendor-verified init + native 2×12 packing.  |
| `tasmota/displaydesc/ST7306_RLCD_300x400_display.ini`                                   | **New.** Vendor-verified init; 2 bpp packer not yet implemented. |
| `tasmota/displaydesc/Sitronix_RLCD_packed_mono.md`                                      | **New.** This document.                               |

No header / struct / API change. The descriptor parser in
[uDisplay.cpp](../../lib/lib_display/UDisplay/src/uDisplay.cpp) is
unchanged — the same `:F,width,height,flags` syntax now simply accepts
larger block sizes.
