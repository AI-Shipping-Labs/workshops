import json

from pyodide.ffi import create_proxy


class SseStreamRenderer:
    """Writes agent events to a JavaScript stream as soon as they happen."""

    def __init__(self, writer):
        self.writer = writer
        self.closed = False

    async def emit(self, event: str, payload: dict):
        """Writes one typed SSE event to the response stream."""

        if self.closed:
            return

        chunk = f"event: {event}\ndata: {json.dumps(payload)}\n\n".encode()
        try:
            await write_bytes(self.writer, chunk)
        except BaseException:
            self.closed = True

    async def close(self):
        """Closes the streaming response writer."""

        if self.closed:
            return

        self.closed = True
        try:
            await self.writer.close()
        except BaseException:
            pass


async def write_bytes(writer, body: bytes):
    """Writes Python bytes into a JavaScript WritableStream writer."""

    proxy = create_proxy(body)
    buffer = proxy.getBuffer()
    try:
        await writer.write(buffer.data.slice())
    finally:
        buffer.release()
        proxy.destroy()
