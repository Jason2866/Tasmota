# Sitronix Reflective LCD (ST7305 / ST7306 / ST7302) — Packed Mono Support

This document covers the descriptor-driven *packed monochrome* support added
for Sitronix reflective LCD controllers in the uDisplay SPI panel driver,
how the `:F` descriptor field works, what changed in the code, the two new
display descriptors (ST7306 and ST7302), and what must be verified per
module before treating those descriptors as production-ready.

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

ST7306 and ST7302 are part of the same Sitronix reflective TFT family and
use the same general RAMWR packed-pixel concept, but with different block
geometries — which is exactly what `:F` is designed to describe.

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

Definitions live in [include/uDisplay_SPI_panel.h](../../lib/lib_display/UDisplay/include/uDisplay_SPI_panel.h)
(`enum UDisplayMonoPackFlags`).

### Block size limits

The packer caps `width * height` at **64 bits** (= 8 bytes per block). This
is enforced in `SPIPanel::hasPackedMono()`. Any combination that fits inside
that limit and produces whole-byte blocks works — for example:

| Controller | `:F,w,h,flags` | Bytes/block | Notes                          |
| ---------- | -------------- | ----------- | ------------------------------ |
| ST7305     | `:F,2,4,3`     | 1           | Original supported case.       |
| ST7306 mono| `:F,2,4,3`     | 1           | 1 bpp mode (DTFORM `3A,10`).   |
| ST7302     | `:F,1,12,3`    | 2           | Native 12-row gate grouping.   |

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
ST7302's 1×12 page) are accepted.

#### `SPIPanel::updateFramePackedMono()`

The single-byte accumulator was replaced with a small fixed-size byte buffer
(`uint8_t block_bytes[8]`) and a continuous bit cursor that rolls over to
the next byte when the current byte fills:

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
previous implementation: `bytes_per_block = 1`, `bit_index` 0..7 lights up
bit positions 7..0 in exactly the same order. The ST7305 descriptor and
hardware behavior are therefore unchanged.

### Descriptor changes

#### `tasmota/displaydesc/ST7302_RLCD_250x122_display.ini`

```diff
-:F,1,8,3
+:F,1,12,3
```

Switches to the controller's native 12-row gate grouping (2 bytes per block,
top 12 bits used, bottom 4 bits padding).

## New descriptor files

Two starter descriptors were added, both modelled on the ST7305 one and
sharing the Sitronix register map.

### `ST7306_RLCD_300x400_display.ini`

- Resolution: 300 × 400
- Packing: `:F,2,4,3` (1 bpp mono mode)
- DTFORM: `3A,10` — forces 1-bit-per-pixel mode so the existing packer
  applies. Native 2 bpp grayscale is **not** enabled (see Limitations).

### `ST7302_RLCD_250x122_display.ini`

- Resolution: 250 × 122
- Packing: `:F,1,12,3` (native page layout, now possible after the code
  change above)
- DTFORM: `3A,11`

## What you MUST verify per module

The two new descriptors are templates, not validated firmware. Before
treating either as production-ready, walk through this list against the
module's vendor reference code and the controller datasheet.

### 1. Init register block

All `D6 … 29` lines were copied verbatim from the ST7305 Waveshare RLCD-4.2
init blob. The Sitronix family shares the register map, but per-panel
trim values differ:

- `C0` Booster control
- `C1 / C2 / C4 / C5` VCOM and gamma trim (panel-specific)
- `B2 / B3 / B4` Frame-rate / waveform LUT
- `D6 / D1 / D8 / 62` Power timing
- `B7 / B0 / B8 / B9` Output enable / data format polarity

Replace these from your module's reference code if you have it. Wrong
gamma/VCOM values typically show as **washed-out, ghosting, or completely
blank** displays, not as garbled pixels.

### 2. Address window (`2A`, `2B`, and the `:A` line)

