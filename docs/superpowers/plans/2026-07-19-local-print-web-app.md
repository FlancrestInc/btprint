# Local Print Web App Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local Flask web app that previews and prints uploaded images or simple text through the proven CTP500 BLE path.

**Architecture:** Keep the printer protocol modules unchanged. Add a text renderer, a print-service boundary that owns one asynchronous in-memory job, and a Flask app that validates browser requests and serves a single local page. The browser polls job state and never accesses Bluetooth directly.

**Tech Stack:** Python 3, Flask, Pillow, existing CTP500 BLE/GATT modules, vanilla HTML/CSS/JavaScript, `unittest`.

---

## File structure

- `requirements.txt`: Runtime dependencies for a fresh local install.
- `text_renderer.py`: Deterministic text validation, wrapping, and Pillow rendering.
- `print_service.py`: Prepared-image validation, background job state, and direct GATT sending.
- `webapp.py`: Flask routes, request parsing, and app wiring.
- `web/templates/index.html`: Single-page form and stable element IDs.
- `web/static/app.css`: Desktop-first utility styling and receipt preview.
- `web/static/app.mjs`: Source switching, preview requests, print requests, and job polling.
- `tests/test_text_renderer.py`: Rendering unit tests.
- `tests/test_print_service.py`: Job lifecycle and concurrent-job tests with mocked transport.
- `tests/test_webapp.py`: Flask request/response tests with a mocked service.
- `tests/web_app_ui.test.mjs`: Node built-in tests for preview, print, and polling client behavior.
- `README.md`: Web-app install, start, and use instructions.

## Chunk 1: Python print boundary

### Task 1: Declare web-app dependencies

**Files:**
- Create: `requirements.txt`

- [ ] **Step 1: Write the dependency file**

```text
Flask>=3.0,<4.0
Pillow>=9.0
```

- [ ] **Step 2: Verify dependency declarations**

Run: `python3 -m pip install --dry-run -r requirements.txt`

Expected: Flask and Pillow resolve without changing the environment.

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "Add web app dependencies"
```

### Task 2: Render validated text as a Pillow image

**Files:**
- Create: `text_renderer.py`
- Create: `tests/test_text_renderer.py`

- [ ] **Step 1: Write failing renderer tests**

```python
import unittest
from unittest import mock
from PIL import ImageOps

from text_renderer import TextRenderError, render_text


class TextRendererTests(unittest.TestCase):
    def test_renders_380_pixel_wide_image(self):
        image = render_text("Hello", font_size=24, align="left", bold=False)
        self.assertEqual(image.mode, "L")
        self.assertEqual(image.width, 380)
        self.assertGreater(image.height, 0)

    def test_rejects_invalid_text_controls(self):
        with self.assertRaisesRegex(TextRenderError, "font size"):
            render_text("Hello", font_size=11, align="left", bold=False)
        with self.assertRaisesRegex(TextRenderError, "alignment"):
            render_text("Hello", font_size=24, align="diagonal", bold=False)

    def test_rejects_blank_and_overlong_text(self):
        with self.assertRaisesRegex(TextRenderError, "text"):
            render_text("   ", font_size=24, align="left", bold=False)
        with self.assertRaisesRegex(TextRenderError, "2,000"):
            render_text("x" * 2001, font_size=24, align="left", bold=False)

    def test_wraps_long_text_without_exceeding_the_height_limit(self):
        image = render_text("word " * 300, font_size=12, align="center", bold=True)
        self.assertLessEqual(image.height, 4096)
        self.assertGreater(image.height, round(12 * 1.25))

    def test_rejects_text_that_would_exceed_the_height_limit(self):
        with self.assertRaisesRegex(TextRenderError, "4,096"):
            render_text("word " * 400, font_size=72, align="left", bold=False)

    def test_uses_125_percent_line_spacing(self):
        with mock.patch("text_renderer.ImageDraw.Draw") as draw, \
             mock.patch("text_renderer.ImageFont.truetype"):
            draw.return_value.textbbox.return_value = (0, 0, 10, 20)
            render_text("one\ntwo", font_size=24, align="left", bold=False)
        positions = [call.args[0] for call in draw.return_value.text.call_args_list]
        self.assertEqual(positions[1][1] - positions[0][1], 30)

    def test_alignment_moves_the_ink_across_the_receipt(self):
        boxes = [
            ImageOps.invert(render_text("X", font_size=24, align=align, bold=False)).getbbox()
            for align in ("left", "center", "right")
        ]
        self.assertLess(boxes[0][0], boxes[1][0])
        self.assertLess(boxes[1][0], boxes[2][0])

    def test_missing_required_font_is_a_render_error(self):
        with mock.patch("text_renderer.ImageFont.truetype", side_effect=OSError):
            with self.assertRaisesRegex(TextRenderError, "font"):
                render_text("Hello", font_size=24, align="left", bold=False)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest tests.test_text_renderer`

Expected: FAIL because `text_renderer` does not exist.

- [ ] **Step 3: Implement only the renderer contract**

```python
CONTENT_WIDTH = 380
MIN_FONT_SIZE = 12
MAX_FONT_SIZE = 72
MAX_TEXT_LENGTH = 2000
MAX_RENDERED_HEIGHT = 4096

