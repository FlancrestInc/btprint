"""Render validated receipt text into a Pillow image."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


CONTENT_WIDTH = 380
MIN_FONT_SIZE = 12
MAX_FONT_SIZE = 72
MAX_TEXT_LENGTH = 2_000
MAX_RENDERED_HEIGHT = 4_096
FONT_DIRECTORY = Path("/usr/share/fonts/truetype/dejavu")
REGULAR_FONT = FONT_DIRECTORY / "DejaVuSans.ttf"
BOLD_FONT = FONT_DIRECTORY / "DejaVuSans-Bold.ttf"


class TextRenderError(ValueError):
    """Raised when text cannot be rendered as a receipt image."""


def render_text(text, *, font_size, align, bold):
    """Return a white, 380-pixel-wide grayscale image containing plain text."""
    _validate(text, font_size, align)
    font = _load_font(font_size, bold)
    measure = ImageDraw.Draw(Image.new("L", (CONTENT_WIDTH, 1), "white"))
    lines = _wrap_lines(text.strip(), font, measure)
    line_spacing = round(font_size * 1.25)
    line_boxes = [measure.textbbox((0, 0), line, font=font) for line in lines]
    last_bottom = max(box[3] for box in line_boxes)
    height = (len(lines) - 1) * line_spacing + last_bottom
    if height > MAX_RENDERED_HEIGHT:
        raise TextRenderError("rendered text must not exceed 4,096 rows")

    image = Image.new("L", (CONTENT_WIDTH, max(1, height)), "white")
    draw = ImageDraw.Draw(image)
    for index, (line, box) in enumerate(zip(lines, line_boxes)):
        ink_width = box[2] - box[0]
        if align == "left":
            x = 0
        elif align == "center":
            x = (CONTENT_WIDTH - ink_width) // 2 - box[0]
        else:
            x = CONTENT_WIDTH - ink_width - box[0]
        draw.text((x, index * line_spacing), line, font=font, fill="black")
    return image


def _validate(text, font_size, align):
    if not isinstance(text, str) or not text.strip():
        raise TextRenderError("text must not be blank")
    if len(text) > MAX_TEXT_LENGTH:
        raise TextRenderError("text must not exceed 2,000 characters")
    if isinstance(font_size, bool) or not isinstance(font_size, int) or not MIN_FONT_SIZE <= font_size <= MAX_FONT_SIZE:
        raise TextRenderError("font size must be between 12 and 72")
    if align not in ("left", "center", "right"):
        raise TextRenderError("alignment must be left, center, or right")


def _load_font(font_size, bold):
    font_path = BOLD_FONT if bold else REGULAR_FONT
    if not font_path.is_file():
        raise TextRenderError("required font is unavailable")
    try:
        return ImageFont.truetype(str(font_path), font_size)
    except OSError as error:
        raise TextRenderError("required font is unavailable") from error


def _wrap_lines(text, font, draw):
    lines = []
    for paragraph in text.splitlines() or [""]:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        line = words[0]
        for word in words[1:]:
            candidate = f"{line} {word}"
            if _text_width(candidate, font, draw) <= CONTENT_WIDTH:
                line = candidate
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def _text_width(text, font, draw):
    left, _top, right, _bottom = draw.textbbox((0, 0), text, font=font)
    return right - left
