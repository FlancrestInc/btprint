# Local Print Web App Design

## Purpose

Provide a local browser interface for the working CTP500 BLE printer. The first
release is a focused utility for printing either an image or a short text note
from this Linux machine. It must use the existing, proven BLE frame and
calibration path.

## Scope

The app runs only on the local machine and binds to `127.0.0.1`. It supports
one active print job at a time and two sources:

- A Pillow-readable uploaded image.
- Text rendered into a receipt-width Pillow image.

It provides a monochrome preview, a dither control for images, basic text
controls, printing status, and an advanced area for calibration overrides.

Out of scope for this release: network access, user accounts, saved jobs,
drag-and-drop layout editing, templates, stickers, or playful effects.

## Architecture

### `webapp.py`

The local Flask entry point. It serves the page and provides JSON endpoints.
It binds to `127.0.0.1:5000` by default and starts with `python3 webapp.py`.

### `print_service.py`

The application boundary for print jobs. It accepts a prepared Pillow image,
an interline-feed setting, and a printer address. It calls
`build_print_frames()` and `GatttoolSession` directly; it does not invoke the
CLI with a shell command. The Flask layer calls `prepare_ble_image()` before it
creates a job, so invalid source settings return a request error. A process-local
lock rejects a second print request while a job is preparing or printing.

`PrintService` owns in-memory jobs. Each job has an ID and one state:
`preparing`, `printing`, `complete`, or `failed`. The service runs one job in a
background thread, retains the most recent 20 completed jobs, and exposes each
job's state and a user-facing error string. Jobs do not survive a server
restart.

### `text_renderer.py`

Renders Unicode plain text into a 380-pixel-wide Pillow image using
`/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf` or its bold counterpart.
The app fails with a clear configuration error if either required font is
missing. Unsupported glyphs use the font renderer's replacement glyph. It
supports font size 12 through 72 pixels, left/center/right alignment, and bold.
It wraps text to 380 pixels, uses line spacing equal to 125% of the font size,
and limits input to 2,000 characters and rendered source height to 4,096 rows.
Because the source is already 380 pixels wide, `prepare_ble_image()` preserves
its content width and then adds the normal printer safety inset.

### Browser assets

`web/static/` contains the JavaScript and CSS. `web/templates/index.html`
contains the single-page structure. The browser sends source data and settings
to the local server, receives a preview image or job state, and never talks to
Bluetooth itself.

## Interface

The page has a compact, desktop-first layout:

- Header with the printer name and target address.
- Image/Text source switch.
- Image controls: picker, selected filename, and dither toggle.
- Text controls: multiline field, font size, alignment, and bold.
- Monochrome receipt-shaped preview which updates after changing source data or
  controls.
- A Print button and status area polling job state to show preparing, printing,
  complete, or an actionable Bluetooth error.
- A collapsed Advanced section with MAC address, interline feed, and vertical
  scale fields.

Defaults are the validated CTP500 calibration: MAC
`20:DC:8B:CD:CA:C0`, interline feed `1`, and vertical scale `0.5`.

## Requests and validation

`POST /preview` accepts either a multipart image upload or text settings and
returns a PNG preview. `POST /print` accepts the same data, validates it again,
creates a job, and returns `202 {"job_id": "..."}`. `GET /jobs/<job_id>`
returns `200 {"state": "preparing|printing|complete|failed", "error":
"...|null"}`. A second `POST /print` while a job is active returns `409`
with `{"error": "A print job is already in progress."}`.

`POST /preview` returns `200 image/png` on success. Invalid preview or print
requests return `400 {"error": "..."}`. An internal image-processing error
returns `500 {"error": "Could not prepare this print."}` and is logged by the
server. `GET /jobs/<job_id>` returns `404` for an expired or unknown job. Both
endpoints validate:

- Source type is `image` or `text`.
- Text is nonempty after trimming.
- Image uploads are present, Pillow-readable, at most 10 MiB, and at most
  12 megapixels after decoding.
- Font size is 12 through 72 pixels.
- Alignment is left, center, or right.
- MAC address is a six-octet colon-separated address; feed is 1 through 8;
  vertical scale is 0.25 through 2.0; and the prepared image is at most 2,048
  rows.

Temporary uploads live in a server-created temporary directory and are removed
after processing. Bluetooth connection and write failures retain their concise
existing text, such as `connect failed` or `write failed`, in the job error.
Unexpected exceptions are logged server-side and shown as `Printing failed; see
the server log.`

## Print flow

1. The browser submits image data or text plus settings.
2. The server opens or renders a Pillow image.
3. `prepare_ble_image()` applies width fitting, calibrated vertical scaling,
   and optional dithering.
4. The server validates the prepared image dimensions. The preview endpoint
   returns that prepared bitmap as PNG. The print endpoint
   creates a `preparing` job and returns its ID.
5. The job becomes `printing`, turns the image into CTP500 frames, and sends
   one complete job through GATT. It then becomes `complete` or `failed`.

The CLI remains supported and unchanged as a fallback path.

## Testing

Automated tests will cover text wrapping, line spacing, alignment, missing
fonts, preview generation, request validation and limits, calibrated defaults,
active-job rejection (including two concurrent print requests yielding exactly
one `202` and one `409`), job-state polling, and successful or failed mocked
GATT transports. Existing frame and CLI tests remain in the suite. A
`requirements.txt` file will declare Flask and Pillow. Manual acceptance is one
image print and one text print through the browser, using the known printer.
