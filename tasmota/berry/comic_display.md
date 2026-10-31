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
start("METRON_USERNAME", "METRON_PASSWORD", "Batman")
```

Pass `nil` or an empty string to use the default series, `Batman`:

```berry
start("METRON_USERNAME", "METRON_PASSWORD", nil)
```

`load("comic_display.be")` defines `start()` and `display_comic()` in the global Berry context. To refresh the cover later, call `display_comic(username, password, series_name)` from a Tasmota rule. Keep the Metron credentials in the rule configuration you control.

## Processing

The script uses Metron's Basic Auth API to find matching series by name, then filters issues by the selected series ID and issue number. List requests ask for one result at a time to stay below Berry's 32 KB string limit. The webclient uses HTTP/1.0 so responses without a `Content-Length` end when the server closes the connection. This requires firmware with the `webclient.use_http10()` binding from `xdrv_52_3_berry_webclient.ino`. The script probes a few randomized issue numbers, with issue 1 as a fallback, then fetches the issue details and downloads its cover image. Portrait covers are rotated 90 degrees counter-clockwise. The image is resized to 800×480, dithered for the Inky Spectra 6 palette, and shown on the display.

The downloaded source is kept at `/metron_comic.jpg`; the dithered image is written to `/metron_comic_dithered.jpg`. The compressed source JPEG must be 512 KiB or smaller. The display refresh takes about 32 seconds.
