"""Single-job background printing for the local web application."""

import logging
import re
import threading
import uuid
from collections import deque

from ctp500_bf import build_print_frames
from ctp500_gatttool import GatttoolSession, GatttoolTransportError


DEFAULT_MAC = "20:DC:8B:CD:CA:C0"
_MAC_ADDRESS = re.compile(r"[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}")
_BUSY_ERROR = "A print job is already in progress."
_UNEXPECTED_ERROR = "Printing failed; see the server log."
_LOGGER = logging.getLogger(__name__)


class PrintServiceError(RuntimeError):
    """The requested print job is invalid or cannot be started."""


class PrintService:
    def __init__(self, *, session_factory=GatttoolSession, frame_builder=build_print_frames):
        self._session_factory = session_factory
        self._frame_builder = frame_builder
        self._lock = threading.Lock()
        self._jobs = {}
        self._completed_job_ids = deque()
        self._active_job_id = None

    def start(self, prepared_image, *, mac=DEFAULT_MAC, interline_feed=1) -> str:
        """Create a job and return its ID, or raise before any background work."""
        self._validate(prepared_image, mac, interline_feed)
        with self._lock:
            if self._active_job_id is not None:
                raise PrintServiceError(_BUSY_ERROR)
            job_id = uuid.uuid4().hex
            self._jobs[job_id] = {"state": "preparing", "error": None}
            self._active_job_id = job_id
            threading.Thread(
                target=self._run_job,
                args=(job_id, prepared_image, mac, interline_feed),
                daemon=True,
            ).start()
        return job_id

    def get(self, job_id) -> dict:
        """Return a copy of a job record or raise KeyError."""
        with self._lock:
            return self._jobs[job_id].copy()

    def _run_job(self, job_id, image, mac, interline_feed):
        session = None
        error_message = None
        try:
            with self._lock:
                self._jobs[job_id]["state"] = "printing"
            frames = self._frame_builder(image, interline_feed=interline_feed)
            session = self._session_factory(mac)
            session.send_frames(frames)
        except GatttoolTransportError as error:
            error_message = str(error)
        except Exception:
            _LOGGER.exception("Unexpected print job failure")
            error_message = _UNEXPECTED_ERROR
        finally:
            if session is not None:
                try:
                    session.close()
                except GatttoolTransportError as error:
                    if error_message is None:
                        error_message = str(error)
                except Exception:
                    _LOGGER.exception("Unexpected print session cleanup failure")
                    if error_message is None:
                        error_message = _UNEXPECTED_ERROR
            with self._lock:
                job = self._jobs[job_id]
                if error_message is None:
                    job["state"] = "complete"
                else:
                    job["state"] = "failed"
                    job["error"] = error_message
                self._active_job_id = None
                self._completed_job_ids.append(job_id)
                while len(self._completed_job_ids) > 20:
                    self._jobs.pop(self._completed_job_ids.popleft(), None)

    @staticmethod
    def _validate(image, mac, interline_feed):
        if getattr(image, "mode", None) != "1":
            raise PrintServiceError("prepared image must use mode '1'")
        width, height = getattr(image, "size", (None, None))
        if width != 384:
            raise PrintServiceError("prepared image must be 384 pixels wide")
        if not isinstance(height, int) or not 0 < height <= 2048:
            raise PrintServiceError("prepared image height must be between 1 and 2048")
        if not isinstance(mac, str) or _MAC_ADDRESS.fullmatch(mac) is None:
            raise PrintServiceError("printer MAC address must contain six colon-separated octets")
        if isinstance(interline_feed, bool) or not isinstance(interline_feed, int) or not 1 <= interline_feed <= 8:
            raise PrintServiceError("interline feed must be between 1 and 8")
