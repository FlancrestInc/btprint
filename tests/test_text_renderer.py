import unittest
from unittest import mock

from PIL import ImageOps

from text_renderer import TextRenderError, render_text


class TextRendererTests(unittest.TestCase):
    def test_renders_380_pixel_wide_grayscale_image(self):
        image = render_text("Hello", font_size=24, align="left", bold=False)

        self.assertEqual(image.mode, "L")
        self.assertEqual(image.width, 380)
        self.assertGreater(image.height, 0)

    def test_rejects_blank_and_overlong_text(self):
        with self.assertRaisesRegex(TextRenderError, "text"):
            render_text("   ", font_size=24, align="left", bold=False)
        with self.assertRaisesRegex(TextRenderError, "2,000"):
            render_text("x" * 2001, font_size=24, align="left", bold=False)

    def test_rejects_invalid_font_size_and_alignment(self):
        with self.assertRaisesRegex(TextRenderError, "font size"):
            render_text("Hello", font_size=11, align="left", bold=False)
        with self.assertRaisesRegex(TextRenderError, "alignment"):
            render_text("Hello", font_size=24, align="diagonal", bold=False)

    def test_wraps_long_text(self):
        image = render_text("wideword " * 100, font_size=24, align="left", bold=False)

        self.assertGreater(image.height, round(24 * 1.25))

    def test_rejects_text_that_would_exceed_4096_rows(self):
        with self.assertRaisesRegex(TextRenderError, "4,096"):
            render_text("word " * 400, font_size=72, align="left", bold=False)

    def test_uses_125_percent_line_spacing(self):
        with mock.patch("text_renderer.ImageDraw.Draw") as draw, \
             mock.patch("text_renderer.ImageFont.truetype"):
            draw.return_value.textbbox.return_value = (0, 0, 10, 20)
            render_text("one\ntwo", font_size=24, align="left", bold=False)

        positions = [call.args[0] for call in draw.return_value.text.call_args_list]
        self.assertEqual(positions[1][1] - positions[0][1], 30)

    def test_each_alignment_moves_ink(self):
        boxes = [
            ImageOps.invert(render_text("X", font_size=24, align=align, bold=False)).getbbox()
            for align in ("left", "center", "right")
        ]

        self.assertLess(boxes[0][0], boxes[1][0])
        self.assertLess(boxes[1][0], boxes[2][0])

    def test_missing_font_is_a_render_error(self):
        with mock.patch("text_renderer.ImageFont.truetype", side_effect=OSError):
            with self.assertRaisesRegex(TextRenderError, "font"):
                render_text("Hello", font_size=24, align="left", bold=False)
