"""Capture-derived CTP500 ``BF`` run-length raster frame encoder."""

from ctp500_ble import build_a2_row, crc8, format_msg


CAPTURED_INIT_FRAMES = (
    bytes.fromhex("5178a40001003399ff"),
    bytes.fromhex("5178a60001000000ff"),
    bytes.fromhex("5178af000200b036cdff"),
    bytes.fromhex("5178be000200000107ff"),
    # The phone label capture uses 0x19 here. Image printing needs the
    # standard 0x1e line-feed speed to avoid vertically flattened output.
    bytes.fromhex("5178bd0001001e5aff"),
)
CAPTURED_FOOTER_FRAMES = (
    bytes.fromhex("5178bd000100146cff"),
    bytes.fromhex("5178a10002006000f5ff"),
    bytes.fromhex("5178a30001000000ff"),
)


def _encode_row(image, row: int) -> bytes:
    """Encode one row as runs: high bit is black, low seven bits are length."""
    pixels = image.load()
    encoded = bytearray()
    black = pixels[0, row] == 0
    length = 0
    for x in range(image.width):
        next_black = pixels[x, row] == 0
        if next_black != black or length == 127:
            encoded.append((0x80 if black else 0) | length)
            black = next_black
            length = 0
        length += 1
    encoded.append((0x80 if black else 0) | length)
    return bytes(encoded)


def build_bf_frame(data: bytes) -> bytes:
    """Build one BF frame from its payload data."""
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("data must be bytes")
    length = len(data)
    if length > 0xFFFF:
        raise ValueError("BF payload length must fit in 16 bits")
    data = bytes(data)
    return b"\x51\x78\xbf\x00" + length.to_bytes(2, "little") + data + bytes((crc8(data), 0xFF))


def encode_bf_frames(image) -> list[bytes]:
    """Encode a mode-1 image as deterministic per-row BF frames."""
    if getattr(image, "mode", None) != "1":
        raise ValueError("image must use mode '1'")
    width, height = image.size
    if width <= 0:
        raise ValueError("image width must be positive")
    if height <= 0:
        raise ValueError("image height must be positive")
    if width > 127 * 0xFFFF:
        raise ValueError("BF row payload is too large")
    return [build_bf_frame(_encode_row(image, row)) for row in range(height)]


build_bf_frames = encode_bf_frames


def build_print_frames(image, *, interline_feed=False) -> list[bytes]:
    """Build a complete image job using the phone capture's command sequence."""
    if image.width != 384:
        raise ValueError("image must be 384 pixels wide")
    frames = list(CAPTURED_INIT_FRAMES)
    if not 0 <= interline_feed <= 0xFF:
        raise ValueError("interline feed must fit in one byte")
    feed = format_msg(0xA1, bytes((interline_feed, 0)))
    for row, compressed in enumerate(encode_bf_frames(image)):
        packed = build_a2_row(image, row)
        frames.append(compressed if len(compressed) < len(packed) else packed)
        if interline_feed:
            frames.append(feed)
    return frames + list(CAPTURED_FOOTER_FRAMES)
