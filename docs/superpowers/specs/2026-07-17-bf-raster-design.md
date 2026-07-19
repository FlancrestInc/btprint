# CTP500 BF Raster Printing Design

## Goal

Print arbitrary images on the CTP500 over direct BLE using the printer's
observed `BF` drawing protocol. Images are resized to 384 pixels wide while
preserving aspect ratio.

## Approach

Add a raster encoder separate from the gatttool transport. It converts a
flattened, monochrome Pillow image into protocol frames modeled on the binary
PacketLogger capture. The encoder emits the observed command header, little-
endian payload length, packed row data, checksum, and `FF` terminator. The
transport sends the resulting frames unchanged.

The existing capture replay option remains available for regression testing.

## Validation

Unit tests will assert exact bytes for small synthetic images, valid frame
lengths and terminators, deterministic output, and aspect-ratio resizing.
The first hardware test will use the existing smoke image, then a small text
and shape image.

## Error handling

Unsupported or unreadable images fail through the existing CLI parser. Encoder
validation rejects malformed dimensions or impossible payload lengths before a
Bluetooth connection is opened.
