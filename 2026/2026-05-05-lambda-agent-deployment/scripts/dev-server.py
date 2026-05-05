import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from dotenv import load_dotenv

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from backend.lambda_runtime import NULL_DELIMITER, route


def lambda_event(method: str, path: str, body: bytes) -> dict:
    return {
        "version": "2.0",
        "rawPath": path,
        "body": body.decode(),
        "requestContext": {
            "http": {
                "method": method,
                "path": path,
            },
        },
        "isBase64Encoded": False,
    }


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("access-control-allow-origin", "*")
        self.send_header("access-control-allow-methods", "GET, POST, OPTIONS")
        self.send_header("access-control-allow-headers", "content-type")
        self.send_header("content-length", "0")
        self.end_headers()

    def handle_request(self):
        length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(length) if length else b""
        path = urlsplit(self.path).path
        response_iter = iter(route(lambda_event(self.command, path, body)))

        metadata = json.loads(next(response_iter).decode())
        delimiter = next(response_iter)
        if delimiter != NULL_DELIMITER:
            raise RuntimeError("Unexpected Lambda response delimiter")

        self.send_response(metadata["statusCode"])
        for name, value in metadata.get("headers", {}).items():
            self.send_header(name, value)
        self.send_header("access-control-allow-origin", "*")
        self.send_header("transfer-encoding", "chunked")
        self.end_headers()

        for chunk in response_iter:
            if not chunk:
                continue
            self.wfile.write(f"{len(chunk):x}\r\n".encode())
            self.wfile.write(chunk)
            self.wfile.write(b"\r\n")
            self.wfile.flush()

        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

    def log_message(self, fmt, *args):
        sys.stderr.write(f"{self.address_string()} - {fmt % args}\n")


def main():
    load_dotenv()
    host = os.environ.get("BACKEND_HOST", "127.0.0.1")
    port = int(os.environ.get("BACKEND_PORT", "8000"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Local backend serving Lambda routes at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
