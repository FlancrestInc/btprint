import threading
import time
import unittest

from PIL import Image

from ctp500_gatttool import GatttoolTransportError
from print_service import PrintService, PrintServiceError


class FakeSession:
    def __init__(self, *, gate=None, error=None):
        self.gate = gate
        self.error = error
        self.frames = []
        self.closed = False

    def send_frames(self, frames):
        self.frames.extend(frames)
        if self.gate is not None:
            self.gate.wait(timeout=1)
        if self.error is not None:
            raise self.error

    def close(self):
        self.closed = True


class PrintServiceTests(unittest.TestCase):
    def prepared(self, *, width=384, height=2, mode="1"):
        return Image.new(mode, (width, height), 1)

    def wait_for_terminal(self, service, job_id):
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            job = service.get(job_id)
            if job["state"] in {"complete", "failed"}:
                return job
            time.sleep(0.01)
        self.fail("job did not reach a terminal state")

    def test_successful_job_sends_frames_and_closes_session(self):
        session = FakeSession()
        service = PrintService(
            session_factory=lambda mac: session,
            frame_builder=lambda image, *, interline_feed: [b"first", b"second"],
        )

        job_id = service.start(self.prepared(), interline_feed=3)

        self.assertIn(service.get(job_id)["state"], {"preparing", "printing", "complete"})
        self.assertEqual(self.wait_for_terminal(service, job_id)["state"], "complete")
        self.assertEqual(session.frames, [b"first", b"second"])
        self.assertTrue(session.closed)

    def test_transport_failure_marks_failed_and_closes_session(self):
        session = FakeSession(error=GatttoolTransportError("write failed"))
        service = PrintService(
            session_factory=lambda mac: session,
            frame_builder=lambda image, *, interline_feed: [b"frame"],
        )

        job = self.wait_for_terminal(service, service.start(self.prepared()))

        self.assertEqual(job, {"state": "failed", "error": "write failed"})
        self.assertTrue(session.closed)

    def test_validation_is_synchronous(self):
        service = PrintService(
            session_factory=lambda mac: FakeSession(),
            frame_builder=lambda image, *, interline_feed: [],
        )
        invalid_images = (
            self.prepared(mode="L"),
            self.prepared(width=383),
            self.prepared(height=0),
            self.prepared(height=2049),
        )
        for image in invalid_images:
            with self.subTest(image=image):
                with self.assertRaises(PrintServiceError):
                    service.start(image)
        for mac in ("20:DC:8B:CD:CA", "20:DC:8B:CD:CA:C0:01", "bad-mac"):
            with self.subTest(mac=mac):
                with self.assertRaises(PrintServiceError):
                    service.start(self.prepared(), mac=mac)
        for feed in (0, 9):
            with self.subTest(feed=feed):
                with self.assertRaises(PrintServiceError):
                    service.start(self.prepared(), interline_feed=feed)

    def test_active_job_is_rejected(self):
        gate = threading.Event()
        service = PrintService(
            session_factory=lambda mac: FakeSession(gate=gate),
            frame_builder=lambda image, *, interline_feed: [b"frame"],
        )
        job_id = service.start(self.prepared())

        with self.assertRaisesRegex(PrintServiceError, "^A print job is already in progress\\.$"):
            service.start(self.prepared())

        gate.set()
        self.wait_for_terminal(service, job_id)

    def test_concurrent_starts_allow_one_job_and_one_busy_error(self):
        gate = threading.Event()
        sessions = []
        service = PrintService(
            session_factory=lambda mac: sessions.append(FakeSession(gate=gate)) or sessions[-1],
            frame_builder=lambda image, *, interline_feed: [b"frame"],
        )
        barrier = threading.Barrier(2)
        job_ids, errors = [], []

        def start_job():
            barrier.wait()
            try:
                job_ids.append(service.start(self.prepared()))
            except PrintServiceError as error:
                errors.append(str(error))

        threads = [threading.Thread(target=start_job) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(len(job_ids), 1)
        self.assertEqual(errors, ["A print job is already in progress."])
        gate.set()
        self.wait_for_terminal(service, job_ids[0])

    def test_get_returns_a_copy_and_unknown_job_raises_key_error(self):
        gate = threading.Event()
        service = PrintService(
            session_factory=lambda mac: FakeSession(gate=gate),
            frame_builder=lambda image, *, interline_feed: [b"frame"],
        )
        job_id = service.start(self.prepared())

        job = service.get(job_id)
        job["state"] = "changed"
        self.assertNotEqual(service.get(job_id)["state"], "changed")
        with self.assertRaises(KeyError):
            service.get("missing")

        gate.set()
        self.wait_for_terminal(service, job_id)

    def test_prunes_oldest_of_twenty_one_completed_jobs(self):
        service = PrintService(
            session_factory=lambda mac: FakeSession(),
            frame_builder=lambda image, *, interline_feed: [],
        )
        job_ids = []
        for _ in range(21):
            job_id = service.start(self.prepared())
            self.wait_for_terminal(service, job_id)
            job_ids.append(job_id)

        with self.assertRaises(KeyError):
            service.get(job_ids[0])
        self.assertEqual(service.get(job_ids[-1])["state"], "complete")


if __name__ == "__main__":
    unittest.main()
