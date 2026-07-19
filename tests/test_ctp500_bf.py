import pytest
from PIL import Image

from ctp500_bf import build_bf_frame, build_print_frames, encode_bf_frames
from ctp500_ble import crc8


def test_bf_frame_prefix_length_checksum_and_trailer():
    frame = build_bf_frame(b"\x00\x7f\x7f\x7f")
    assert frame[:4] == b"\x51\x78\xbf\x00"
    assert int.from_bytes(frame[4:6], "little") == 4
    assert frame[6:-2] == b"\x00\x7f\x7f\x7f"
    assert frame[-2:] == bytes((crc8(frame[6:-2]), 0xFF))


def test_blank_384_pixel_row_matches_captured_run_length_encoding():
    image = Image.new("1", (384, 1), 1)
    assert encode_bf_frames(image) == [build_bf_frame(b"\x7f\x7f\x7f\x03")]


def test_black_run_matches_captured_dot_row_encoding():
    image = Image.new("1", (384, 1), 1)
    for x in range(4, 7):
        image.putpixel((x, 0), 0)
    assert encode_bf_frames(image) == [
        build_bf_frame(b"\x04\x83\x7f\x7f\x7b")
    ]


def test_bf_encoding_is_deterministic():
    image = Image.new("1", (8, 1), 0)
    assert encode_bf_frames(image) == encode_bf_frames(image)


def test_print_job_uses_the_captured_setup_and_finish_frames():
    image = Image.new("1", (384, 1), 1)
    frames = build_print_frames(image)
    assert [frame.hex() for frame in frames[:5]] == [
        "5178a40001003399ff",
        "5178a60001000000ff",
        "5178af000200b036cdff",
        "5178be000200000107ff",
        "5178bd0001001e5aff",
    ]
    assert frames[5] == build_bf_frame(b"\x7f\x7f\x7f\x03")
    assert [frame.hex() for frame in frames[-3:]] == [
        "5178bd000100146cff",
        "5178a10002006000f5ff",
        "5178a30001000000ff",
    ]


def test_print_job_can_feed_requested_steps_after_each_raster_row():
    image = Image.new("1", (384, 2), 1)
    frames = build_print_frames(image, interline_feed=3)
    assert frames[5:9] == [
        build_bf_frame(b"\x7f\x7f\x7f\x03"),
        bytes.fromhex("5178a100020003003fff"),
        build_bf_frame(b"\x7f\x7f\x7f\x03"),
        bytes.fromhex("5178a100020003003fff"),
    ]


@pytest.mark.parametrize("image", [Image.new("L", (1, 1)), Image.new("1", (0, 1)), Image.new("1", (1, 0))])
def test_bf_rejects_invalid_images(image):
    with pytest.raises(ValueError):
        encode_bf_frames(image)
