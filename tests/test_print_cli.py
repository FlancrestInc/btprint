import builtins
import contextlib
import importlib.util
import io
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image
from ctp500_gatttool import GatttoolTransportError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAC = "20:DC:8B:CD:CA:C0"


def load_cli_module():
    spec = importlib.util.spec_from_file_location("print_cli", PROJECT_ROOT / "print.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def gatttool_module(session, transport_error):
    module = types.ModuleType("ctp500_gatttool")
    module.GatttoolSession = session
    module.GatttoolTransportError = transport_error
    return module


class PrintCliTests(unittest.TestCase):
    def setUp(self):
        sys.modules.pop("print_cli", None)
        sys.modules.pop("ctp500_gatttool", None)
        self.cli = load_cli_module()

    def test_parser_defaults_to_the_printer_address_and_has_no_channel(self):
        args = self.cli.build_parser().parse_args(["photo.png"])

        self.assertEqual(args.image, "photo.png")
        self.assertEqual(args.mac, DEFAULT_MAC)
        self.assertFalse(args.dither)
        self.assertEqual(args.interline_feed, 1)
        self.assertEqual(args.vertical_scale, 0.5)
        self.assertIsNone(args.dry_run)
        with self.assertRaises(SystemExit):
            self.cli.build_parser().parse_args(["photo.png", "--channel", "1"])

    def test_dry_run_saves_384_wide_mode_one_image_without_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.png"
            output = Path(directory) / "prepared.png"
            Image.new("L", (9, 2), 255).save(source)
            original_import = builtins.__import__
            imported = []

            def tracking_import(name, *args, **kwargs):
                imported.append(name)
                return original_import(name, *args, **kwargs)

            with mock.patch("builtins.__import__", side_effect=tracking_import):
                with mock.patch.object(subprocess, "Popen") as popen:
                    self.cli.main([str(source), "--dry-run", str(output)])

            with Image.open(output) as prepared:
                self.assertEqual(prepared.mode, "1")
                self.assertEqual(prepared.size, (384, 44))
            self.assertNotIn("ctp500_gatttool", imported)
            popen.assert_not_called()

    def test_main_forwards_optional_mac_and_sends_all_frames_in_order(self):
        session = mock.Mock(spec=["send_frames", "close"])
        session_type = mock.Mock(return_value=session)
        transport_error = type("GatttoolTransportError", (RuntimeError,), {})
        frames = [b"first", b"second", b"third"]

        with mock.patch.dict(
            sys.modules,
            {"ctp500_gatttool": gatttool_module(session_type, transport_error)},
        ):
            with mock.patch.object(
                self.cli, "prepare_ble_image", return_value=mock.sentinel.prepared
            ) as prepare:
                with mock.patch.object(self.cli, "build_print_frames", return_value=frames) as build:
                    self.cli.main(["source.png", "01:02:03:04:05:06"])

        prepare.assert_called_once_with(
            "source.png", dither=False, vertical_scale=0.5
        )
        build.assert_called_once_with(mock.sentinel.prepared, interline_feed=1)
        session_type.assert_called_once_with("01:02:03:04:05:06")
        self.assertEqual(
            session.mock_calls,
            [mock.call.send_frames(frames), mock.call.close()],
        )

    def test_parser_accepts_an_explicit_interline_feed_amount(self):
        args = self.cli.build_parser().parse_args(["photo.png", "--interline-feed", "3"])
        self.assertEqual(args.interline_feed, 3)

    def test_parser_accepts_vertical_scale(self):
        args = self.cli.build_parser().parse_args(["photo.png", "--vertical-scale", "0.4"])
        self.assertEqual(args.vertical_scale, 0.4)

    def test_main_closes_session_after_success(self):
        session = mock.Mock(spec=["send_frames", "close"])
        session_type = mock.Mock(return_value=session)
        transport_error = type("GatttoolTransportError", (RuntimeError,), {})

        with mock.patch.dict(
            sys.modules,
            {"ctp500_gatttool": gatttool_module(session_type, transport_error)},
        ):
            with mock.patch.object(
                self.cli, "prepare_ble_image", return_value=mock.sentinel.prepared
            ):
                with mock.patch.object(self.cli, "build_print_frames", return_value=[]):
                    self.cli.main(["source.png"])

        self.assertEqual(session.mock_calls, [mock.call.send_frames([]), mock.call.close()])

    def _assert_main_reports_error(self, session_type, transport_error):
        stderr = io.StringIO()
        with mock.patch.dict(
            sys.modules,
            {"ctp500_gatttool": gatttool_module(session_type, transport_error)},
        ):
            with contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as exited:
                    with mock.patch.object(
                        self.cli,
                        "prepare_ble_image",
                        return_value=mock.sentinel.prepared,
                    ):
                        with mock.patch.object(self.cli, "build_print_frames", return_value=[]):
                            self.cli.main(["source.png"])

        self.assertEqual(exited.exception.code, 2)
        return stderr.getvalue()

    def test_main_reports_missing_gatttool_as_a_parser_error(self):
        session_type = mock.Mock(
            side_effect=GatttoolTransportError("gatttool executable was not found")
        )

        stderr = self._assert_main_reports_error(session_type, GatttoolTransportError)

        self.assertIn("gatttool executable was not found", stderr)

    def test_main_reports_gatttool_session_creation_failure_as_a_parser_error(self):
        transport_error = type("GatttoolTransportError", (RuntimeError,), {})
        session_type = mock.Mock(side_effect=transport_error("connect failed"))
        stderr = self._assert_main_reports_error(session_type, transport_error)

        self.assertIn("connect failed", stderr)

    def test_main_reports_gatttool_write_failure_as_a_parser_error(self):
        transport_error = type("GatttoolTransportError", (RuntimeError,), {})
        session = mock.Mock()
        session.send_frames.side_effect = transport_error("write failed")
        stderr = self._assert_main_reports_error(mock.Mock(return_value=session), transport_error)

        self.assertIn("write failed", stderr)
        session.close.assert_called_once_with()

    def test_main_rejects_too_tall_image_before_transport_or_dry_run(self):
        with mock.patch.object(
            self.cli,
            "prepare_ble_image",
            side_effect=ValueError("scaled image height exceeds 65535 rows"),
        ):
            with self.assertRaises(SystemExit) as exited:
                self.cli.main(["too-tall.png", "--dry-run", "out.png"])

        self.assertEqual(exited.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