class TextRenderError(ValueError):
    pass

def render_text(text, *, font_size, align, bold):
    """Return a white 380-pixel-wide grayscale image for valid plain text."""
```

Load the DejaVu regular or bold path specified by the design. Reject blank or
overlong text, invalid sizes, invalid alignment, missing font files, and a
rendered height above the limit with `TextRenderError`. Use `ImageDraw.textbbox`
to wrap words and place each line. Set line spacing with
`round(font_size * 1.25)`. Use white background and black text.

- [ ] **Step 4: Run the renderer tests to verify they pass**

Run: `python3 -m unittest tests.test_text_renderer`

Expected: all renderer tests pass.

- [ ] **Step 5: Commit**

```bash
git add text_renderer.py tests/test_text_renderer.py
git commit -m "Add receipt text renderer"
```

### Task 3: Add a single-job print service

**Files:**
- Create: `print_service.py`
- Create: `tests/test_print_service.py`

- [ ] **Step 1: Write failing service tests**

```python
import threading
import time
import unittest
from PIL import Image

from ctp500_gatttool import GatttoolTransportError
from print_service import PrintService, PrintServiceError


class FakeSession:
    def __init__(self, gate=None, error=None):
        self.gate, self.error, self.frames, self.closed = gate, error, [], False

    def send_frames(self, frames):
        self.frames.extend(frames)
        if self.gate:
            self.gate.wait(timeout=1)
        if self.error:
            raise self.error

    def close(self):
        self.closed = True


