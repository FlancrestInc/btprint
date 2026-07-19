# CTP500 Image Printing Implementation Plan

> **Superseded transport note:**
> `docs/superpowers/plans/2026-07-17-ble-gatt-printing.md` supersedes this
> plan's runtime transport. BLE/GATT replaces its Bluetooth Classic RFCOMM,
> PyBluez, and BlueZ CLI transport instructions.

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reliable Linux CLI that prints image files to a CTP500 over Bluetooth Classic RFCOMM.

**Architecture:** Put deterministic image preparation and ESC/POS byte generation in a small `ctp500` module, so it can be unit-tested without a printer. Keep `print.py` as the CLI/transport boundary: it resolves a paired device, opens RFCOMM, and sends a completed command stream.

**Tech Stack:** Python 3, Pillow, PyBluez, BlueZ `bluetoothctl`, unittest.

---

## Chunk 1: Deterministic raster protocol

### Task 1: Add failing protocol tests

**Files:**
- Create: `tests/test_ctp500.py`
- Create: `ctp500.py`

- [ ] **Step 1: Write failing tests for black-pixel packing and padding**

```python
import unittest
from PIL import Image
from ctp500 import pack_raster_rows

class CTP500ProtocolTests(unittest.TestCase):
    def test_pack_raster_rows_is_msb_first_and_right_pads_white(self):
        image = Image.new("1", (9, 1), 1)
        image.putpixel((0, 0), 0)
        image.putpixel((8, 0), 0)
        self.assertEqual(pack_raster_rows(image), b"\x80\x80")
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `python3 -m unittest tests.test_ctp500.CTP500ProtocolTests.test_pack_raster_rows_is_msb_first_and_right_pads_white -v`

Expected: FAIL because `ctp500` does not exist.

- [ ] **Step 3: Implement the minimal row packer in `ctp500.py`**

```python
def pack_raster_rows(image: Image.Image) -> bytes:
    if image.mode != "1":
        raise ValueError("image must be mode '1'")
    width, height = image.size
    row_bytes = (width + 7) // 8
    output = bytearray(row_bytes * height)
    for y in range(height):
        for x in range(width):
            if image.getpixel((x, y)) == 0:
                output[y * row_bytes + x // 8] |= 0x80 >> (x % 8)
    return bytes(output)
```

- [ ] **Step 4: Run the focused test to verify it passes**

Run: `python3 -m unittest tests.test_ctp500.CTP500ProtocolTests.test_pack_raster_rows_is_msb_first_and_right_pads_white -v`

Expected: PASS.

- [ ] **Step 5: Commit**

This workspace has no initialized Git metadata; skip the commit and record that limitation in the handoff.

### Task 2: Add a complete ESC/POS golden-payload test

**Files:**
- Modify: `tests/test_ctp500.py`
- Modify: `ctp500.py`

- [ ] **Step 1: Write the failing golden test**

At module scope, extend the imports from Task 1 with `from ctp500 import
build_print_stream`. Add the following methods to the existing
`CTP500ProtocolTests` class created in Task 1; do not define a second class.

```python
    def test_build_print_stream_has_ctp500_preamble_raster_and_finish(self):
        image = Image.new("1", (9, 2), 1)
        image.putpixel((0, 0), 0)
        image.putpixel((8, 1), 0)
        expected = (
            b"\x1d\x67\x39\x1e\x47\x03\x1d\x67\x69\x1b\x40\x1d\x49\xf0\x19"
            b"\x1d\x76\x30\x00\x02\x00\x02\x00"
            b"\x80\x00\x00\x80"
            b"\n\n\n\x1d\x56\x00"
        )
        self.assertEqual(build_print_stream(image), expected)

    def test_build_print_stream_rejects_height_larger_than_16_bit_field(self):
        image = Image.new("1", (1, 65536), 1)
        with self.assertRaises(ValueError):
            build_print_stream(image)
```

- [ ] **Step 2: Run it and verify it fails**

Run: `python3 -m unittest tests.test_ctp500.CTP500ProtocolTests.test_build_print_stream_has_ctp500_preamble_raster_and_finish -v`

Expected: FAIL because `build_print_stream` is missing.

- [ ] **Step 3: Implement `build_print_stream`**

Add named `PREAMBLE` and `FINISH` byte constants. Calculate `row_bytes = (width + 7) // 8`; reject height above `0xffff`; generate the header with `bytes((0x1d, 0x76, 0x30, 0, row_bytes & 0xff, row_bytes >> 8, height & 0xff, height >> 8))`; concatenate preamble, header, packed data, and finish.

- [ ] **Step 4: Run both protocol tests**

Run: `python3 -m unittest tests.test_ctp500 -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Skip because the workspace is not a Git repository.

## Chunk 2: Image normalization and command-line transport

### Task 3: Add failing rendering tests

**Files:**
- Modify: `tests/test_ctp500.py`
- Modify: `ctp500.py`

- [ ] **Step 1: Test 384-dot proportional downscaling and no upscale**

At module scope, extend the imports with `from ctp500 import prepare_image`.
Add the following method to the existing `CTP500ProtocolTests` class created
in Task 1; do not redefine the class.

```python
    def test_prepare_image_downscales_to_384_without_upscaling(self):
        wide = Image.new("RGB", (768, 100), "white")
        small = Image.new("RGB", (100, 50), "white")
        self.assertEqual(prepare_image(wide).size, (384, 50))
        self.assertEqual(prepare_image(small).size, (100, 50))
```

Add `CTP500ProtocolTests` methods which assert: transparent pixels in both an
`RGBA` image and a palette image with `info["transparency"]` render as white;
an input pixel value of 127 renders black while 128 renders white; and
`prepare_image(image, dither=True)` returns a mode-`1` image of the expected
dimensions.

- [ ] **Step 2: Run the test and verify it fails**

Run: `python3 -m unittest tests.test_ctp500.CTP500ProtocolTests.test_prepare_image_downscales_to_384_without_upscaling -v`

Expected: FAIL because `prepare_image` is missing.

- [ ] **Step 3: Implement `prepare_image`**

Open/accept a Pillow image. For any image that carries alpha (including `RGBA`,
`LA`, and palette images with `info["transparency"]`), convert to `RGBA` and
flatten with `Image.alpha_composite` onto an opaque white background; then
convert to `L`. Resize only when width exceeds 384 using
`Image.Resampling.LANCZOS`; use `point(lambda value: 0 if value < 128 else 255,
mode="1")` by default, and `convert("1", dither=Image.Dither.FLOYDSTEINBERG)`
when requested. Reject an output height above 65,535 here, rather than only in
stream construction, so both printing and `--dry-run` have the same limit.

- [ ] **Step 4: Run all protocol/rendering tests**

Run: `python3 -m unittest tests.test_ctp500 -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Skip because the workspace is not a Git repository.

### Task 4: Replace the BLE CLI with RFCOMM transport

**Files:**
- Modify: `print.py`
- Create: `tests/test_print_cli.py`

- [ ] **Step 1: Write a failing CLI unit test for parser defaults**

Use `importlib.util.spec_from_file_location` to load `print.py` as
`print_cli`. Add a `unittest.TestCase` that imports `build_parser` and asserts
that an image-only invocation uses no MAC, channel `1`, no dithering, and no
dry-run path.

Add mocked boundary tests for `resolve_printer_mac`: one exact paired-device
name match returns its address, while zero or multiple exact matches produce a
helpful failure that includes candidate addresses. Add a dry-run test using a
temporary image and temporary output path which asserts it saves an unpadded
mode-`1` image and never imports or connects via the `bluetooth` module. Add a
renderer test confirming an image taller than 65,535 pixels is rejected before
both transport and dry-run output.

- [ ] **Step 2: Run the test and verify it fails**

Run: `python3 -m unittest tests.test_print_cli -v`

Expected: FAIL because `build_parser` does not exist.

- [ ] **Step 3: Implement a standard-library CLI and transport boundary**

Use `argparse` with positional `image`, optional positional `mac`, `--channel`, `--dither`, and `--dry-run`. Load the image through `prepare_image`; save it when dry-running; otherwise resolve an absent MAC with `subprocess.run(["bluetoothctl", "paired-devices"], check=True, text=True, capture_output=True)`, requiring one exact `Mini Printer-DC20` device-name match. Lazily import `bluetooth`, connect `BluetoothSocket(bluetooth.RFCOMM)` to `(mac, channel)`, send the entire `build_print_stream` result via `sendall`, and always close the socket. Convert command, file, image, and Bluetooth failures into concise `parser.error` messages.

- [ ] **Step 4: Run all tests**

Run: `python3 -m unittest discover -v`

Expected: PASS.

- [ ] **Step 5: Perform static syntax validation**

Run: `python3 -m py_compile print.py ctp500.py`

Expected: no output and exit status 0.

- [ ] **Step 6: Commit**

Skip because the workspace is not a Git repository.

## Chunk 3: Operator documentation and hardware validation

### Task 5: Document setup and printing

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write README usage**

Document: `python3 -m pip install Pillow PyBluez`; paired-device confirmation with `bluetoothctl paired-devices`; image printing with both automatic name resolution and explicit MAC; `--dither`; and `--dry-run prepared.png`. Note that a CTP500 must be powered on and paired before printing.

- [ ] **Step 2: Add a manual asymmetric smoke-test procedure**

Give this directly runnable command to create the smoke-test image:

```bash
python3 -c 'from PIL import Image; im=Image.new("1", (32, 24), 1); im.putpixel((0, 0), 0); im.putpixel((8, 4), 0); [im.putpixel((x, 23), 0) for x in range(24, 32)]; im.save("ctp500-smoke.png")'
```

Acceptance: the printed output has the same orientation, no clipping, no
shifted columns, and no unexpected blank bands.

- [ ] **Step 3: Verify all automated checks after documentation edits**

Run: `python3 -m unittest discover -v && python3 -m py_compile print.py ctp500.py`

Expected: all tests pass and compilation emits no output.

- [ ] **Step 4: Commit**

Skip because the workspace is not a Git repository.
