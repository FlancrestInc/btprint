from PIL import Image

PREAMBLE = b"\x1d\x67\x39\x1e\x47\x03\x1d\x67\x69\x1b\x40\x1d\x49\xf0\x19"
FINISH = b"\n\n\n\x1d\x56\x00"
RESAMPLING = getattr(Image, "Resampling", Image)
DITHER = getattr(Image, "Dither", Image)


def prepare_image(source: Image.Image, dither: bool = False) -> Image.Image:
    has_alpha = source.mode in {"RGBA", "LA"} or (
        source.mode == "P" and "transparency" in source.info
    )
    if has_alpha:
        rgba = source.convert("RGBA")
        background = Image.new("RGBA", rgba.size, "white")
        image = Image.alpha_composite(background, rgba).convert("L")
    else:
        image = source.convert("L")

    width, height = image.size
    if width > 384:
        height = max(1, round(height * 384 / width))
        image = image.resize((384, height), RESAMPLING.LANCZOS)

    if image.height > 0xFFFF:
        raise ValueError("image height must fit in a 16-bit raster header")

    if dither:
        return image.convert("1", dither=DITHER.FLOYDSTEINBERG)
    return image.point(lambda value: 0 if value <= 127 else 255, "1")


def pack_raster_rows(image: Image.Image) -> bytes:
    if image.mode != "1":
        raise ValueError("image must use mode '1'")

    width, height = image.size
    pixels = image.load()
    raster = bytearray()
    for y in range(height):
        for start_x in range(0, width, 8):
            byte = 0
            for bit in range(8):
                x = start_x + bit
                if x < width and pixels[x, y] == 0:
                    byte |= 1 << (7 - bit)
            raster.append(byte)
    return bytes(raster)


def build_print_stream(image: Image.Image) -> bytes:
    width, height = image.size
    if width <= 0:
        raise ValueError("image width must be positive")
    if height <= 0:
        raise ValueError("image height must be positive")
    if height > 0xFFFF:
        raise ValueError("image height must fit in a 16-bit raster header")

    bytes_per_row = (width + 7) // 8
    if bytes_per_row > 0xFFFF:
        raise ValueError("row width must fit in a 16-bit raster header")

    raster_header = (
        b"\x1d\x76\x30\x00"
        + bytes_per_row.to_bytes(2, "little")
        + height.to_bytes(2, "little")
    )
    return PREAMBLE + raster_header + pack_raster_rows(image) + FINISH
