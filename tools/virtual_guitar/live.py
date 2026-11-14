"""Audible, output-only demo using the production audio and control runtime.

Synthesis, HTTP, JSON, and routing stay outside the audio callback. The callback
copies a precomputed source into reusable buffers and calls the real DSP.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import Future, TimeoutError
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import queue
import threading
import time
from urllib.parse import urlsplit

import numpy as np

from audio import Engine, EngineConfig
from engine.router import decode
from engine.runtime import Runtime

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


class LiveSource:
    """Audio-thread-owned cursor, with atomic control-side transport targets."""

    def __init__(self, mono, samplerate, blocksize, volume=0.35):
        mono = np.asarray(mono, dtype=np.float32)
        if mono.ndim != 1 or not len(mono) or not np.all(np.isfinite(mono)):
            raise ValueError('live input must contain finite mono samples')
        self.samples = mono.copy()
        # Short fades prevent a discontinuity when repeating an arbitrary WAV.
        fade = min(len(mono) // 2, max(1, int(samplerate * 0.005)))
        self.samples[:fade] *= np.linspace(0, 1, fade)
        self.samples[-fade:] *= np.linspace(1, 0, fade)
        self.samplerate, self.position = samplerate, 0
        self.playing, self.volume = True, volume
        self._source_gain = self._output_gain = 0.0
        self._step = 1 / max(1, int(samplerate * 0.02))
        self._index = np.arange(1, blocksize + 1, dtype=np.float32)
        self._ramp = np.zeros(blocksize, np.float32)
        self._mono = np.zeros(blocksize, np.float32)

    def _gain(self, current, target, frames):
        ramp = self._ramp[:frames]
        step = self._step if target > current else -self._step
        np.multiply(self._index[:frames], step, out=ramp)
        ramp += current
        np.clip(ramp, min(current, target), max(current, target), out=ramp)
        return ramp

    def process(self, audio, out):
        """Fixed-size output callback path; no synthesis, transport I/O or locks."""
        frames = len(out)
        if frames > len(self._mono):
            out.fill(0)
            audio.note_xrun()
            return
        mono = self._mono[:frames]
        playing = self.playing
        if playing or self._source_gain > 0:
            written = 0
            while written < frames:
                count = min(frames - written, len(self.samples) - self.position)
                mono[written:written + count] = self.samples[self.position:self.position + count]
                self.position = (self.position + count) % len(self.samples)
                written += count
            ramp = self._gain(self._source_gain, float(playing), frames)
            mono *= ramp
            self._source_gain = float(ramp[-1])
        else:
            mono.fill(0)
        audio.process(mono, out)
        ramp = self._gain(self._output_gain, self.volume, frames)
        out *= ramp[:, None]
        self._output_gain = float(ramp[-1])


class Demo:
    """Control-side coordinator. The HTTP thread submits bounded requests here."""

    def __init__(self, source, audio, runtime, *, label, headless=False, camera=None, hand_port=47802):
        self.source, self.audio, self.runtime = source, audio, runtime
        self.label, self.headless = label, headless
        self.camera, self.hand_port = camera, hand_port
        self.commands = queue.Queue(maxsize=32)
        self.published = {}
        self.seq = int(time.time() * 1000)
        self.publish()

    def control(self, control, value=None):
        self.seq = max(self.seq + 1, self.runtime.router.clock())
        event = dict(version=1, source='manual', seq=self.seq,
                     timestamp_ms=self.runtime.router.clock(),
                     type='action' if value is None else 'parameter', control=control)
        if value is not None:
            event.update(value=value, confidence=1.0)
        if not self.runtime.router.ingest(json.dumps(event)):
            raise ValueError('control rejected by engine')

    def apply(self, command):
        if not isinstance(command, dict):
            raise ValueError('expected a command object')
        action = command.get('action')
        value = command.get('value')
        if action == 'camera_start' and self.camera is not None:
            self.camera.start()
        elif action == 'camera_stop' and self.camera is not None:
            self.camera.stop()
        elif action == 'playing' and type(value) is bool:
            self.source.playing = value
        elif action == 'volume' and type(value) in (int, float) and 0 <= value <= 1:
            self.source.volume = float(value)
        elif action in ('filter', 'reverb') and type(value) in (int, float) and 0 <= value <= 1:
            self.control(action, value)
        elif action in ('loop', 'bypass'):
            self.control(action)
        elif action == 'preset' and value in ('dry', 'dark', 'space'):
            if self.audio.snapshot()['bypass']:
                self.control('bypass')
            f, r = {'dry': (1.0, 0.0), 'dark': (0.25, 0.15), 'space': (0.8, 0.75)}[value]
            self.control('filter', f)
            self.control('reverb', r)
        else:
            raise ValueError('unknown action or invalid value')

    def drain(self):
        for _ in range(32):
            try:
                command, result = self.commands.get_nowait()
            except queue.Empty:
                break
            if not result.set_running_or_notify_cancel():
                continue
            try:
                self.apply(command)
                result.set_result(True)
            except (ValueError, TypeError) as exc:
                result.set_exception(ValueError(str(exc)))
        self.publish()

    def publish(self):
        self.published = dict(label=self.label, headless=self.headless,
                              playing=self.source.playing, volume=self.source.volume,
                              position=self.source.position / self.source.samplerate,
                              seconds=len(self.source.samples) / self.source.samplerate,
                              ws_port=self.runtime.ws_port,
                              hand_port=self.hand_port,
                              camera=self.camera.snapshot() if self.camera is not None else None,
                              engine=self.runtime.snapshot())


def make_server(demo, port):
    """Serve only the demo assets and dashboard; never expose the repository."""
    assets = {
        '/': (HERE / 'web/index.html', 'text/html'),
        '/app.js': (HERE / 'web/app.js', 'text/javascript'),
        '/style.css': (HERE / 'web/style.css', 'text/css'),
        '/dashboard/': (ROOT / 'dashboard/index.html', 'text/html'),
        '/dashboard/app.js': (ROOT / 'dashboard/app.js', 'text/javascript'),
        '/dashboard/style.css': (ROOT / 'dashboard/style.css', 'text/css'),
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, body, content_type='application/json'):
            if not isinstance(body, bytes):
                body = json.dumps(body, allow_nan=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type + '; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == '/api/state':
                self.reply(200, demo.published)
            elif path in assets:
                file, mime = assets[path]
                self.reply(200, file.read_bytes(), mime)
            elif path.startswith('/dashboard/'):
                # Pick up new dashboard assets (e.g. Claude's juice.js/css)
                # without maintaining a second copy or serving workspace files.
                folder = (ROOT / 'dashboard').resolve()
                file = (folder / path.removeprefix('/dashboard/')).resolve()
                if file.is_relative_to(folder) and file.is_file() and file.suffix in ('.html', '.js', '.css', '.svg', '.png', '.woff2'):
                    self.reply(200, file.read_bytes(), mimetypes.guess_type(file.name)[0] or 'application/octet-stream')
                else:
                    self.reply(404, {'error': 'not found'})
            else:
                self.reply(404, {'error': 'not found'})

        def do_POST(self):
            # JSON plus exact origin/Host checks prevent cross-site commands.
            host = self.headers.get('Host')
            allowed = (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')
            if host not in allowed or self.headers.get('Origin') not in (None, f'http://{host}'):
                self.reply(403, {'error': 'local same-origin requests only'})
                return
            if self.path not in ('/api/command', '/api/frame'):
                self.reply(404, {'error': 'not found'})
                return
            if self.path == '/api/frame':
                if self.headers.get('Content-Type') != 'image/jpeg':
                    self.reply(415, {'error': 'image/jpeg required'})
                    return
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 250_000:
                        raise ValueError('frame must be 1..250000 bytes')
                    self.connection.settimeout(2)
                    demo.camera.submit(self.rfile.read(size))
                    self.reply(202, {'ok': True})
                except (ValueError, TypeError) as exc:
                    self.reply(400, {'error': str(exc)})
                return
            if self.headers.get('Content-Type') != 'application/json':
                self.reply(415, {'error': 'application/json required'})
                return
            result = Future()
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 4096:
                    raise ValueError('command must be 1..4096 bytes')
                self.connection.settimeout(2)
                command = decode(self.rfile.read(size))
                demo.commands.put_nowait((command, result))
                result.result(timeout=2)
                self.reply(200, {'ok': True})
            except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
                self.reply(400, {'error': str(exc)})
            except (queue.Full, TimeoutError):
                result.cancel()
                self.reply(503, {'error': 'demo busy; try again'})

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


async def run_live(args, mono, samplerate, label):
    audio = Engine(EngineConfig(samplerate=samplerate, input_gain_db=args.gain_db))
    audio.set_filter(args.filter)
    audio.set_reverb(args.reverb)
    source = LiveSource(mono, samplerate, args.blocksize, args.volume)
    runtime = Runtime(audio, udp_port=args.udp_port, ws_port=args.ws_port)
    from .browser_vision import BrowserVision
    camera = BrowserVision(Path(args.model), udp_port=args.udp_port,
                           hand_port=args.hand_port, scene=args.scene)
    demo = Demo(source, audio, runtime, label=label, headless=args.headless,
                camera=camera, hand_port=args.hand_port)
    http = make_server(demo, args.http_port)
    http_thread = None
    try:
        await runtime.start()
        # Never present a healthy page that is actually talking to an old engine.
        deadline = time.monotonic() + 3
        while any(runtime.adapters[key]['status'] != 'running' for key in ('udp', 'websocket')):
            errors = [v['last_error'] for v in runtime.adapters.values() if v['last_error']]
            if errors or time.monotonic() >= deadline:
                raise RuntimeError('Demo ports unavailable. Stop the other engine/simulator, or use '
                                   '--http-port 8081 --ws-port 47811 --udp-port 47810. ' + '; '.join(errors))
            await asyncio.sleep(0.02)

        with ExitStack() as stack:
            stream = None
            if not args.headless:
                from audio.stream import resolve_device, sd

                def callback(out, frames, clock, status):
                    if status.output_underflow:
                        audio.note_xrun()
                    source.process(audio, out)

                device = resolve_device(args.out_dev, args.hostapi, 'output')
                stream = stack.enter_context(sd.OutputStream(
                    device=device, samplerate=samplerate, blocksize=args.blocksize,
                    channels=2, dtype='float32', latency='high', callback=callback))
            demo.publish()
            http_thread = threading.Thread(target=http.serve_forever, daemon=True, name='virtual-guitar-http')
            http_thread.start()
            url = f'http://127.0.0.1:{http.server_port}/'
            print(f'VIRTUAL GUITAR — {label}', flush=True)
            print(f'Demo: {url} | UDP: {runtime.udp_port} | WS: {runtime.ws_port}', flush=True)
            print('HEADLESS: no audible output.' if args.headless else 'Laptop audio is live. Start at low speaker volume.', flush=True)
            print('Pause guitar to hear the recorded loop alone. Ctrl-C stops the demo.', flush=True)
            if args.open:
                import webbrowser
                webbrowser.open(url)
            started = next_block = time.monotonic()
            out = np.zeros((args.blocksize, 2), np.float32)
            while not args.duration or time.monotonic() - started < args.duration:
                if stream is not None and not stream.active:
                    raise RuntimeError('Audio output stopped; restart the demo after checking the output device.')
                demo.drain()
                if args.headless:
                    source.process(audio, out)
                    next_block += args.blocksize / samplerate
                    if next_block < time.monotonic() - 0.25:
                        next_block = time.monotonic()
                    await asyncio.sleep(max(0, next_block - time.monotonic()))
                else:
                    await asyncio.sleep(0.02)
    finally:
        await asyncio.to_thread(camera.close)
        await runtime.close()
        if http_thread is not None:
            await asyncio.to_thread(http.shutdown)
            http_thread.join(timeout=2)
        http.server_close()
    return 0
