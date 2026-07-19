import unittest
from unittest.mock import MagicMock, patch

from PIL import Image, ImageOps

import ctp500_ble


class Ctp500BleTests(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(
            ctp500_ble.WRITE_UUID, "0000ae01-0000-1000-8000-00805f9b34fb"
        )
        self.assertEqual(ctp500_ble.WRITE_DELAY_SECONDS, 0.03)

    def test_crc8_is_calculated_over_data_only(self):
        self.assertEqual(ctp500_ble.crc8(b"\x30\x00"), 0xF9)
        self.assertEqual(
            ctp500_ble.format_msg(0xA1, b"\x01\x00").hex(),
            "5178a1000200010015ff",
        )

    def test_build_a2_row_packs_leftmost_black_as_lsb_without_a_prefix(self):
        image = Image.new("1", (384, 1), 1)
        for x in (0, 7, 8, 383):
            image.putpixel((x, 0), 0)
        self.assertEqual(
            ctp500_ble.build_a2_row(image, 0).hex(),
            "5178a20030008101" + "00" * 45 + "8047ff",
        )

    def test_build_a2_row_validates_image_and_row(self):
        with self.assertRaises(ValueError):
            ctp500_ble.build_a2_row(Image.new("L", (384, 1)), 0)
        with self.assertRaises(ValueError):
            ctp500_ble.build_a2_row(Image.new("1", (383, 1)), 0)
        with self.assertRaises(IndexError):
            ctp500_ble.build_a2_row(Image.new("1", (384, 1)), 1)

    def test_init_frames_are_immutable_and_keep_first_two_frames_combined(self):
        self.assertIsInstance(ctp500_ble.INIT_FRAMES, tuple)
        self.assertEqual(
            [frame.hex() for frame in ctp500_ble.INIT_FRAMES],
            [
                "5178a80001000000ff5178a30001000000ff",
                "5178bb0001000107ff",
                "5178a30001000000ff",
                "5178a40001003399ff",
                "5178a6000b00aa551738445f5f5f44382ca1ff",
                "5178af000200e02e89ff",
                "5178be0001000000ff",
                "5178bd0001001e5aff",
                "5178bf0004007f7f7f03a8ff",
            ],
        )

    def test_footer_frames_are_immutable_and_exact(self):
        self.assertIsInstance(ctp500_ble.FOOTER_FRAMES, tuple)
        self.assertEqual(
            [frame.hex() for frame in ctp500_ble.FOOTER_FRAMES],
            [
                "5178bf0004007f7f7f03a8ff",
                "5178bd000100194fff",
                "5178a10002003000f9ff",
                "5178a10002003000f9ff",
                "5178bd000100194fff",
                "5178a6000b00aa5517000000000000001711ff",
                "5178a30001000000ff",
            ],
        )

    def test_build_print_frames_has_exact_one_row_ordering(self):
        image = Image.new("1", (384, 1), 1)
        image.putpixel((0, 0), 0)
        frames = ctp500_ble.build_print_frames(image)
        self.assertEqual(
            frames,
            list(ctp500_ble.INIT_FRAMES)
            + [
                bytes.fromhex("5178a200300001" + "00" * 47 + "08ff"),
                bytes.fromhex("5178a1000200010015ff"),
            ]
            + list(ctp500_ble.FOOTER_FRAMES),
        )

    def test_prepare_resizes_32px_wide_image_to_384px(self):
        image = Image.new("L", (32, 4), 128)
        result = ctp500_ble.prepare_ble_image(image)
        self.assertEqual(result.mode, "1")
        self.assertEqual(result.size, (384, 51))

    def test_prepare_insets_content_from_the_top_and_left_print_edges(self):
        image = Image.new("1", (1, 1), 0)
        result = ctp500_ble.prepare_ble_image(image)
        self.assertEqual(result.size, (384, 384))
        self.assertEqual(result.getpixel((0, 0)), 255)
        self.assertEqual(result.getpixel((3, 3)), 255)
        self.assertEqual(result.getpixel((4, 4)), 0)

    def test_prepare_flattens_transparent_pixels_over_white(self):
        image = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        result = ctp500_ble.prepare_ble_image(image)
        self.assertEqual(result.size, (384, 384))
        self.assertEqual(set(result.getdata()), {255})

    def test_prepare_autocontrasts_before_resize_then_uses_floyd_steinberg(self):
        image = Image.new("L", (2, 1))
        image.putdata([100, 150])
        content = ImageOps.autocontrast(image).resize((380, 190))
        expected = Image.new("L", (384, 194), "white")
        expected.paste(content, (4, 4))
        expected = expected.convert("1", dither=Image.FLOYDSTEINBERG)
        self.assertEqual(
            ctp500_ble.prepare_ble_image(image, dither=True).tobytes(), expected.tobytes()
        )

    def test_prepare_scales_grayscale_canvas_before_dithering(self):
        image = Image.new("L", (2, 1))
        image.putdata([100, 150])
        content = ImageOps.autocontrast(image).resize((380, 190))
        expected = Image.new("L", (384, 194), "white")
        expected.paste(content, (4, 4))
        expected = expected.resize((384, 97), Image.NEAREST)
        expected = expected.convert("1", dither=Image.FLOYDSTEINBERG)

        result = ctp500_ble.prepare_ble_image(
            image, dither=True, vertical_scale=0.5
        )

        self.assertEqual(result.size, (384, 97))
        self.assertEqual(result.tobytes(), expected.tobytes())

    def test_path_input_is_closed_after_a_detached_copy_is_made(self):
        opened = MagicMock()
        opened.__enter__.return_value = Image.new("L", (1, 1), 255)
        with patch.object(ctp500_ble.Image, "open", return_value=opened):
            result = ctp500_ble.prepare_ble_image("sample.png")
        opened.__enter__.assert_called_once_with()
        opened.__exit__.assert_called_once()
        self.assertEqual(result.size, (384, 384))

    def test_prepare_rejects_scaled_height_above_uint16(self):
        image = Image.new("L", (1, 173), 255)
        with self.assertRaises(ValueError):
            ctp500_ble.prepare_ble_image(image)

    def test_vertical_stretch_repeats_rows_with_nearest_neighbor_pixels(self):
        image = Image.new("1", (384, 2), 1)
        image.putpixel((0, 0), 0)
        image.putpixel((1, 1), 0)
        result = ctp500_ble.stretch_vertical(image, 3)
        self.assertEqual(result.size, (384, 6))
        self.assertEqual([result.getpixel((0, y)) for y in range(6)], [0, 0, 0, 1, 1, 1])
        self.assertEqual([result.getpixel((1, y)) for y in range(6)], [1, 1, 1, 0, 0, 0])

    def test_vertical_stretch_accepts_a_fractional_scale(self):
        image = Image.new("1", (384, 10), 1)
        self.assertEqual(ctp500_ble.stretch_vertical(image, 0.4).size, (384, 4))

    def test_prepare_rejects_zero_width_source(self):
        with self.assertRaisesRegex(ValueError, "positive width and height"):
            ctp500_ble.prepare_ble_image(Image.new("L", (0, 1)))

    def test_prepare_rejects_zero_height_source(self):
        with self.assertRaisesRegex(ValueError, "positive width and height"):
            ctp500_ble.prepare_ble_image(Image.new("L", (1, 0)))


if __name__ == "__main__":
    unittest.main()
