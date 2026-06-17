import json

from workers import Response


class HttpError(Exception):
    """HTTP-aware exception raised by route handlers and rendered by entry.py."""

    def __init__(self, message: str, status: int = 500):
        super().__init__(message)
        self.status = status


def cors_headers(content_type: str | None = None) -> dict[str, str]:
    """Builds shared response headers for browser and curl callers."""

    headers = {
        "access-control-allow-origin": "*",
        "access-control-allow-methods": "GET,POST,OPTIONS",
        "access-control-allow-headers": "content-type",
    }
    if content_type:
        headers["content-type"] = content_type
    return headers


def json_response(data: object, status: int = 200) -> Response:
    """Serializes a Python object as JSON for API responses."""

    return Response(
        json.dumps(data),
        status=status,
        headers=cors_headers("application/json; charset=utf-8"),
    )


def html_response(html: str) -> Response:
    """Returns the single-page test UI served from `/`."""

    return Response(html, headers=cors_headers("text/html; charset=utf-8"))


def empty_cors_response() -> Response:
    """Returns the CORS preflight response for OPTIONS requests."""

    return Response("", status=204, headers=cors_headers())


def error_response(error: BaseException) -> Response:
    """Converts exceptions raised by handlers into JSON HTTP errors."""

    status = error.status if isinstance(error, HttpError) else 500
    return json_response({"error": str(error) or "Unknown error"}, status)
