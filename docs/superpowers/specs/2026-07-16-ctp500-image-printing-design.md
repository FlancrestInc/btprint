# CTP500 image printing design

## Goal

Provide a reliable Linux command-line path to print image files on a Core
Innovations CTP500 (advertised as `Mini Printer-DC20`).  Keep the input and
rendering layer suitable for adding text and PDF inputs later.

## Approach

Use Bluetooth Classic RFCOMM channel 1 and the printer's ESC/POS raster-image
commands.  The prior BLE implementation is replaced because the CTP500-specific
reference implementation uses RFCOMM/ESC-POS and the old per-row bit packing
likely explains the mirrored/corrupt output.

## Command-line interface

`python3 print.py IMAGE [MAC] [--dither] [--dry-run OUTPUT]`

- `IMAGE` is a Pillow-readable image file.
- `MAC` is optional. When absent, the tool runs `bluetoothctl paired-devices`,
  selects the sole exact `Mini Printer-DC20` match, and fails with the matching
  addresses if zero or multiple devices match. The RFCOMM channel defaults to
  1 and can be overridden with `--channel`.
- `--dither` uses Floyd-Steinberg dithering; threshold rendering is the default.
- `--dry-run OUTPUT` writes the prepared, unpadded 1-bit PNG and does not
  connect to a printer.

## Rendering and data flow

1. Load the source image, flatten transparency against white, and convert it to
   grayscale.
2. Resize proportionally to a maximum 384-dot width without enlarging smaller
   images. Height is limited only by the 16-bit ESC/POS raster command field
   (65,535 rows); larger images fail clearly.
3. Use Pillow grayscale conversion and a fixed threshold of 128, or Pillow
   Floyd-Steinberg dithering with `--dither`, to make dry runs repeatable.
4. Right-pad each row with white dots to its next full byte. Represent black
   dots as set bits and pack each row MSB first, which matches ESC/POS raster
   data. The visual image remains left-aligned.
5. Send the CTP500-tested preamble `1D 67 39`, `1E 47 03`, `1D 67 69`,
   `1B 40`, and `1D 49 F0 19`; then issue `GS v 0` in mode 0 with bytes
   `1D 76 30 00 xL xH yL yH`, followed by the packed rows. `xL/xH` are the
   little-endian count of bytes per row and `yL/yH` are the little-endian row
   count. Finish with three line feeds and `1D 56 00`, matching the known
   working CTP500 stream.

## Error handling

Validate input files and arguments before connecting. Report useful errors for
missing dependencies, unresolved Bluetooth devices, failed RFCOMM connections,
and unsupported image data. Close the socket in all cases.

## Verification

Unit-test image normalization and raster packing, including a byte-level golden
payload for a tiny asymmetric bitmap. It must assert command bytes, dimensions,
polarity, MSB-first orientation, and white right-padding. Use `--dry-run` to
inspect the exact rendered output without consuming paper, then print an
asymmetric smoke-test pattern with distinct left/right and top/bottom features.
Successful output has no reversal, clipping, byte-boundary corruption, or
unexpected blank/mirrored regions.
