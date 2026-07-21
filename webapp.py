"""Local-only Flask endpoints for previewing and printing CTP500 jobs."""

import io
import hmac
import re
import secrets
import tempfile

from flask import Flask, jsonify, render_template, request, send_file, session
from werkzeug.exceptions import Forbidden, RequestEntityTooLarge
from PIL import Image, UnidentifiedImageError

from ctp500_ble import prepare_ble_image
from print_service import DEFAULT_MAC, PrintService, PrintServiceError
from text_renderer import TextRenderError, render_text


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_MULTIPART_OVERHEAD = 1024 * 1024
MAX_DECODED_PIXELS = 12_000_000
MAX_PREPARED_ROWS = 2_048
_MAC_ADDRESS = re.compile(r"[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}")


class RequestError(ValueError):
    """Raised for a request that cannot be previewed or printed."""


def create_app(*, print_service=None, upload_tempdir=None):
    """Create the local web app, optionally using a supplied print service."""
    app = Flask(__name__, template_folder="web/templates", static_folder="web/static")
    app.config["SECRET_KEY"] = secrets.token_bytes(32)
    # Flask measures the whole multipart request. Leave room for form fields and
    # boundaries; _read_uploaded_image enforces the actual file-byte limit.
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES + MAX_MULTIPART_OVERHEAD
    service = print_service if print_service is not None else PrintService()

    @app.get("/")
    def index():
        return render_template("index.html", default_mac=DEFAULT_MAC)

    @app.errorhandler(RequestEntityTooLarge)
    def request_too_large(_error):
        return _error_response("Upload must not exceed 10 MiB.", 400)

    @app.errorhandler(Forbidden)
    def forbidden(_error):
        return _error_response("Forbidden.", 403)

    @app.errorhandler(_PreparationFailure)
    def preparation_failure(_error):
        return _error_response("Could not prepare this print.", 500)

    @app.errorhandler(RequestError)
    @app.errorhandler(TextRenderError)
    def invalid_request(error):
        return _error_response(str(error), 400)

    @app.get("/csrf-token")
    def csrf_token():
        token = session.get("csrf_token")
        if token is None:
            token = secrets.token_urlsafe(32)
            session["csrf_token"] = token
        return jsonify(csrf_token=token)

    @app.post("/preview")
    def preview():
        _validate_csrf_request()
        prepared, settings = _prepared_and_settings(app, upload_tempdir)
        prepared = _display_preview(prepared, settings["vertical_scale"])
        output = io.BytesIO()
        prepared.save(output, format="PNG")
        output.seek(0)
        return send_file(output, mimetype="image/png")

    @app.post("/print")
    def print_job():
        _validate_csrf_request()
        prepared, settings = _prepared_and_settings(app, upload_tempdir)
        try:
            job_id = service.start(
                prepared, mac=settings["mac"], interline_feed=settings["interline_feed"]
            )
        except PrintServiceError as error:
            if str(error) == "A print job is already in progress.":
                return _error_response(str(error), 409)
            app.logger.exception("Could not start print job")
            return _error_response("Could not start print job.", 500)
        return jsonify(job_id=job_id), 202

    @app.get("/jobs/<job_id>")
    def job_status(job_id):
        try:
            return jsonify(service.get(job_id))
        except KeyError:
            return _error_response("Job not found.", 404)

    return app


def _prepared_from_request(app, upload_tempdir):
    return _prepared_and_settings(app, upload_tempdir)[0]


def _display_preview(prepared, vertical_scale):
    """Expand calibrated raster rows to match their physical paper height."""
    height = max(1, round(prepared.height / vertical_scale))
    if height == prepared.height:
        return prepared
    return prepared.resize((prepared.width, height), Image.NEAREST)


def _validate_csrf_request():
    origin = request.headers.get("Origin")
    expected_origin = request.host_url.rstrip("/")
    token = request.headers.get("X-CSRF-Token")
    expected_token = session.get("csrf_token")
    if (
        origin != expected_origin
        or not isinstance(token, str)
        or not isinstance(expected_token, str)
        or not hmac.compare_digest(token, expected_token)
    ):
        return _reject_csrf_request()


def _reject_csrf_request():
    raise Forbidden()


def _prepared_and_settings(app, upload_tempdir):
    source, settings = _parse_request(upload_tempdir)
    try:
        prepared = prepare_ble_image(
            source, dither=settings["dither"], vertical_scale=settings["vertical_scale"]
        )
    except (OSError, ValueError) as error:
        raise RequestError(str(error)) from error
    except Exception:
        app.logger.exception("Could not prepare print image")
        return _raise_preparation_failure()
    if prepared.height > MAX_PREPARED_ROWS:
        raise RequestError("prepared image must not exceed 2,048 rows")
    return prepared, settings


def _raise_preparation_failure():
    raise _PreparationFailure()


class _PreparationFailure(Exception):
    pass


def _parse_request(upload_tempdir):
    source_type = request.form.get("source_type")
    if source_type not in {"image", "text"}:
        raise RequestError("source type must be image or text")
    settings = _parse_settings()
    if source_type == "text":
        try:
            return render_text(
                request.form.get("text"), font_size=_parse_int("font_size", 24, 12, 72),
                align=request.form.get("align", "left"), bold=_parse_bool("bold", False),
            ), settings
        except TextRenderError:
            raise
    return _read_uploaded_image(upload_tempdir), settings


def _parse_settings():
    mac = request.form.get("mac", DEFAULT_MAC)
    if not isinstance(mac, str) or _MAC_ADDRESS.fullmatch(mac) is None:
        raise RequestError("printer MAC address must contain six colon-separated octets")
    return {
        "mac": mac,
        "interline_feed": _parse_int("interline_feed", 1, 1, 8),
        "vertical_scale": _parse_float("vertical_scale", 0.5, 0.25, 2.0),
        "dither": _parse_bool("dither", False),
    }


def _parse_int(name, default, minimum, maximum):
    value = request.form.get(name, str(default))
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise RequestError(f"{name.replace('_', ' ')} must be between {minimum} and {maximum}") from error
    if isinstance(result, bool) or not minimum <= result <= maximum:
        raise RequestError(f"{name.replace('_', ' ')} must be between {minimum} and {maximum}")
    return result


def _parse_float(name, default, minimum, maximum):
    value = request.form.get(name, str(default))
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise RequestError(f"{name.replace('_', ' ')} must be between {minimum} and {maximum}") from error
    if not minimum <= result <= maximum:
        raise RequestError(f"{name.replace('_', ' ')} must be between {minimum} and {maximum}")
    return result


def _parse_bool(name, default):
    value = request.form.get(name, str(default).lower()).lower()
    if value == "true":
        return True
    if value == "false":
        return False
    raise RequestError(f"{name} must be true or false")


def _read_uploaded_image(upload_tempdir):
    upload = request.files.get("image")
    if upload is None or not upload.filename:
        raise RequestError("image upload is required")
    try:
        with tempfile.TemporaryDirectory(dir=upload_tempdir) as directory:
            path = f"{directory}/upload"
            _save_upload_with_limit(upload.stream, path)
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                if image.width * image.height > MAX_DECODED_PIXELS:
                    raise RequestError("image must not exceed 12 megapixels")
                return image.copy()
    except RequestError:
        raise
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as error:
        raise RequestError("image upload must be readable by Pillow") from error


def _save_upload_with_limit(stream, path):
    total = 0
    with open(path, "wb") as destination:
        while chunk := stream.read(64 * 1024):
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                raise RequestError("Upload must not exceed 10 MiB.")
            destination.write(chunk)


def _error_response(message, status):
    return jsonify(error=message), status


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000)