class PrintServiceTests(unittest.TestCase):
    def prepared(self):
        return Image.new("1", (384, 2), 1)

    def wait_for_terminal(self, service, job_id):
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            job = service.get(job_id)
            if job["state"] in ("complete", "failed"):
                return job
            time.sleep(0.01)
        self.fail("job did not reach a terminal state")

    def test_starts_a_job_and_records_completion(self):
        session = FakeSession()
        service = PrintService(session_factory=lambda mac: session,
                               frame_builder=lambda image, interline_feed: [b"frame"])
        job_id = service.start(self.prepared())
        self.assertIn(service.get(job_id)["state"], ("preparing", "printing", "complete"))
        self.assertEqual(self.wait_for_terminal(service, job_id)["state"], "complete")
        self.assertEqual(session.frames, [b"frame"])
        self.assertTrue(session.closed)

    def test_rejects_second_active_job_and_allows_exactly_one_concurrent_start(self):
        gate, sessions = threading.Event(), []
        service = PrintService(session_factory=lambda mac: sessions.append(FakeSession(gate)) or sessions[-1],
                               frame_builder=lambda image, interline_feed: [b"frame"])
        barrier, jobs, errors = threading.Barrier(2), [], []

        def start_job():
            barrier.wait()
            try:
                jobs.append(service.start(self.prepared()))
            except PrintServiceError as error:
                errors.append(str(error))

        threads = [threading.Thread(target=start_job) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(errors, ["A print job is already in progress."])
        gate.set()
        self.wait_for_terminal(service, jobs[0])

    def test_transport_failure_marks_job_failed_and_closes_session(self):
        session = FakeSession(error=GatttoolTransportError("write failed"))
        service = PrintService(session_factory=lambda mac: session,
                               frame_builder=lambda image, interline_feed: [b"frame"])
        job = self.wait_for_terminal(service, service.start(self.prepared()))
        self.assertEqual(job["state"], "failed")
        self.assertEqual(job["error"], "write failed")
        self.assertTrue(session.closed)

    def test_rejects_invalid_prepared_image_and_forgets_old_completed_jobs(self):
        service = PrintService(session_factory=lambda mac: FakeSession(),
                               frame_builder=lambda image, interline_feed: [])
        with self.assertRaisesRegex(PrintServiceError, "384"):
            service.start(Image.new("1", (383, 1), 1))
        job_ids = []
        for _ in range(21):
            job_id = service.start(self.prepared())
            self.wait_for_terminal(service, job_id)
            job_ids.append(job_id)
        with self.assertRaises(KeyError):
            service.get(job_ids[0])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest tests.test_print_service`

Expected: FAIL because `print_service` does not exist.

- [ ] **Step 3: Implement the focused job service**

```python
class PrintServiceError(RuntimeError):
    pass

class PrintService:
    def __init__(self, *, session_factory=GatttoolSession,
                 frame_builder=build_print_frames):
        self._session_factory = session_factory
        self._frame_builder = frame_builder
        self._lock = threading.Lock()
        self._jobs = {}
        self._active_job_id = None

    def start(self, prepared_image, *, mac=DEFAULT_MAC, interline_feed=1) -> str:
        """Create a background job for a validated prepared bitmap or raise busy."""

    def get(self, job_id) -> dict:
        """Return a copy of the job state or raise KeyError."""
```

Use a `threading.Lock` to atomically validate that no job is active, create the
job record in `preparing` state, and start its worker. Validate the prepared
image synchronously before creating the job: mode `1`, width 384, positive
height no greater than 2,048; validate MAC with a full-match regular expression
and feed 1–8. The Flask layer prepares the source image and validates vertical
scale before it calls this method, so invalid user requests can return 400
instead of accepted failed jobs.

The worker first sets `printing`, calls the injected frame builder, sends frames
through the injected session, and always calls `close()` in `finally`. It then
sets `complete`. Map `GatttoolTransportError` and validation errors to their
string in `error`; map unexpected exceptions to `Printing failed; see the
server log.` and log the traceback. In the same lock-protected final state
update, clear `_active_job_id` on both completion and failure. Retain only the
last 20 completed jobs.

- [ ] **Step 4: Run service tests to verify they pass**

Run: `python3 -m unittest tests.test_print_service`

Expected: all service tests pass, including the two-thread race test.

- [ ] **Step 5: Run the existing printer suite**

Run: `python3 -m unittest discover -s tests`

Expected: all existing and new tests pass.

- [ ] **Step 6: Commit**

```bash
git add print_service.py tests/test_print_service.py
git commit -m "Add single-job print service"
```

## Chunk 2: Flask app and browser interface

### Task 4: Add preview and job HTTP endpoints

**Files:**
- Create: `webapp.py`
- Create: `tests/test_webapp.py`

- [ ] **Step 1: Write failing Flask tests**

```python
import io
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock
from PIL import Image

from print_service import PrintServiceError
from webapp import create_app


def valid_text_form(**overrides):
    form = {"source_type": "text", "text": "Hello", "font_size": "24",
            "align": "left", "bold": "false", "dither": "false",
            "mac": "20:DC:8B:CD:CA:C0", "interline_feed": "1",
            "vertical_scale": "0.5"}
    form.update(overrides)
    return form


class FakePrintService:
    def __init__(self):
        self.busy, self.jobs, self.started = False, {}, []

    def start(self, prepared, *, mac, interline_feed):
        if self.busy:
            raise PrintServiceError("A print job is already in progress.")
        self.busy = True
        job_id = f"job-{len(self.started) + 1}"
        self.started.append((prepared, mac, interline_feed))
        self.jobs[job_id] = {"state": "preparing", "error": None}
        return job_id

    def get(self, job_id):
        if job_id not in self.jobs:
            raise KeyError(job_id)
        return self.jobs[job_id]


class WebAppTests(unittest.TestCase):
    def setUp(self):
        self.service = FakePrintService()
        self.tempdir = tempfile.TemporaryDirectory()
        self.app = create_app(print_service=self.service,
                              upload_tempdir=self.tempdir.name)
        self.client = self.app.test_client()

    def tearDown(self):
        self.tempdir.cleanup()

    def test_preview_returns_a_monochrome_png_for_text(self):
        response = self.client.post("/preview", data={
            "source_type": "text", "text": "Hello", "font_size": "24",
            "align": "left", "bold": "false", "dither": "false",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "image/png")

    def test_print_returns_202_and_job_id(self):
        response = self.client.post("/print", data=valid_text_form())
        self.assertEqual(response.status_code, 202)
        self.assertIn("job_id", response.get_json())

    def test_active_print_returns_409_json_error(self):
        self.service.busy = True
        response = self.client.post("/print", data=valid_text_form())
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["error"], "A print job is already in progress.")

    def test_job_lookup_and_unknown_job_statuses(self):
        self.service.jobs["job-1"] = {"state": "printing", "error": None}
        self.assertEqual(self.client.get("/jobs/job-1").get_json()["state"], "printing")
        self.assertEqual(self.client.get("/jobs/missing").status_code, 404)

    def test_invalid_settings_and_oversize_request_return_json_400(self):
        for form in (valid_text_form(source_type="other"),
                     valid_text_form(font_size="73"),
                     valid_text_form(align="diagonal"),
                     valid_text_form(mac="not-a-mac"),
                     valid_text_form(interline_feed="0"),
                     valid_text_form(vertical_scale="2.1")):
            response = self.client.post("/preview", data=form)
            self.assertEqual(response.status_code, 400)
            self.assertIn("error", response.get_json())
        response = self.client.post("/preview", data={"image": (io.BytesIO(b"x" * (10 * 1024 * 1024 + 1)), "large.png")})
        self.assertEqual(response.status_code, 400)

    def test_image_source_requires_an_upload_and_processing_failure_is_json_500(self):
        self.assertEqual(self.client.post("/preview", data={"source_type": "image"}).status_code, 400)
        invalid = self.client.post("/preview", data={"source_type": "image", "image": (io.BytesIO(b"not an image"), "bad.png")})
        self.assertEqual(invalid.status_code, 400)
        with mock.patch("webapp.prepare_ble_image", side_effect=RuntimeError("bad image")):
            response = self.client.post("/preview", data=valid_text_form())
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json(), {"error": "Could not prepare this print."})

    def test_image_preview_enforces_decoded_limit_and_cleans_temp_file(self):
        image = Image.new("L", (4000, 3001), "white")
        stream = io.BytesIO(); image.save(stream, "PNG"); stream.seek(0)
        response = self.client.post("/preview", data={"source_type": "image", "image": (stream, "large.png")})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(list(Path(self.tempdir.name).iterdir()), [])

    def test_print_rejects_prepared_height_above_limit(self):
        with mock.patch("webapp.prepare_ble_image", return_value=Image.new("1", (384, 2049), 1)):
            response = self.client.post("/print", data=valid_text_form())
        self.assertEqual(response.status_code, 400)

    def test_concurrent_print_requests_yield_one_202_and_one_409(self):
        class LockedService(FakePrintService):
            def __init__(self):
                super().__init__()
                self.lock = threading.Lock()

            def start(self, prepared, *, mac, interline_feed):
                with self.lock:
                    return super().start(prepared, mac=mac, interline_feed=interline_feed)

        service = LockedService()
        app = create_app(print_service=service, upload_tempdir=self.tempdir.name)
        barrier, statuses = threading.Barrier(2), []
        def post_print():
            client = app.test_client()
            barrier.wait()
            statuses.append(client.post("/print", data=valid_text_form()).status_code)
        threads = [threading.Thread(target=post_print) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertCountEqual(statuses, [202, 409])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest tests.test_webapp`

Expected: FAIL because `webapp` does not exist.

- [ ] **Step 3: Implement request parsing and routes**

```python
def create_app(*, print_service=None, upload_tempdir=None):
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
    app.register_error_handler(RequestEntityTooLarge, request_too_large)
    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000)
