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

Pass `nil` or an empty string to use a random comic series:

```berry
start("METRON_USERNAME", "METRON_PASSWORD", nil)
```

`load("comic_display.be")` defines `start()` and `display_comic()` in the global Berry context. To refresh the cover later, call `display_comic(username, password, series_name)` from a Tasmota rule. Keep the Metron credentials in the rule configuration you control.

To refresh the cover every 15 minutes, enter this rule in the Tasmota console, replacing the credential placeholders with your Metron account details:

```text
Rule1 ON System#Boot DO BrRun load("comic_display.be") ENDON ON Time#Minute|15 DO BrRun display_comic("METRON_USERNAME","METRON_PASSWORD",nil) ENDON
Rule1 1
```

The rule loads the Berry script at boot and calls `display_comic()` at minutes 00, 15, 30, and 45. To load the script immediately without rebooting, run `BrRun load("comic_display.be")` once in the console.

## Processing

The script uses Metron's Basic Auth API to find matching series by name, then filters issues by the selected series ID and issue number. List requests ask for one result at a time to stay below Berry's 32 KB string limit. HTTPS requests use a 10 s connect timeout and 15 s HTTP timeout and identify themselves as `TasmotaComicDisplay/1.0`. Transient network errors are retried. `HTP: Connection error -2` after that timeout means the device never completed TCP/TLS to `metron.cloud` (often an IP firewall on Metron's side). Call `diagnose_network()` after loading the script: `example.com` should return HTTP 200, while `metron.cloud` staying at `-1`/`-2` confirms the host is unreachable from this network. The script probes up to three randomized issue numbers. It uses the cover URL from the issue list result when present, and fetches the issue details only when that result has no cover URL. It then downloads the cover image. Portrait covers are rotated 90 degrees counter-clockwise. The image is resized to 800×480, dithered for the Inky Spectra 6 palette, and shown on the display.

The downloaded source is kept at `/metron_comic.jpg`; the dithered image is written to `/metron_comic_dithered.jpg`. The compressed source JPEG must be 512 KiB or smaller. The display refresh takes about 32 seconds.