These are panel-internal *byte addresses* (post-packing), not pixel
coordinates. The starting values used in the new descriptors are derived
from the panel resolution and the chosen packing geometry, but Sitronix
panels typically need a small offset because the gate driver starts a few
lines in. **If text/graphics are shifted, this is the first thing to fix.**

For ST7302 specifically: with `1×12` packing, the row address range
counts in 12-row groups. 122 rows → 11 full groups of 12 = 132 rows
allocated (10 unused). Confirm against the vendor init.

### 3. Rotation table (`:R` and `:0` … `:3`)

Copied from ST7305. The MADCTL byte values for each rotation depend on
the controller's MX/MY/MV bits and may need swapping if your panel is
physically mounted in a different orientation.

### 4. Pin map in `:H`

The `:H` line uses CS=40, SCK=11, MOSI=12, DC=5, RESET=41, no MISO, no
backlight (Waveshare RLCD-4.2 layout). Change to match your wiring.

### 5. Packing flags

Both new descriptors use `flags=3` (invert + reverse-Y) inherited from
ST7305. If your display looks **photonegative**, drop the invert bit
(use `2`). If it's **upside down**, drop the reverse-Y bit (use `1`).
If it looks correct, leave it.

## Limitations

### True 2 bpp grayscale ST7306 is not supported

ST7306 natively supports 4-level grayscale by packing 2 bits per pixel
(2×2 block = 4 pixels = 1 byte). The current `:F` parser is gated on
`bpp == 1`, and the uDisplay framebuffer + the Tasmota `Renderer` base
class both assume the standard 1 bpp vertical-page layout
(`fb_buffer[x + (y >> 3) * width] & (1 << (y & 7))`).

Adding real grayscale would require:

1. A 2 bpp framebuffer allocator in [uDisplay.cpp](../../lib/lib_display/UDisplay/src/uDisplay.cpp)
   (currently sizes 1 bpp as `gxs * ((gys + 7) / 8)`).
2. A `getGrayPixel(x, y) -> 0..3` accessor parallel to `getMonoPixel`.
3. An extended `:F` form (e.g. `:F,w,h,flags,bpp_pack`) and a packer that
   uses `bpp_pack` bits per pixel.
4. Renderer-level changes so user/LVGL pixel writes can express grayscale
   instead of being clamped to mono.

That is a cross-cutting change to the Renderer contract and intentionally
**not** part of this work. The ST7306 descriptor here uses the controller's
1 bpp mode (DTFORM `3A,10`) which works with the existing packer today,
just without grayscale.

### ST7302 packing assumption

The new code emits `ceil(12/8) = 2` whole bytes per 1×12 column page, with
the unused trailing 4 bits zeroed. Some ST7302 reference drivers pack
12-bit pages *tightly* (no inter-block byte alignment, so 2 pages = 3
bytes). If your panel only accepts that tight packing, this code does
not yet cover it; the cleanest fix would be a new flag bit
`UDISP_MONO_PACK_BIT_TIGHT` and a continuous bit cursor across the whole
column stripe rather than per-block.

## Files touched

| File                                                                                    | Change                                                |
| --------------------------------------------------------------------------------------- | ----------------------------------------------------- |
| `lib/lib_display/UDisplay/src/uDisplay_SPI_panel.cpp`                                   | Multi-byte packed-mono blocks, cap raised to 64 bits. |
| `tasmota/displaydesc/ST7306_RLCD_300x400_display.ini`                                   | **New.** ST7306 1 bpp template.                       |
| `tasmota/displaydesc/ST7302_RLCD_250x122_display.ini`                                   | **New.** ST7302 native 1×12 template.                 |
| `tasmota/displaydesc/Sitronix_RLCD_packed_mono.md`                                      | **New.** This document.                               |

No header / struct / API change. The descriptor parser in
[uDisplay.cpp](../../lib/lib_display/UDisplay/src/uDisplay.cpp) is
unchanged — the same `:F,width,height,flags` syntax now simply accepts
larger block sizes.