```

Make form parsing a small helper that returns source data plus settings. For
images, use `TemporaryDirectory(dir=upload_tempdir)` inside the request, save
the `image` multipart field there, open it with Pillow, call `verify()`, reopen
a detached copy, and reject decoded images above 12 megapixels. The context
manager must remove the file on every success or error path. For text, call
`render_text()`. Use the same helper for preview and print. Preview calls
`prepare_ble_image()` and sends an in-memory PNG with `send_file`. Print calls
the same preparation helper, rejects a prepared image taller than 2,048 rows,
then passes the prepared bitmap, MAC, and feed to `PrintService.start`. Convert
known validation errors to `400 {"error": ...}`, busy errors to the exact 409
JSON body, unknown jobs to 404, and unexpected preparation failures to the
exact 500 JSON body from the design.

Implement `request_too_large()` to return the same `400 {"error": "..."}`
shape as other invalid requests, rather than Flask's default HTML 413 response.
For every unexpected preparation exception, call `app.logger.exception()` before
returning the 500 JSON body. Test source type, missing image, text controls,
MAC shape, feed range, vertical scale range, byte limit, decoded-pixel limit,
prepared-height limit, job lookup, and the 400/409/500 JSON bodies shown in the
design.

- [ ] **Step 4: Run endpoint tests to verify they pass**

Run: `python3 -m unittest tests.test_webapp`

Expected: all endpoint tests pass.

- [ ] **Step 5: Commit**

```bash
git add webapp.py tests/test_webapp.py
git commit -m "Add local print web endpoints"
```

### Task 5: Build the focused browser page

**Files:**
- Create: `web/templates/index.html`
- Create: `web/static/app.css`
- Create: `web/static/app.mjs`
- Modify: `tests/test_webapp.py`
- Create: `tests/web_app_ui.test.mjs`

- [ ] **Step 1: Add failing page-contract tests**

```python
def test_index_contains_the_required_print_controls(self):
    response = self.client.get("/")
    page = response.get_data(as_text=True)
    for element_id in ("printer-address", "source-image", "source-text", "image-file",
                       "image-filename", "dither", "text-input", "font-size", "alignment",
                       "bold", "preview", "print-button", "status", "advanced-settings"):
        self.assertIn(f'id="{element_id}"', page)
