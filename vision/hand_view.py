"""Optional loopback landmark feed. Capture only replaces a bounded mailbox."""
import asyncio
import json
import queue
import re
import threading


class HandView:
    def __init__(self, port=47802):
        self.port = port
        self.mailbox = queue.Queue(maxsize=1)
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.error = None
        self.thread = None

    def publish(self, frame):
        # Serialize in capture to detach the snapshot from mutable landmarks.
        payload = json.dumps(frame, allow_nan=False, separators=(',', ':'))
        try:
            self.mailbox.get_nowait()
        except queue.Empty:
            pass
        try:
            self.mailbox.put_nowait(payload)
        except queue.Full:
            pass

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True, name='vision-hand-view')
        self.thread.start()
        return self

    def _run(self):
        try:
            asyncio.run(self._serve())
        except Exception as exc:
            self.error = str(exc)
            self.ready.set()

    async def _serve(self):
        from websockets.asyncio.server import serve
        latest = None

        async def client(ws):
            last_payload = None
            try:
                while not self.stop.is_set():
                    if latest is not None and latest != last_payload:
                        payload = latest
                        await asyncio.wait_for(ws.send(payload), .1)
                        last_payload = payload
                    await asyncio.sleep(.05)
            except Exception:
                return  # Slow or disconnected display never affects capture.

        origins = [None, re.compile(r'http://(?:localhost|127\.0\.0\.1)(?::[0-9]+)?')]
        async with serve(client, '127.0.0.1', self.port, origins=origins,
                         max_size=4096, max_queue=1, write_limit=4096, close_timeout=.2) as server:
            self.port = server.sockets[0].getsockname()[1]
            self.ready.set()
            while not self.stop.is_set():
                try:
                    latest = self.mailbox.get_nowait()
                except queue.Empty:
                    pass
                await asyncio.sleep(.02)

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(1)
