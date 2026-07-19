# CTP500 BLE/GATT printing design

## Goal

Print images from Linux using the same BLE/GATT protocol proven by the working
macOS script.

## Decision

Replace the RFCOMM transport with `bleak`. Scan with
`BleakScanner.find_device_by_address(address, timeout=10)`, connect the found
device with `BleakClient`, and write without response to
`0000ae01-0000-1000-8000-00805f9b34fb`. Do not use ESC/POS on this path.

## Data flow

1. Load and flatten the input image over white, then convert it to grayscale
   and apply autocontrast, as the working Mac flow does.
2. Resize it to the printer's 384-pixel width, preserving aspect ratio, then
   apply threshold or Floyd-Steinberg dithering.
3. Convert each row to the working A2 bitmap format. At 384 pixels, a row is
   exactly `51 78 A2 00 32 00 30 00 <48 packed bytes> <CRC8> FF`. The CRC-8
   covers only `30 00 <48 packed bytes>`. Pack MSB first: the leftmost black
   pixel is bit `0x80`.
4. Send these writes in this exact order. Init: `5178a80001000000ff5178a30001000000ff`
   as one write; `5178bb0001000107ff`; then, one write each,
   `5178a30001000000ff`, `5178a40001003399ff`,
   `5178a6000b00aa551738445f5f5f44382ca1ff`, `5178af000200e02e89ff`,
   `5178be0001000000ff`, `5178bd0001001e5aff`, and
   `5178bf0004007f7f7f03a8ff`. After each A2 row, write the one-step feed
   frame `5178a1000200010015ff`. Footer: one write each,
   `5178bf0004007f7f7f03a8ff`, `5178bd000100194fff`,
   `5178a10002003000f9ff`, `5178a10002003000f9ff`,
   `5178bd000100194fff`, `5178a6000b00aa5517000000000000001711ff`, and
   `5178a30001000000ff`. Use `response=False` and await `asyncio.sleep(0.03)`
   after every write.

## Boundaries

- Put deterministic BLE frame construction and 384-wide bitmap preparation in
  a new `ctp500_ble` module so it can be unit-tested without Bluetooth
  hardware. It must flatten alpha over white and retain `--dither` behavior.
- Keep `print.py` as the CLI and BLE connection boundary. Lazy-import `bleak`
  only after image preparation and dry-run handling.
- Preserve `--dither` and `--dry-run`. A dry run saves the 384-pixel-wide BLE
  bitmap and must not import `bleak`. Remove `--channel` and paired-device
  lookup.
- Preserve the positional `image [mac]` CLI shape. Its optional `mac` is now
  a BLE address, defaulting to `20:DC:8B:CD:CA:C0`.
- Report missing Bleak, discovery, connection, and write errors through
  `parser.error`.
- Document `bleak` as the runtime dependency in the existing README; remove RFCOMM
  and BlueZ paired-device commands from operator instructions.

## Verification

Unit-test CRC-8 data-only framing, MSB bit order, 384-width normalization,
every init and footer write, and the exact A1 row feed. Mock Bleak at the CLI
boundary to assert address discovery with its 10-second timeout, AE01 writes
with `response=False`, and a 30 ms delay after every write. Test missing Bleak,
discovery, connection, and write errors as parser errors. The asynchronous
transport wrapper catches these errors outside `asyncio.run` and lets the CLI
convert them with `parser.error`. Replace RFCOMM tests
and smoke instructions. Add a CLI regression test that dry run saves a
384-pixel-wide bitmap without importing `bleak`, plus a rendering test that
the post-resize `--dither` path uses Floyd-Steinberg. The new smoke test must
describe its scaled 384-pixel positions, not the original 32-pixel source
coordinates. Verify all tests and compilation locally, then run the asymmetric
hardware smoke test.
