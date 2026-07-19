"""Print CTP500-compatible images over Bluetooth Low Energy."""

import argparse

from ctp500_bf import build_print_frames
from ctp500_ble import prepare_ble_image


DEFAULT_MAC = "20:DC:8B:CD:CA:C0"


def interline_feed_steps(value):
    steps = int(value)
    if not 1 <= steps <= 0xFF:
        raise argparse.ArgumentTypeError("interline feed must be 1 through 255")
    return steps


def vertical_scale(value):
    scale = float(value)
    if scale <= 0:
        raise argparse.ArgumentTypeError("vertical scale must be positive")
    return scale


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Print an image to a CTP500-compatible BLE printer."
    )
    parser.add_argument("image", help="source image readable by Pillow")
    parser.add_argument("mac", nargs="?", default=DEFAULT_MAC, help="printer MAC address")
    parser.add_argument(
        "--dither", action="store_true", help="use Floyd-Steinberg dithering"
    )
    parser.add_argument(
        "--dry-run", metavar="OUTPUT", help="save the prepared 1-bit image"
    )
    parser.add_argument(
        "--replay-pklg", metavar="CAPTURE",
        help="replay printer write frames from a PacketLogger .pklg capture",
    )
    parser.add_argument(
        "--interline-feed", nargs="?", const=1, default=1,
        type=interline_feed_steps, metavar="STEPS",
        help="feed STEPS (default 1) after each image row",
    )
    parser.add_argument(
        "--vertical-scale", default=0.5, type=vertical_scale, metavar="FACTOR",
        help="resize image height by FACTOR (default 0.5)",
    )
    return parser


def main(argv=None) -> None:
    parser = build_parser()
    # Allow the optional capture flag between the two positional arguments.
    parse = getattr(parser, "parse_intermixed_args", parser.parse_args)
    args = parse(argv)

    try:
        prepared = prepare_ble_image(
            args.image, dither=args.dither, vertical_scale=args.vertical_scale
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))

    if args.dry_run:
        try:
            prepared.save(args.dry_run)
        except OSError as error:
            parser.error(str(error))
        return

    try:
        from ctp500_gatttool import GatttoolSession, GatttoolTransportError
        if args.replay_pklg:
            from ctp500_pklg import extract_write_frames
    except (FileNotFoundError, OSError, ValueError) as error:
        parser.error(str(error))

    try:
        session = GatttoolSession(args.mac)
        try:
            frames = (extract_write_frames(args.replay_pklg)
                      if args.replay_pklg else build_print_frames(
                          prepared, interline_feed=args.interline_feed
                      ))
            session.send_frames(frames)
        finally:
            session.close()
    except (GatttoolTransportError, FileNotFoundError, OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
