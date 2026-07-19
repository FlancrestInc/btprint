import errno
import subprocess
import unittest
from unittest.mock import MagicMock

import ctp500_gatttool


class GatttoolSessionTests(unittest.TestCase):
    def make_session(self, *, reads=(b"[LE]> connect\r\n", b"Connection successful\r\n[LE]> "),
                     process=None, write=None, select_fn=None, clock=None):
        self.fds = (31, 32)
        self.closed = []
        self.commands = []
        self.sleeps = []
        self.process = process or MagicMock()
        if process is None:
            self.process.poll.return_value = None
        self.popen = MagicMock(return_value=self.process)
        chunks = iter(reads)

        def fake_read(fd, size):
            try:
                return next(chunks)
            except StopIteration:
                return b""

        self.write = write or (lambda fd, data: self.commands.append(bytes(data)) or len(data))
        self.select = select_fn or (lambda readers, writers, errors, timeout: (readers, [], []))
        self.clock_values = iter(clock or (0.0, 0.0, 0.0, 0.0))
        session = ctp500_gatttool.GatttoolSession(
            "20:DC:8B:CD:CA:C0",
            openpty=lambda: self.fds,
            popen=self.popen,
            read=fake_read,
            write=self.write,
            select_fn=self.select,
            close=lambda fd: self.closed.append(fd),
            sleep=self.sleeps.append,
            monotonic=lambda: next(self.clock_values),
        )
        return session

    def test_launches_interactive_gatttool_and_connects_with_lf(self):
        session = self.make_session()
        self.assertEqual(
            session.command,
            ("gatttool", "-i", "hci0", "-b", "20:DC:8B:CD:CA:C0", "-t", "public", "-m", "247", "-I"),
        )
        self.assertEqual(self.commands, [b"connect\n"])
        self.popen.assert_called_once_with(
            session.command, stdin=32, stdout=32, stderr=32, close_fds=True
        )
        self.assertEqual(self.closed, [32])

    def test_connection_failure_text_raises_transport_error(self):
        with self.assertRaisesRegex(ctp500_gatttool.GatttoolTransportError, "connection failed"):
            self.make_session(reads=(b"Error: connect error: Connection refused\r\n",))

    def test_eof_and_early_exit_raise_transport_error(self):
        with self.assertRaisesRegex(ctp500_gatttool.GatttoolTransportError, "EOF"):
            self.make_session(reads=(b"",))
        process = MagicMock()
        process.poll.return_value = 1
        with self.assertRaisesRegex(ctp500_gatttool.GatttoolTransportError, "exited"):
            self.make_session(process=process, reads=())

    def test_connect_timeout_raises_transport_error(self):
        with self.assertRaisesRegex(ctp500_gatttool.GatttoolTransportError, "timed out"):
            self.make_session(
                reads=(),
                select_fn=lambda readers, writers, errors, timeout: ([], [], []),
                clock=(0.0, 16.0),
            )

    def test_missing_gatttool_becomes_transport_error_and_closes_fds(self):
        closed = []
        with self.assertRaisesRegex(ctp500_gatttool.GatttoolTransportError, "gatttool"):
            ctp500_gatttool.GatttoolSession(
                "AA:BB:CC:DD:EE:FF",
                openpty=lambda: (7, 8),
                popen=MagicMock(side_effect=FileNotFoundError()),
                close=closed.append,
            )
        self.assertEqual(closed, [8, 7])

    def test_sends_frames_in_order_and_paces_each_one(self):
        session = self.make_session()
        self.commands.clear()
        frames = (b"\x51\x78", b"\x00\xff")
        session.send_frames(frames)
        self.assertEqual(
            self.commands,
            [b"char-write-cmd 0x0006 5178\n", b"char-write-cmd 0x0006 00ff\n"],
        )
        self.assertEqual(self.sleeps, [0.03, 0.03, 6.0])

    def test_splits_large_frame_into_small_ble_writes_without_extra_pacing(self):
        session = self.make_session()
        self.commands.clear()
        session.send_frames((bytes(range(25)),))
        self.assertEqual(
            self.commands,
            [
                b"char-write-cmd 0x0006 " + bytes(range(20)).hex().encode() + b"\n",
                b"char-write-cmd 0x0006 " + bytes(range(20, 25)).hex().encode() + b"\n",
            ],
        )
        self.assertEqual(self.sleeps, [0.03, 6.0])

    def test_hold_sleeps_for_the_proven_post_job_connection_window(self):
        session = self.make_session()
        session.hold()
        self.assertEqual(self.sleeps, [6.0])

    def test_short_and_interrupted_writes_are_retried_until_complete(self):
        writes = []
        outcomes = iter((InterruptedError(), 2, 1, 999))

        def write(fd, data):
            writes.append(bytes(data))
            result = next(outcomes)
            if isinstance(result, BaseException):
                raise result
            return min(result, len(data))

        session = self.make_session()
        session._write = write
        writes.clear()
        session.send_frames((b"\xaa",))
        command = b"char-write-cmd 0x0006 aa\n"
        self.assertEqual(writes, [command, command, command[2:], command[3:]])

    def test_zero_or_broken_write_is_transport_error(self):
        session = self.make_session()
        session._write = lambda fd, data: 0
        with self.assertRaisesRegex(ctp500_gatttool.GatttoolTransportError, "write"):
            session.send_frames((b"\x01",))
        session = self.make_session()
        session._write = MagicMock(side_effect=OSError(errno.EIO, "broken"))
        with self.assertRaises(ctp500_gatttool.GatttoolTransportError):
            session.send_frames((b"\x01",))

    def test_send_frames_rejects_a_child_that_has_already_exited(self):
        session = self.make_session()
        session._process.poll.return_value = 1
        with self.assertRaisesRegex(ctp500_gatttool.GatttoolTransportError, "exited"):
            session.send_frames((b"\x01",))
        self.assertEqual(self.commands, [b"connect\n"])

    def test_write_counts_larger_than_the_remaining_command_are_transport_errors(self):
        session = self.make_session()
        session._write = lambda fd, data: len(data) + 1
        with self.assertRaisesRegex(ctp500_gatttool.GatttoolTransportError, "write"):
            session.send_frames((b"\x01",))

    def test_drains_available_echo_after_each_frame(self):
        session = self.make_session(clock=(0.0,) * 8)
        select_calls = []
        drain_reads = iter((b"echo\n", b""))
        def select_fn(readers, writers, errors, timeout):
            select_calls.append(timeout)
            return ([31], [], [])
        session._select = select_fn
        session._read = lambda fd, size: next(drain_reads)
        session.send_frames((b"\x01",))
        self.assertEqual(select_calls, [0, 0])

    def test_command_failed_output_raises_transport_error(self):
        reads = iter((b"[LE]> connect\n", b"Connection successful\n[LE]> ", b"Error: Command Failed\n"))

        def select_fn(readers, writers, errors, timeout):
            return ([31], [], [])

        session = self.make_session(reads=reads, select_fn=select_fn)
        session._select = select_fn
        with self.assertRaisesRegex(ctp500_gatttool.GatttoolTransportError, "Command Failed"):
            session.send_frames((b"\x01",))

    def test_command_failed_marker_split_across_reads_is_detected(self):
        session = self.make_session()
        split_reads = iter((b"Command ", b"Failed\n", b""))
        session._select = lambda readers, writers, errors, timeout: ([31], [], [])
        session._read = lambda fd, size: next(split_reads)
        with self.assertRaisesRegex(ctp500_gatttool.GatttoolTransportError, "Command Failed"):
            session.send_frames((b"\x01",))

    def test_close_handles_failed_quit_and_wait_timeouts_then_kills(self):
        process = MagicMock()
        process.poll.return_value = None
        process.wait.side_effect = (subprocess.TimeoutExpired("gatttool", 1), subprocess.TimeoutExpired("gatttool", 1), None)
        session = self.make_session(process=process)
        session._write = MagicMock(side_effect=OSError(errno.EIO, "broken"))
        session.close()
        process.terminate.assert_called_once_with()
        process.kill.assert_called_once_with()
        self.assertEqual(session._master_fd, None)
        self.assertEqual(session._slave_fd, None)
        self.assertEqual(self.closed, [32, 31])
        session.close()
        process.terminate.assert_called_once_with()

    def test_close_preserves_operation_error_when_cleanup_fails(self):
        session = self.make_session()
        session._write = lambda fd, data: 0
        with self.assertRaisesRegex(ctp500_gatttool.GatttoolTransportError, "write"):
            try:
                session.send_frames((b"\x01",))
            finally:
                session.close()
        self.assertEqual(self.closed, [32, 31])


if __name__ == "__main__":
    unittest.main()
