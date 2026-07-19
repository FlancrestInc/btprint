# CTP500 Bluetooth Image Printing

Print a Pillow-readable image to a CTP500-compatible thermal printer over BLE/GATT on Linux.

## Requirements

- Python 3 and Pillow. Install Pillow with pip:

  ```bash
  python3 -m pip install --user Pillow
  ```

- BlueZ `gatttool` on `PATH`. `gatttool` is a system executable, not a Python
  dependency. If it is missing, the CLI exits with the concise error
  `gatttool executable was not found`.

- A CTP500 that is powered on and awake.

This host uses adapter `hci0`, the printer's public BLE MAC address, and no
pairing. Printing connects directly to the address; there is no RFCOMM channel,
`bluetoothctl` paired-device lookup, or PyBluez dependency.

## Print an image

Print directly to the printer BLE address:

```bash
python3 print.py ctp500-smoke.png 20:DC:8B:CD:CA:C0
```

The known printer address is already the optional MAC default, so this also
works:

```bash
python3 print.py photo.png
```

Use Floyd-Steinberg dithering for photographs:

```bash
python3 print.py photo.png --dither
```

Normal printing uses the calibrated paper settings: one feed step after every
row and `--vertical-scale 0.5`. Use the tuning flags only if a different paper
or printer needs adjustment:

```bash
python3 print.py photo.png --dither --interline-feed 1 --vertical-scale 0.5
```

For the clearest results, use a photo with good contrast. Very small text,
one-pixel checkerboards, and other fine detail are below the printer's useful
physical resolution.

Images are resized to fit a 380-pixel content area with a four-pixel white
inset at the top and left, preserving aspect ratio and preventing the
printer's edge margin from clipping content. Each row uses the printer's native
run-length (`BF`) format, with automatic fallback to the raw bitmap (`A2`)
format for dense rows. The setup, feed, and finish frames match the successful
phone capture.

Prepare the 384-pixel-wide BLE bitmap without connecting to Bluetooth:

```bash
python3 print.py photo.png --dry-run prepared.png
```

Dry runs do not start `gatttool` or any subprocess.

## Replay a captured phone print

To replay the exact outgoing print frames from an Apple PacketLogger capture:

```bash
python3 print.py ctp500-smoke.png --replay-pklg '/mnt/Eddy/music/iostrace.pklg'
```

The image argument is required by the CLI but is ignored during replay.

## Asymmetric smoke test

Create the test image:

```bash
python3 -c 'from PIL import Image; im=Image.new("1", (32, 24), 1); im.putpixel((0, 0), 0); im.putpixel((8, 4), 0); [im.putpixel((x, 23), 0) for x in range(24, 32)]; im.save("ctp500-smoke.png")'
```

BLE normalization scales the 32x24 source to 384 pixels wide. The output should
have a black dot near the upper left, a second near `(96, 48)`, and the
eight-pixel source band at the bottom right scaled across the bottom-right
quarter. This confirms orientation, columns, and the bottom edge, with no
clipping or blank bands. Print it directly with:

```bash
python3 print.py ctp500-smoke.png 20:DC:8B:CD:CA:C0
```
