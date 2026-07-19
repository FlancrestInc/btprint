import io
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from print_service import PrintServiceError
from webapp import create_app


def valid_text_form(**overrides):
    form = {
        "source_type": "text", "text": "Hello", "font_size": "24",
        "align": "left", "bold": "false", "dither": "false",
        "mac": "20:DC:8B:CD:CA:C0", "interline_feed": "1",
        "vertical_scale": "0.5",
    }
    form.update(overrides)
    return form


class FakePrintService:
    def __init__(self):
        self.busy = False
        self.jobs = {}
        self.started = []

    def start(self, prepared, *, mac, interline_feed):
        if self.busy:
            raise PrintServiceError("A print job is already in progress.")
        self.busy = True
        job_id = f"job-{len(self.started) + 1}"
        self.started.append((prepared, mac, interline_feed))
        self.jobs[job_id] = {"state": "preparing", "error": None}
        return job_id

    def get(self, job_id):
        if job_id not in self.jobs:
            raise KeyError(job_id)
        return self.jobs[job_id]


class WebAppTests(unittest.TestCase):
    def setUp(self):
        self.service = FakePrintService()
        self.tempdir = tempfile.TemporaryDirectory()
        self.app = create_app(print_service=self.service, upload_tempdir=self.tempdir.name)
        self.client = self.app.test_client()

    def tearDown(self):
        self.tempdir.cleanup()

    def test_preview_returns_a_monochrome_png_for_text(self):
        response = self.client.post("/preview", data=valid_text_form())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "image/png")
        image = Image.open(io.BytesIO(response.data))
        self.assertEqual(image.mode, "1")

    def test_print_returns_202_and_passes_prepared_image_to_service(self):
        response = self.client.post("/print", data=valid_text_form(interline_feed="3"))
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.get_json(), {"job_id": "job-1"})
        prepared, mac, feed = self.service.started[0]
        self.assertEqual(prepared.mode, "1")
        self.assertEqual(mac, "20:DC:8B:CD:CA:C0")
        self.assertEqual(feed, 3)

    def test_active_print_returns_exact_409_json_error(self):
        self.service.busy = True
        response = self.client.post("/print", data=valid_text_form())
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json(), {"error": "A print job is already in progress."})

    def test_job_lookup_and_unknown_job_statuses(self):
        self.service.jobs["job-1"] = {"state": "printing", "error": None}
        self.assertEqual(self.client.get("/jobs/job-1").get_json()["state"], "printing")
        self.assertEqual(self.client.get("/jobs/missing").status_code, 404)

    def test_invalid_settings_return_json_400(self):
        invalid_forms = (
            valid_text_form(source_type="other"), valid_text_form(font_size="73"),
            valid_text_form(align="diagonal"), valid_text_form(bold="perhaps"),
            valid_text_form(mac="not-a-mac"), valid_text_form(interline_feed="0"),
            valid_text_form(vertical_scale="2.1"), valid_text_form(vertical_scale="bad"),
            valid_text_form(text="   "),
        )
        for form in invalid_forms:
            with self.subTest(form=form):
                response = self.client.post("/preview", data=form)
                self.assertEqual(response.status_code, 400)
                self.assertIn("error", response.get_json())

    def test_oversize_request_returns_json_400(self):
        response = self.client.post(
            "/preview",
            data={"source_type": "image", "image": (io.BytesIO(b"x" * (10 * 1024 * 1024 + 1)), "large.png")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.get_json())

    def test_image_source_requires_valid_upload(self):
        missing = self.client.post("/preview", data={"source_type": "image"})
        invalid = self.client.post(
            "/preview", data={"source_type": "image", "image": (io.BytesIO(b"not an image"), "bad.png")}
        )
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(invalid.status_code, 400)
        self.assertIn("error", missing.get_json())
        self.assertIn("error", invalid.get_json())

    def test_image_preview_enforces_decoded_limit_and_cleans_temp_file(self):
        image = Image.new("L", (4000, 3001), "white")
        stream = io.BytesIO()
        image.save(stream, "PNG")
        stream.seek(0)
        response = self.client.post(
            "/preview", data={"source_type": "image", "image": (stream, "large.png")}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(list(Path(self.tempdir.name).iterdir()), [])

    def test_image_upload_cleanup_on_success(self):
        stream = io.BytesIO()
        Image.new("L", (10, 10), "white").save(stream, "PNG")
        stream.seek(0)
        response = self.client.post(
            "/preview", data={"source_type": "image", "image": (stream, "small.png")}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(Path(self.tempdir.name).iterdir()), [])

    def test_prepare_failure_is_logged_and_returns_exact_500(self):
        with mock.patch("webapp.prepare_ble_image", side_effect=RuntimeError("bad image")), \
             mock.patch.object(self.app.logger, "exception") as log:
            response = self.client.post("/preview", data=valid_text_form())
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json(), {"error": "Could not prepare this print."})
        log.assert_called_once()

    def test_print_rejects_prepared_height_above_limit(self):
        with mock.patch("webapp.prepare_ble_image", return_value=Image.new("1", (384, 2049), 1)):
            response = self.client.post("/print", data=valid_text_form())
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.get_json())

    def test_concurrent_print_requests_yield_one_202_and_one_409(self):
        class LockedService(FakePrintService):
            def __init__(self):
                super().__init__()
                self.lock = threading.Lock()

            def start(self, prepared, *, mac, interline_feed):
                with self.lock:
                    return super().start(prepared, mac=mac, interline_feed=interline_feed)

        app = create_app(print_service=LockedService(), upload_tempdir=self.tempdir.name)
        barrier, statuses = threading.Barrier(2), []

        def post_print():
            client = app.test_client()
            barrier.wait()
            statuses.append(client.post("/print", data=valid_text_form()).status_code)

        threads = [threading.Thread(target=post_print) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertCountEqual(statuses, [202, 409])


if __name__ == "__main__":
    unittest.main()
