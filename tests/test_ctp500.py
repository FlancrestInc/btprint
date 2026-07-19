import unittest
from unittest import mock

from PIL import Image

from ctp500 import build_print_stream, pack_raster_rows, prepare_image


class CTP500ProtocolTests(unittest.TestCase):
    def test_prepare_image_resizes_wide_sources_without_upscaling_narrow_ones(self):
        wide = Image.new("L", (768, 100), 0)
        narrow = Image.new("L", (100, 50), 0)

        self.assertEqual(prepare_image(wide).size, (384, 50))
        self.assertEqual(prepare_image(narrow).size, (100, 50))

    def test_prepare_image_resizes_with_lanczos(self):
        image = Image.new("L", (768, 100), 0)
        lanczos = getattr(Image, "Resampling", Image).LANCZOS
        original_resize = Image.Image.resize

        with mock.patch.object(
            Image.Image, "resize", autospec=True, side_effect=original_resize
        ) as resize:
            prepare_image(image)

        resize.assert_called_once_with(mock.ANY, (384, 50), lanczos)

    def test_prepare_image_flattens_transparent_rgba_pixels_over_white(self):
        image = Image.new("RGBA", (2, 1), (0, 0, 0, 255))
        image.putpixel((1, 0), (0, 0, 0, 0))

        prepared = prepare_image(image)

        self.assertEqual(prepared.mode, "1")
        self.assertEqual([prepared.getpixel((x, 0)) for x in range(2)], [0, 255])

    def test_prepare_image_flattens_transparent_la_pixels_over_white(self):
        image = Image.new("LA", (2, 1), (0, 255))
        image.putpixel((0, 0), (0, 255))
        image.putpixel((1, 0), (0, 0))

        prepared = prepare_image(image)

        self.assertEqual([prepared.getpixel((x, 0)) for x in range(2)], [0, 255])

    def test_prepare_image_flattens_transparent_palette_pixels_over_white(self):
        image = Image.new("P", (2, 1))
        image.putpalette([0, 0, 0, 0, 0, 0] + [0] * 762)
        image.putdata([0, 1])
        image.info["transparency"] = 1

        prepared = prepare_image(image)

        self.assertEqual([prepared.getpixel((x, 0)) for x in range(2)], [0, 255])

    def test_prepare_image_threshold_makes_127_black_and_128_white(self):
        image = Image.new("L", (2, 1))
        image.putdata([127, 128])

        self.assertEqual(
            [prepare_image(image).getpixel((x, 0)) for x in range(2)], [0, 255]
        )

    def test_prepare_image_dither_returns_mode_one_at_source_dimensions(self):
        image = Image.linear_gradient("L").resize((100, 50))

        prepared = prepare_image(image, dither=True)

        self.assertEqual(prepared.mode, "1")
        self.assertEqual(prepared.size, (100, 50))

    def test_prepare_image_dither_distributes_uniform_midgray_between_black_and_white(self):
        image = Image.new("L", (8, 8), 128)

        prepared = prepare_image(image, dither=True)

        self.assertEqual(set(prepared.getdata()), {0, 255})

    def test_prepare_image_dither_uses_floyd_steinberg(self):
        image = Image.new("L", (8, 8), 128)
        floyd_steinberg = getattr(Image, "Dither", Image).FLOYDSTEINBERG
        original_convert = Image.Image.convert

        with mock.patch.object(
            Image.Image, "convert", autospec=True, side_effect=original_convert
        ) as convert:
            prepare_image(image, dither=True)

        self.assertIn(
            mock.call(mock.ANY, "1", dither=floyd_steinberg), convert.call_args_list
        )

    def test_prepare_image_rejects_height_that_does_not_fit_raster_header(self):
        image = Image.new("L", (1, 65536), 255)

        with self.assertRaisesRegex(ValueError, "height must fit"):
            prepare_image(image)

    def test_packs_black_pixels_msb_first_with_white_right_padding(self):
        image = Image.new("1", (9, 1), 1)
        image.putpixel((0, 0), 0)
        image.putpixel((8, 0), 0)

        self.assertEqual(pack_raster_rows(image), b"\x80\x80")

    def test_builds_complete_print_stream(self):
        image = Image.new("1", (9, 2), 1)
        image.putpixel((0, 0), 0)
        image.putpixel((8, 1), 0)

        preamble = b"\x1d\x67\x39\x1e\x47\x03\x1d\x67\x69\x1b\x40\x1d\x49\xf0\x19"
        raster_header = b"\x1d\x76\x30\x00\x02\x00\x02\x00"
        raster = b"\x80\x00\x00\x80"
        finish = b"\n\n\n\x1d\x56\x00"

        self.assertEqual(
            build_print_stream(image), preamble + raster_header + raster + finish
        )

    def test_rejects_height_that_does_not_fit_raster_header(self):
        image = Image.new("1", (1, 65536), 1)

        with self.assertRaises(ValueError):
            build_print_stream(image)

    def test_rejects_zero_width(self):
        image = Image.new("1", (0, 1), 1)

        with self.assertRaisesRegex(ValueError, "width must be positive"):
            build_print_stream(image)

    def test_rejects_zero_height(self):
        image = Image.new("1", (1, 0), 1)

        with self.assertRaisesRegex(ValueError, "height must be positive"):
            build_print_stream(image)

    def test_rejects_width_that_exceeds_raster_header_limit(self):
        image = Image.new("1", (524281, 1), 1)

        with self.assertRaisesRegex(ValueError, "row width must fit"):
            build_print_stream(image)
