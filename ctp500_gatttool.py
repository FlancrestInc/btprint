"""Persistent direct-GATT transport for the CTP500 printer."""

import os
import pty
import select
import subprocess
import time


GATTTOOL_EXECUTABLE = "gatttool"
ADAPTER = "hci0"
ADDRESS_TYPE = "public"
MTU = 247
WRITE_HANDLE = 0x0006
CONNECTION_TIMEOUT_SECONDS = 15
WRITE_DELAY_SECONDS = 0.03
WRITE_CHUNK_BYTES = 20
HOLD_SECONDS = 6.0
_CLOSE_TIMEOUT_SECONDS = 1


class GatttoolTransportError(RuntimeError):
    """The local gatttool session cannot communicate with the printer."""


class GatttoolSession:
    """A connected interactive gatttool process using its own pseudo-terminal."""

    def __init__(
        self,
        mac,
        *,
        openpty=pty.openpty,
        popen=subprocess.Popen,
        read=os.read,
        write=os.write,
        select_fn=select.select,
        close=os.close,
        sleep=time.sleep,
        monotonic=time.monotonic,
    ):
        self.command = (
            GATTTOOL_EXECUTABLE,
            "-i",
            ADAPTER,
            "-b",
            mac,
            "-t",
            ADDRESS_TYPE,
            "-m",
            str(MTU),
            "-I",
        )
        self._read = read
        self._write = write
        self._select = select_fn
        self._close_fd = close
        self._sleep = sleep
        self._monotonic = monotonic
        self._master_fd = None
        self._slave_fd = None
        self._process = None
        self._output_buffer = b""

        try:
            self._master_fd, self._slave_fd = openpty()
            self._process = popen(
                self.command,
                stdin=self._slave_fd,
                stdout=self._slave_fd,
                stderr=self._slave_fd,
                close_fds=True,
            )
        except FileNotFoundError as error:
            self._close_fds()
            raise GatttoolTransportError("gatttool executable was not found") from error
        except OSError as error:
            self._close_fds()
            raise GatttoolTransportError("could not start gatttool") from error

        self._close_slave()
        try:
            self._write_all(b"connect\n")
            self._wait_for_connection()
        except Exception:
            self.close()
            raise

    def _write_all(self, data):
        view = memoryview(data)
        while view:
            try:
                count = self._write(self._master_fd, view)
            except InterruptedError:
                continue
            except OSError as error:
                raise GatttoolTransportError("gatttool command write failed") from error
            if count <= 0 or count > len(view):
                raise GatttoolTransportError("gatttool command write failed")
            view = view[count:]

    def _wait_for_connection(self):
        start = self._monotonic()
        output = b""
        while True:
            if self._process.poll() is not None:
                raise GatttoolTransportError("gatttool exited before connection succeeded")
            remaining = CONNECTION_TIMEOUT_SECONDS - (self._monotonic() - start)
            if remaining <= 0:
                raise GatttoolTransportError("gatttool connection timed out")
            readable, _, _ = self._select([self._master_fd], [], [], remaining)
            if not readable:
                continue
            try:
                chunk = self._read(self._master_fd, 4096)
            except OSError as error:
                raise GatttoolTransportError("gatttool connection read failed") from error
            if not chunk:
                raise GatttoolTransportError("gatttool connection reached EOF")
            output = (output + chunk)[-8192:]
            text = output.decode("utf-8", errors="replace")
            if "Connection successful" in text:
                return
            lower = text.lower()
            if "connection failed" in lower or "connect error" in lower:
                raise GatttoolTransportError("gatttool connection failed: " + text.strip())

    def send_frames(self, frames):
        sent = False
        for frame in frames:
            if self._process is None or self._process.poll() is not None:
                raise GatttoolTransportError("gatttool exited before frame write")
            for offset in range(0, len(frame), WRITE_CHUNK_BYTES):
                chunk = frame[offset : offset + WRITE_CHUNK_BYTES]
                command = f"char-write-cmd 0x{WRITE_HANDLE:04x} {chunk.hex()}\n".encode()
                self._write_all(command)
                self._drain_output()
            self._sleep(WRITE_DELAY_SECONDS)
            sent = True
        if sent:
            self.hold()

    def hold(self):
        """Keep the connection open briefly after a completed print job."""
        self._sleep(HOLD_SECONDS)

    def _drain_output(self):
        while True:
            readable, _, _ = self._select([self._master_fd], [], [], 0)
            if not readable:
                return
            try:
                output = self._read(self._master_fd, 4096)
            except OSError as error:
                raise GatttoolTransportError("gatttool output read failed") from error
            if not output:
                return
            self._output_buffer = (self._output_buffer + output)[-8192:]
            text = self._output_buffer.decode("utf-8", errors="replace")
            lowered = text.lower()
            if "command failed" in lowered or "error" in lowered:
                raise GatttoolTransportError("gatttool command failed: " + text.strip())

    def _close_slave(self):
        if self._slave_fd is not None:
            try:
                self._close_fd(self._slave_fd)
            except OSError:
                pass
            self._slave_fd = None

    def _close_fds(self):
        self._close_slave()
        if self._master_fd is not None:
            try:
                self._close_fd(self._master_fd)
            except OSError:
                pass
            self._master_fd = None

    def close(self):
        """Stop gatttool and release descriptors. This method is idempotent."""
        process = self._process
        if process is None:
            self._close_fds()
            return
        self._process = None
        try:
            if self._master_fd is not None and process.poll() is None:
                try:
                    self._write_all(b"quit\n")
                except GatttoolTransportError:
                    pass
                try:
                    process.wait(timeout=_CLOSE_TIMEOUT_SECONDS)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try:
                        process.wait(timeout=_CLOSE_TIMEOUT_SECONDS)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=_CLOSE_TIMEOUT_SECONDS)
        except (OSError, subprocess.SubprocessError):
            pass
        finally:
            self._close_fds()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False