```

```javascript
import test from "node:test";
import assert from "node:assert/strict";
import { createPrintController } from "../web/static/app.mjs";

test("preview, print, polling, and terminal button state", async () => {
  const requests = [];
  const states = [];
  const replies = [
    { ok: true, headers: { get: () => "image/png" }, blob: async () => new Blob() },
    { ok: true, json: async () => ({ job_id: "job-1" }) },
    { ok: true, json: async () => ({ state: "printing", error: null }) },
    { ok: true, json: async () => ({ state: "complete", error: null }) },
  ];
  const controller = createPrintController({
    fetch: async (url) => (requests.push(url), replies.shift()),
    formData: () => new FormData(),
    setPreview: () => states.push("preview"),
    setStatus: (state) => states.push(state),
    setPrintEnabled: (enabled) => states.push(enabled ? "enabled" : "disabled"),
    delay: async () => {},
  });
  await controller.refreshPreview();
  await controller.print();
  assert.deepEqual(requests, ["/preview", "/print", "/jobs/job-1", "/jobs/job-1"]);
  assert.deepEqual(states, ["preview", "disabled", "preparing", "printing", "complete", "enabled"]);
});
```

- [ ] **Step 2: Run the page test to verify it fails**

Run: `python3 -m unittest tests.test_webapp.WebAppTests.test_index_contains_the_required_print_controls && node --test tests/web_app_ui.test.mjs`

Expected: FAIL because the template and browser module are absent.

- [ ] **Step 3: Implement the page and client behavior**

Use semantic controls and labels. Keep Image and Text as radio buttons or
tabs, with only the selected source controls visible. Set the advanced fields
to MAC `20:DC:8B:CD:CA:C0`, feed `1`, and scale `0.5`. Make every source or
control change request a debounced `/preview` update; put the returned PNG in
`#preview`. On Print, submit the same `FormData` to `/print`, disable the Print
button, then poll `/jobs/<id>` every 500 ms until `complete` or `failed`.
Display server errors in `#status` and re-enable the button at terminal state.

Make `app.mjs` export a testable `createPrintController()` that receives the
browser dependencies used in the test above. The module's browser entry point
collects real DOM controls, builds `FormData`, and passes `window.fetch`,
`URL.createObjectURL`, and DOM update callbacks into that controller. The HTML
loads it with `<script type="module" src="/static/app.mjs"></script>`. Ensure
source changes make a debounced preview request, a failed preview leaves the
old preview visible and shows an error, a failed print re-enables the button,
and polling stops at either terminal job state.

CSS should keep the page compact and readable at desktop width, give the
preview an honest receipt-paper aspect, provide visible keyboard focus, and use
`prefers-reduced-motion` for any loading transition. Do not add accounts,
saved jobs, templates, or decorative printer simulation.

- [ ] **Step 4: Run the page-contract test to verify it passes**

Run: `python3 -m unittest tests.test_webapp.WebAppTests.test_index_contains_the_required_print_controls && node --test tests/web_app_ui.test.mjs`

Expected: PASS.

- [ ] **Step 5: Manually exercise the local page without a print**

Run: `python3 webapp.py`

Expected: Flask listens only on `http://127.0.0.1:5000`; open it in a browser,
switch between image and text, and confirm previews update. Stop the server
with Ctrl-C.

- [ ] **Step 6: Commit**

```bash
git add web/templates/index.html web/static/app.css web/static/app.mjs tests/test_webapp.py tests/web_app_ui.test.mjs
git commit -m "Add local print web interface"
```

### Task 6: Document and verify the complete feature

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add the local web-app instructions**

Document dependency install, `python3 -m pip install --user -r requirements.txt`,
the `python3 webapp.py` start command, local-only address, image/text use,
calibrated defaults, and the fact that a print job cannot be cancelled after
Bluetooth sending begins.

- [ ] **Step 2: Run the full automated suite**

Run: `python3 -m unittest discover -s tests`

Expected: all tests pass.

- [ ] **Step 3: Perform manual hardware acceptance**

Print one photo with dithering and one short text note from the browser. Verify
the photo has the established geometry and the note has correct alignment.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "Document local print web app"
```
