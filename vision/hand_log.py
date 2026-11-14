"""Opt-in, bounded asynchronous wrist metadata log for take-aligned Eyes analysis."""
import json
import math
from pathlib import Path
import queue
import threading

MAX_BYTES = 64 * 1024 * 1024
MAX_LINE = 4096


def hand_record(result, timestamp_ms, strum_hand='Right'):
    if type(timestamp_ms) is not int or timestamp_ms<0 or strum_hand not in ('Left','Right'):
        raise ValueError('invalid hand-log timestamp or strumming-hand label')
    hands=[]
    for points, labels in zip(result.hand_landmarks,result.handedness):
        if not points or not labels: continue
        wrist, label = points[0], labels[0]
        x,y,confidence = float(wrist.x),float(wrist.y),float(label.score)
        if label.category_name not in ('Left','Right') or not all(math.isfinite(v) and 0<=v<=1 for v in (x,y,confidence)):
            continue
        hands.append(dict(handedness=label.category_name,wrist=[x,y],confidence=confidence))
    return dict(timestamp_ms=timestamp_ms,hands=hands,strum_hand=strum_hand)


class HandLog:
    def __init__(self,path):
        self.path=Path(path)
        self.size=self.path.stat().st_size if self.path.exists() else 0
        if self.size>=MAX_BYTES: raise ValueError('hand log reached 64 MiB; choose a new file')
        if self.size:
            with self.path.open('rb') as old:
                old.seek(-1,2)
                if old.read(1)!=b'\n':raise ValueError('existing hand log has an incomplete last line; choose a new file')
        self.file=self.path.open('a',encoding='utf-8')
        self.queue=queue.Queue(maxsize=256)
        self.stop=threading.Event()
        self.error=None
        self.count=0
        self.thread=threading.Thread(target=self._write,name='vision-hand-log',daemon=True)
        self.thread.start()

    def record(self,record):
        if self.error or self.stop.is_set():return False
        try:
            payload=json.dumps(record,allow_nan=False,separators=(',',':'))+'\n'
            size=len(payload.encode('utf-8'))
            if size>MAX_LINE or self.size+size>MAX_BYTES:
                raise ValueError('hand log size limit reached; recording stopped')
            self.queue.put_nowait(payload)
            self.size+=size
            self.count+=1
            return True
        except (ValueError,queue.Full) as exc:
            self.error=str(exc) or 'hand-log writer fell behind; recording stopped'
            self.stop.set()
            return False

    def _write(self):
        try:
            while not self.stop.is_set() or not self.queue.empty():
                try:payload=self.queue.get(timeout=.05)
                except queue.Empty:continue
                self.file.write(payload)
                self.file.flush()  # Coach can read completed frames before capture stops.
        except OSError as exc:
            self.error=str(exc)
            self.stop.set()
        finally:
            try:self.file.close()
            except OSError as exc:self.error=str(exc)

    def close(self):
        self.stop.set()
        self.thread.join(2)
        if self.thread.is_alive():self.error='hand-log writer did not finish; log may be incomplete'
