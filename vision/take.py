"""Bounded control-only performance recorder, compatible with engine replay."""
import json
from pathlib import Path
import queue
import threading
import time


class TakeRecorder:
    def __init__(self, path):
        self.path = Path(path)
        self.file = self.path.open('x', encoding='utf-8')  # Never overwrite a take.
        self.queue = queue.Queue(maxsize=256)
        self.stop = threading.Event()
        self.error = None
        self.count = 0
        self.start = time.monotonic()
        self.epoch = int(time.time() * 1000)
        self.thread = threading.Thread(target=self._write, daemon=True, name='gesture-take')
        self.thread.start()

    def record(self, event):
        if self.error or self.stop.is_set():
            return False
        elapsed = int((time.monotonic() - self.start) * 1000)
        if elapsed > 3600000 or self.count >= 10000:
            self.error = 'Take limit reached (one hour or 10000 controls); recording stopped.'
            self.stop.set()
            return False
        payload = json.dumps(dict(event, timestamp_ms=self.epoch + elapsed), allow_nan=False) + '\n'
        try:
            self.queue.put_nowait(payload)
        except queue.Full:
            self.error = 'Disk writer fell behind; recording stopped. Saved file contains only the completed prefix.'
            self.stop.set()
            return False
        self.count += 1
        return True

    def _write(self):
        try:
            while not self.stop.is_set() or not self.queue.empty():
                try:
                    self.file.write(self.queue.get(timeout=.05))
                except queue.Empty:
                    continue
        except OSError as exc:
            self.error = str(exc)
            self.stop.set()
        finally:
            try:
                self.file.close()
            except OSError as exc:
                self.error = str(exc)

    def close(self):
        self.stop.set()
        self.thread.join(2)
        if self.thread.is_alive():
            self.error = 'Disk writer did not finish; take may be incomplete.'
