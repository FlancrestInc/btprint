"""CTP500 BLE frame building and image preparation helpers."""

from pathlib import Path

from PIL import Image, ImageOps


WRITE_UUID = "0000ae01-0000-1000-8000-00805f9b34fb"
WRITE_DELAY_SECONDS = 0.03
PRINT_WIDTH = 384
EDGE_INSET = 4

def crc8(data: bytes) -> int:
    value = 0
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = ((value << 1) ^ 0x07) & 0xFF if value & 0x80 else (value << 1) & 0xFF
    return value


def format_msg(cmd: int, data: bytes) -> bytes:
    if not 0 <= cmd <= 0xFF:
        raise ValueError("cmd must fit in one byte")
    if len(data) > 0xFF:
        raise ValueError("data must fit in one frame")
    return bytes((0x51, 0x78, cmd, 0x00, len(data), 0x00)) + data + bytes((crc8(data), 0xFF))


INIT_FRAMES = (
    bytes.fromhex("5178a80001000000ff5178a30001000000ff"),
    bytes.fromhex("5178bb0001000107ff"),
    bytes.fromhex("5178a30001000000ff"),
    bytes.fromhex("5178a40001003399ff"),
    bytes.fromhex("5178a6000b00aa551738445f5f5f44382ca1ff"),
    bytes.fromhex("5178af000200e02e89ff"),
    bytes.fromhex("5178be0001000000ff"),
    bytes.fromhex("5178bd0001001e5aff"),
    bytes.fromhex("5178bf0004007f7f7f03a8ff"),
)
FOOTER_FRAMES = (
    bytes.fromhex("5178bf0004007f7f7f03a8ff"),
    bytes.fromhex("5178bd000100194fff"),
    bytes.fromhex("5178a10002003000f9ff"),
    bytes.fromhex("5178a10002003000f9ff"),
    bytes.fromhex("5178bd000100194fff"),
    bytes.fromhex("5178a6000b00aa5517000000000000001711ff"),
    bytes.fromhex("5178a30001000000ff"),
)


def _open_image(source):
    if isinstance(source, (str, Path)):
        with Image.open(source) as image:
            return image.copy()
    return source.copy()


def prepare_ble_image(source, dither: bool = False, vertical_scale: float = 1):
    if not isinstance(vertical_scale, (int, float)) or vertical_scale <= 0:
        raise ValueError("vertical scale must be positive")
    image = _open_image(source)
    if image.width <= 0 or image.height <= 0:
        raise ValueError("source image must have positive width and height")
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        background = Image.new("RGBA", image.size, "white")
        background.alpha_composite(image.convert("RGBA"))
        image = background.convert("L")
    else:
        image = image.convert("L")
    image = ImageOps.autocontrast(image)
    content_width = PRINT_WIDTH - EDGE_INSET
    height = max(1, int(image.height * (content_width / image.width)))
    if height + EDGE_INSET > 0xFFFF:
        raise ValueError("scaled image height exceeds 65535 rows")
    image = image.resize((content_width, height))
    canvas = Image.new("L", (PRINT_WIDTH, height + EDGE_INSET), "white")
    canvas.paste(image, (EDGE_INSET, EDGE_INSET))
    scaled_height = max(1, round(canvas.height * vertical_scale))
    if scaled_height > 0xFFFF:
        raise ValueError("vertically scaled image height exceeds 65535 rows")
    image = (
        canvas
        if scaled_height == canvas.height
        else canvas.resize((PRINT_WIDTH, scaled_height), Image.NEAREST)
    )
    return image.convert("1", dither=Image.FLOYDSTEINBERG if dither else Image.NONE)


def stretch_vertical(image, factor):
    """Resize monochrome rows to compensate for coarse paper stepping."""
    if not isinstance(factor, (int, float)) or factor <= 0:
        raise ValueError("vertical scale must be positive")
    if factor == 1:
        return image
    if image.mode != "1" or image.width != PRINT_WIDTH:
        raise ValueError("image must be a 384-pixel-wide mode-1 image")
    height = max(1, round(image.height * factor))
    if height > 0xFFFF:
        raise ValueError("vertically scaled image height exceeds 65535 rows")
    return image.resize((PRINT_WIDTH, height), Image.NEAREST)


def build_a2_row(image, row_index: int) -> bytes:
    if image.mode != "1" or image.width != 384:
        raise ValueError("image must be a 384-pixel-wide mode-1 image")
    if not 0 <= row_index < image.height:
        raise IndexError("row index is outside the image")
    packed = bytearray()
    for offset in range(0, 384, 8):
        byte = 0
        for bit in range(8):
            if image.getpixel((offset + bit, row_index)) == 0:
                byte |= 1 << bit
        packed.append(byte)
    return format_msg(0xA2, bytes(packed))


def build_print_frames(image) -> list[bytes]:
    rows = [build_a2_row(image, row) for row in range(image.height)]
    feed = format_msg(0xA1, b"\x01\x00")
    frames = list(INIT_FRAMES)
    for row in rows:
        frames.extend((row, feed))
    return frames + list(FOOTER_FRAMES)
