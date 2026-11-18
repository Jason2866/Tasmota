# Metron Comic Display for Inky Impression

Fetches a random issue from Metron and displays its cover on the Inky Impression 7.3-inch display.

## Requirements

- A Metron account at [metron.cloud](https://metron.cloud/)
- Tasmota with Berry, `webclient`, `json`, filesystem, and image support
- Inky Impression 7.3 display configured for the universal display driver
- PSRAM, for decoding and resizing the cover image
- The updated Tasmota firmware containing `img.resize()` and `InkyDither.dither()`

> **Security note:** when built with `USE_BERRY_WEBCLIENT_ASYNC`, the script uses the async webclient and pins the `metron.cloud` API public key before sending credentials. The pin must be updated if Metron rotates its key. Other builds retain the legacy webclient behavior, which accepts any TLS certificate; use those builds only on trusted networks. Credentials are sent only to `metron.cloud` API endpoints; cover downloads do not send credentials, and HTTP redirects are not followed.

## Usage

Before running the script, enter `DisplayRotate 1` in the Tasmota console. This sets the 90° software rotation needed for the Metron covers to display in the correct orientation on the Inky panel.

Upload [comic_display.be](./comic_display.be) and [inky_dither.be](./inky_dither.be) to the Tasmota filesystem. Set a non-empty `WebPassword` so filesystem access requires authentication, then create `/metron_comic_account.json` on the device with your Metron credentials:

```json
{
  "username": "METRON_USERNAME",
  "password": "METRON_PASSWORD"
}
```

Keep the account file on the device filesystem, do not commit it, and do not expose it through an unauthenticated `UFSServe` mapping. Load the scripts and display a random cover with:

```berry
load("comic_display.be")
display_comic_from_config()
```

The explicit `start(username, password, series_name)` and `display_comic(username, password, series_name)` interfaces remain available for interactive use. Pass `nil` or an empty string as `series_name` to choose a random series. The parameterless `display_comic_from_config()` wrapper reads `username` and `password` from the account file and calls `display_comic()` with a random series.

`load("comic_display.be")` defines `start()`, `display_comic()`, and `display_comic_from_config()` in the global Berry context. Use the parameterless wrapper for scheduled refreshes so credentials do not appear in rule text.

To refresh the cover every 15 minutes, enter this rule in the Tasmota console:

```text
Rule1 ON System#Boot DO Br load("comic_display.be") ENDON ON Time#Minute|15 DO Br display_comic_from_config() ENDON
Rule1 1
```

The rule loads the Berry script at boot and calls `display_comic_from_config()` at minutes 00, 15, 30, and 45. To load the script immediately without rebooting, run `Br load("comic_display.be")` once in the console, then run `Br display_comic_from_config()`.

## Processing

The script uses Metron's Basic Auth API to find matching series by name, then requests issues filtered by the selected series ID with `page_size=1`. It tries up to three consecutive pages starting at a time-seeded page; it does not probe issue-number values. List requests ask for one result at a time to stay below Berry's 32 KB string limit. HTTPS requests use a 10 s connect timeout and 15 s HTTP timeout and identify themselves as `TasmotaComicDisplay/1.0`. Transient network errors are retried. `HTP: Connection error -2` after that timeout means the device never completed TCP/TLS to `metron.cloud` (often an IP firewall on Metron's side). Call `diagnose_network()` after loading the script: `example.com` should return HTTP 200, while `metron.cloud` staying at `-1`/`-2` confirms the host is unreachable from this network. The script uses the issue's cover URL when present, and fetches issue details only when the list result has no cover URL. It then downloads the cover image. The image is resized to the logical dimensions selected by the `DisplayRotate` setting; uDisplay applies the configured panel rotation when drawing, then the image is dithered for the Inky Spectra 6 palette and shown on the display.

The downloaded source is kept at `/metron_comic.jpg`; the dithered image is written to `/metron_comic_dithered.jpg`. The compressed source JPEG must be 1024 KiB or smaller. The display refresh takes about 32 seconds.
