"""Independent UDP, serial and WebSocket lifecycles, outside audio processing."""
from __future__ import annotations
import asyncio
import json
import logging
import re
from .router import Router, MAX_MESSAGE, decode


LOG = logging.getLogger('omniriff.adapters')


class Datagram(asyncio.DatagramProtocol):
    def __init__(self, runtime): self.runtime = runtime
    def datagram_received(self, data, addr): self.runtime.router.ingest(data)
    def error_received(self, exc): self.runtime.error('udp', exc)


def read_serial_chunk(port):
    """Wait for the first byte, or drain an already queued bounded batch.

    pySerial read(N) waits for N bytes or timeout. Reading 256 unconditionally
    delays short footswitch lines until timeout. Keep both the availability
    query and the read on the worker thread; idle reads still have a timeout.
    """
    return port.read(max(1, min(256, port.in_waiting)))


class SerialDecoder:
    """Bounded NDJSON framing, host timestamping, reset/reconnect sessions."""
    def __init__(self, router):
        self.router = router
        self.buffer = bytearray()
        self.discard = False
        self.previous = None

    def connect(self):
        self.buffer.clear()
        self.discard = False
        self.previous = None
        self.router.reset('arduino')

    def feed(self, data):
        for value in data:
            if value != 10:
                if not self.discard:
                    self.buffer.append(value)
                    if len(self.buffer) > MAX_MESSAGE:
                        self.buffer.clear(); self.discard = True
                continue
            if self.discard:
                self.router.reject('invalid', 'arduino')
            elif self.buffer:
                self.line(bytes(self.buffer))
            self.buffer.clear(); self.discard = False

    def line(self, raw):
        try:
            event = decode(raw)
            if not isinstance(event, dict) or set(event) != {'seq', 'type', 'control'}:
                raise ValueError('invalid compact line')
            if type(event['seq']) is not int or event['seq'] < 0 or event['type'] != 'action' or event['control'] not in ('loop', 'bypass'):
                raise ValueError('invalid action')
        except (ValueError, TypeError, UnicodeError, RecursionError):
            self.router.reject('invalid', 'arduino'); return
        seq = event['seq']
        # Serial is ordered and non-replayed. A zero after progress is the
        # firmware reset marker; a repeated zero is still a duplicate.
        if seq == 0 and self.previous is not None and self.previous > 0:
            self.router.reset('arduino')
        full = dict(event, version=1, source='arduino', timestamp_ms=self.router.clock())
        if self.router.ingest(json.dumps(full)):
            self.previous = seq


class Runtime:
    def __init__(self, audio, *, udp_port=47800, ws_port=47801, serial_port=None, hz=20, stale_ms=250, replay=None):
        if not 0 < hz <= 60: raise ValueError('state rate must be in (0, 60]')
        self.audio = audio
        self.replay = replay
        self.router = Router(audio, stale_ms=stale_ms)
        if replay is not None and serial_port:
            raise ValueError('replay cannot be combined with serial input')
        self.udp_port, self.ws_port = None if replay is not None else udp_port, ws_port
        self.serial_port, self.hz = serial_port, hz
        self.adapters = {key: dict(status='disabled', errors=0, last_error=None) for key in ('udp', 'serial', 'websocket')}
        self.reported_errors = {}
        self.tasks = {}
        self.udp = None
        self.server = None
        self.serial = None

    def error(self, name, exc):
        item = self.adapters[name]
        item['status'] = 'error'; item['errors'] += 1
        item['last_error'] = f'{type(exc).__name__}: {exc}'[:240]
        if self.reported_errors.get(name) != item['last_error']:
            LOG.warning('%s adapter failed (audio remains independent): %s', name, item['last_error'])
            self.reported_errors[name] = item['last_error']

    def running(self, name):
        self.adapters[name]['status'] = 'running'
        self.reported_errors.pop(name, None)

    def snapshot(self):
        state = dict(self.audio.snapshot(), version=1, timestamp_ms=self.router.clock(),
                    controls=dict(self.router.counts),
                    sources={k: dict(v) for k, v in self.router.sources.items()},
                    adapters={k: dict(v) for k, v in self.adapters.items()})
        if self.replay is not None:
            state['replay'] = dict(self.replay.state)
        return state

    async def supervise(self, name, factory):
        try:
            while True:
                self.adapters[name]['status'] = 'starting'
                try:
                    await factory()
                except asyncio.CancelledError: raise
                except Exception as exc:
                    self.error(name, exc)
                else:
                    self.error(name, RuntimeError('adapter exited'))
                self.adapters[name]['status'] = 'retrying'
                await asyncio.sleep(1)
        finally:
            self.adapters[name]['status'] = 'stopped'

    async def start(self):
        if self.replay is not None:
            self.tasks['replay'] = asyncio.create_task(self.replay.run(self.router), name='omniriff-replay')
        for name, enabled, factory in [('udp', self.udp_port is not None, self.run_udp),
                                       ('websocket', self.ws_port is not None, self.run_ws),
                                       ('serial', bool(self.serial_port), self.run_serial)]:
            if enabled: self.tasks[name] = asyncio.create_task(self.supervise(name, factory), name=f'omniriff-{name}')

    async def close(self):
        for task in self.tasks.values(): task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        self.tasks.clear()

    async def run_udp(self):
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(lambda: Datagram(self), local_addr=('127.0.0.1', self.udp_port))
        self.udp = transport
        self.udp_port = transport.get_extra_info('sockname')[1]
        self.running('udp')
        try: await asyncio.Future()
        finally: transport.close(); self.udp = None

    async def run_ws(self):
        from websockets.asyncio.server import serve
        # Loopback-only server, accept local served dashboards and CLI clients.
        origins = [None, re.compile(r'https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?')]
        async with serve(self.ws_client, '127.0.0.1', self.ws_port, origins=origins,
                         max_size=MAX_MESSAGE, max_queue=8, close_timeout=1, compression=None) as server:
            self.server = server
            self.ws_port = server.sockets[0].getsockname()[1]
            self.running('websocket')
            try: await asyncio.Future()
            finally: self.server = None

    async def ws_client(self, websocket):
        async def publish():
            while True:
                await asyncio.wait_for(websocket.send(json.dumps(self.snapshot(), allow_nan=False)), 0.5)
                await asyncio.sleep(1 / self.hz)
        sender = asyncio.create_task(publish())
        receiver = asyncio.create_task(self.receive_ws(websocket))
        try:
            await asyncio.wait((sender, receiver), return_when=asyncio.FIRST_COMPLETED)
        finally:
            sender.cancel(); receiver.cancel()
            await asyncio.gather(sender, receiver, return_exceptions=True)
            await websocket.close()

    async def receive_ws(self, websocket):
        async for raw in websocket:
            self.router.ingest(raw, expected_source='dashboard')

    async def run_serial(self):
        import serial
        decoder = SerialDecoder(self.router)
        port = await asyncio.to_thread(serial.Serial, self.serial_port, 115200, timeout=0.1)
        self.serial = port
        decoder.connect()
        self.running('serial')
        try:
            while True:
                data = await asyncio.to_thread(read_serial_chunk, port)
                if data: decoder.feed(data)
        finally:
            # read has a bounded timeout; closing unblocks on device removal.
            port.close(); self.serial = None
