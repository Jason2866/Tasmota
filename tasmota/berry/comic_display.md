# Metron Comic Display for Inky Impression

Fetches a random issue from Metron and displays its cover on the Inky Impression 7.3-inch display.

## Requirements

- A Metron account at [metron.cloud](https://metron.cloud/)
- Tasmota with Berry, `webclient`, `json`, filesystem, and image support
- Inky Impression 7.3 display configured for the universal display driver
- PSRAM, for decoding and resizing the cover image
- The updated Tasmota firmware containing `img.resize()` and `InkyDither.dither()`

## Usage

Upload [comic_display.be](./comic_display.be) and [inky_dither.be](./inky_dither.be) to the Tasmota filesystem, then run:

```berry
load("comic_display.be")
comic_display.start("METRON_USERNAME", "METRON_PASSWORD", "Batman")
```

The search term is optional; when omitted, it defaults to `batman`:

```berry
comic_display.start("METRON_USERNAME", "METRON_PASSWORD")
```

To refresh the cover later, call `display_comic(username, password, series_name)` from a Tasmota rule. Keep the Metron credentials in the rule configuration you control.

## Processing

The script uses Metron's Basic Auth API to search issues by series name, chooses one result from the first API page, fetches the issue details, and downloads its cover image. Portrait covers are rotated 90 degrees counter-clockwise. The image is resized to 800×480, dithered for the Inky Spectra 6 palette, and shown on the display.

The downloaded source is kept at `/metron_comic.jpg`; the dithered image is written to `/metron_comic_dithered.jpg`. The compressed source JPEG must be 512 KiB or smaller. The display refresh takes about 32 seconds.
