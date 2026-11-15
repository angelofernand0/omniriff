"""Live-protocol checks against ephemeral fake servers; no hardware/model/control calls."""
import asyncio
import copy
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from tools.tablecheck import ORIGIN, check


class TableCheckTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        from audio import Engine, EngineConfig
        from engine.runtime import Runtime
        from coach.feed import initial_frame
        cls.engine = Runtime(Engine(EngineConfig(samplerate=8000))).snapshot()
        for name, adapter in cls.engine['adapters'].items():
            adapter['status'] = 'disabled' if name == 'serial' else 'running'
        cls.hand = dict(version=1, type='hand', timestamp_ms=0, present=False, engaged=False,
                        confidence=0., control='filter', value=None, landmarks=[])
        cls.coach = initial_frame('fake-tablecheck-session')

    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.takes = self.root / 'takes'; self.takes.mkdir()
        (self.takes / 'keep.wav').write_bytes(b'do not modify')
        self.model = self.root / 'hand.task'; self.model.write_bytes(b'not a loadable model, existence only')
        self.servers = []
        self.app_messages = []
        self.origins = []
        self.settings = {name: {} for name in ('engine', 'hand', 'coach', 'dashboard')}
        from websockets.asyncio.server import serve
        self.ports = {}
        for name, template in [('engine', self.engine), ('hand', self.hand), ('coach', self.coach)]:
            async def handler(ws, name=name, template=template):
                self.origins.append(ws.request.headers.get('Origin'))
                settings = self.settings[name]
                if not settings.get('silent'):
                    frame = copy.deepcopy(settings.get('frame', template))
                    if not settings.get('keep_time'):
                        frame['timestamp_ms'] = int(time.time() * 1000)
                    payload = settings.get('payload', json.dumps(frame))
                    await ws.send(payload)
                from websockets.exceptions import ConnectionClosed
                try:
                    async for message in ws:
                        self.app_messages.append(message)
                except ConnectionClosed:
                    pass  # oversized/malformed peers intentionally close the fake feed
            server = await serve(handler, '127.0.0.1', 0, origins=[ORIGIN], close_timeout=.1)
            self.servers.append(server)
            self.ports[name + '_port'] = server.sockets[0].getsockname()[1]
        async def http(reader, writer):
            try:
                request = await reader.readuntil(b'\r\n\r\n')
                self.assertTrue(request.startswith(b'GET '))
                self.assertIn(('Origin: ' + ORIGIN).encode(), request)
                settings = self.settings['dashboard']
                if settings.get('silent'):
                    await reader.read()
                    return
                body = settings.get('body', b'<html><title>OmniRiff</title></html>')
                status = settings.get('status', '200 OK')
                extra = settings.get('headers', '')
                # Sim server's one local redirect is supported.
                if settings.get('local_redirect') and request.startswith(b'GET / HTTP'):
                    status, extra = '302 Found', 'Location: /?sim=input\r\n'
                writer.write(f'HTTP/1.1 {status}\r\nContent-Type: text/html\r\n{extra}Content-Length: {len(body)}\r\nConnection: close\r\n\r\n'.encode() + body)
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()
        server = await asyncio.start_server(http, '127.0.0.1', 0)
        self.servers.append(server)
        self.ports['dashboard_port'] = server.sockets[0].getsockname()[1]

    async def asyncTearDown(self):
        for server in self.servers:
            server.close()
        await asyncio.gather(*(server.wait_closed() for server in self.servers))
        self.temporary.cleanup()

    async def run_check(self, **options):
        args = dict(self.ports, take_dir=self.takes, model=self.model, timeout=.3)
        args.update(options)
        return {row.name: row for row in await check(**args)}

    async def test_all_green_absent_hand_and_no_application_messages_or_take_changes(self):
        rows = await self.run_check()
        self.assertTrue(all(row.green for row in rows.values()), rows)
        self.assertIn('no hand seen', rows['hand'].detail)
        self.assertIn('xruns=0', rows['engine'].detail)
        self.assertIn('input_peak=', rows['engine'].detail)
        self.assertIn('loop=idle', rows['engine'].detail)
        self.assertIn('serial=disabled', rows['engine'].detail)
        self.assertEqual(self.app_messages, [])
        self.assertEqual(self.origins, [ORIGIN] * 3)
        self.assertEqual(list(self.takes.iterdir()), [self.takes / 'keep.wav'])
        self.assertEqual((self.takes / 'keep.wav').read_bytes(), b'do not modify')

    async def test_each_network_endpoint_down_does_not_hide_other_results(self):
        for name in ('engine', 'dashboard', 'hand', 'coach'):
            with self.subTest(endpoint=name):
                server = await asyncio.start_server(lambda r, w: w.close(), '127.0.0.1', 0)
                port = server.sockets[0].getsockname()[1]
                server.close(); await server.wait_closed()
                rows = await self.run_check(**{name + '_port': port})
                self.assertFalse(rows[name].green)
                self.assertTrue(all(row.green for key, row in rows.items() if key != name), rows)

    async def test_all_silent_endpoints_timeout_concurrently_under_five_seconds(self):
        for settings in self.settings.values():
            settings['silent'] = True
        started = time.monotonic()
        rows = await self.run_check(timeout=.2)
        self.assertLess(time.monotonic() - started, 2.)
        for name in ('engine', 'dashboard', 'hand', 'coach'):
            self.assertFalse(rows[name].green)
        self.assertTrue(rows['takes'].green and rows['model'].green)

    async def test_unfinished_websocket_handshake_times_out(self):
        async def stall(reader, writer):
            try:
                await reader.read()
            finally:
                writer.close(); await writer.wait_closed()
        server = await asyncio.start_server(stall, '127.0.0.1', 0)
        self.servers.append(server)
        rows = await self.run_check(engine_port=server.sockets[0].getsockname()[1], timeout=.2)
        self.assertFalse(rows['engine'].green)
        self.assertTrue(rows['coach'].green)

    async def test_malformed_binary_nonfinite_and_wrong_schema_frames(self):
        payloads = ['{', '{}', '[]', 'NaN', '1e999', b'binary', json.dumps(dict(self.engine, version=9)),
                    json.dumps(dict(self.engine, input_peak_dbfs=float('nan'))),
                    json.dumps(dict(self.engine, input_peak_dbfs=float('inf'))),
                    json.dumps(dict(self.engine, input_peak_dbfs=0)).replace('\"input_peak_dbfs\": 0', '\"input_peak_dbfs\": 1e999')]
        for payload in payloads:
            with self.subTest(payload=str(payload)[:30]):
                self.settings['engine']['payload'] = payload
                rows = await self.run_check()
                self.assertFalse(rows['engine'].green)
                self.assertTrue(rows['hand'].green)
        self.settings['engine']['payload'] = 'x' * 33000
        self.assertFalse((await self.run_check())['engine'].green)

    async def test_stale_engine_and_hand_fail_but_cached_idle_coach_is_valid(self):
        for name, template in [('engine', self.engine), ('hand', self.hand), ('coach', self.coach)]:
            self.settings[name].update(frame=dict(template, timestamp_ms=1), keep_time=True)
        rows = await self.run_check()
        self.assertFalse(rows['engine'].green)
        self.assertFalse(rows['hand'].green)
        self.assertTrue(rows['coach'].green)
        self.assertIn('cached idle is normal', rows['coach'].detail)

    async def test_dashboard_stale_thresholds_are_not_reported_green(self):
        now = int(time.time() * 1000)
        self.settings['engine'].update(frame=dict(self.engine, timestamp_ms=now - 1100), keep_time=True)
        self.settings['hand'].update(frame=dict(self.hand, timestamp_ms=now - 600), keep_time=True)
        rows = await self.run_check()
        self.assertFalse(rows['engine'].green)
        self.assertFalse(rows['hand'].green)

    async def test_xruns_and_active_adapter_failure_fail_without_mutating_counts(self):
        self.settings['engine']['frame'] = dict(self.engine, xruns=3)
        rows = await self.run_check()
        self.assertFalse(rows['engine'].green)
        self.assertIn('xruns=3 (total)', rows['engine'].detail)
        frame = copy.deepcopy(self.engine); frame['adapters']['serial']['status'] = 'error'
        self.settings['engine']['frame'] = frame
        self.assertFalse((await self.run_check())['engine'].green)
        frame['adapters']['serial']['status'] = 'disabled'
        frame['adapters']['udp']['status'] = 'disabled'
        self.assertFalse((await self.run_check())['engine'].green)
        self.assertEqual(self.app_messages, [])

    async def test_scripted_coach_explicit_and_out_of_credit_red(self):
        self.settings['coach']['frame'] = dict(self.coach, scripted=True)
        rows = await self.run_check()
        self.assertTrue(rows['coach'].green)
        self.assertIn('SCRIPTED', rows['coach'].detail)
        for cue in ('Coach is out of credit.', 'Coach is out of credit; keep playing without me.'):
            self.settings['coach']['frame'] = dict(self.coach, state='asleep', cue=cue)
            rows = await self.run_check()
            self.assertFalse(rows['coach'].green)
            self.assertIn('OUT OF CREDIT', rows['coach'].detail)
        self.settings['coach']['frame'] = dict(self.coach, state='asleep', cue='Free play.')
        self.assertTrue((await self.run_check())['coach'].green)

    async def test_non_status_coach_messages_cannot_make_check_green(self):
        self.settings['coach']['payload'] = json.dumps(dict(version=1, type='coach.say', timestamp_ms=1, text='Hi'))
        self.assertFalse((await self.run_check())['coach'].green)

    async def test_replay_coach_is_named_and_probe_remains_read_only(self):
        replay = dict(self.coach, session_id='replay-synthetic-test', scripted=True)
        self.settings['coach']['frame'] = replay
        result = (await self.run_check())['coach']
        self.assertTrue(result.green)
        self.assertIn('REPLAY — recorded feed, not live', result.detail)
        self.assertNotIn('LIVE feed', result.detail)
        self.assertNotIn('SCRIPTED — NOT LIVE AI', result.detail)
        self.assertEqual(self.app_messages, [])
        self.settings['coach']['frame'] = dict(replay, cue='Coach is out of credit.')
        result = (await self.run_check())['coach']
        self.assertFalse(result.green)
        self.assertIn('REPLAY', result.detail)
        self.assertIn('OUT OF CREDIT', result.detail)

    async def test_replay_prefix_cannot_be_reported_as_a_live_coach(self):
        self.settings['coach']['frame'] = dict(self.coach, session_id='replay-synthetic-test', scripted=False)
        result = (await self.run_check())['coach']
        self.assertFalse(result.green)
        self.assertIn('REPLAY metadata inconsistent', result.detail)
        self.assertNotIn('LIVE feed', result.detail)
        self.assertEqual(self.app_messages, [])

    async def test_optional_components_skip_their_networks_and_model(self):
        self.settings['hand']['silent'] = self.settings['coach']['silent'] = True
        rows = await self.run_check(no_vision=True, no_coach=True, model=self.root / 'missing')
        self.assertEqual(set(rows), {'engine', 'dashboard', 'takes'})
        self.assertTrue(all(row.green for row in rows.values()))
        self.assertEqual(self.origins, [ORIGIN])

    async def test_missing_model_take_dir_and_permission_failure(self):
        rows = await self.run_check(model=self.takes, take_dir=self.root / 'missing')
        self.assertFalse(rows['model'].green)
        self.assertFalse(rows['takes'].green)
        self.model.write_bytes(b'')
        self.assertFalse((await self.run_check())['model'].green)
        with patch('tools.tablecheck.tempfile.TemporaryFile', side_effect=PermissionError()):
            rows = await self.run_check()
            self.assertFalse(rows['takes'].green)
        self.assertEqual(list(self.takes.iterdir()), [self.takes / 'keep.wav'])

    async def test_http_failure_wrong_page_and_local_only_redirect(self):
        settings = self.settings['dashboard']
        for option in ({'status': '503 Unavailable'}, {'body': b'<html>Other app</html>'},
                       {'status': '302 Found', 'headers': 'Location: https://example.com/\r\n'}):
            settings.clear(); settings.update(option)
            self.assertFalse((await self.run_check())['dashboard'].green)
        settings.clear(); settings['local_redirect'] = True
        self.assertTrue((await self.run_check())['dashboard'].green)

    async def test_local_probe_timeout_does_not_block_other_checks(self):
        from tools.tablecheck import Result
        def slow_model(path):
            time.sleep(.5)
            return Result('model', True, 'late')
        with patch('tools.tablecheck.model_check', slow_model):
            started = time.monotonic()
            rows = await self.run_check(timeout=.1)
            self.assertFalse(rows['model'].green)
            self.assertLess(time.monotonic() - started, .45)

    async def test_maximum_deadline_includes_fresh_cli_startup_under_five_seconds(self):
        for settings in self.settings.values():
            settings['silent'] = True
        flags = [item for name, port in self.ports.items() for item in ('--' + name.replace('_', '-'), str(port))]
        started = time.monotonic()
        proc = await asyncio.create_subprocess_exec(sys.executable, '-m', 'tools.tablecheck',
            '--take-dir', str(self.takes), '--model', str(self.model), '--timeout', '3', *flags,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(proc.communicate(), 5)
        self.assertLess(time.monotonic() - started, 5.)
        self.assertEqual(proc.returncode, 1, stderr.decode())
        self.assertEqual(sum(line.startswith(b'RED ') for line in stdout.splitlines()), 4)

    async def test_cli_exit_codes_and_one_line_results(self):
        flags = [item for name, port in self.ports.items() for item in ('--' + name.replace('_', '-'), str(port))]
        args = ['--take-dir', str(self.takes), '--model', str(self.model), '--timeout', '.3', *flags]
        async def cli(arguments):
            proc = await asyncio.create_subprocess_exec(sys.executable, '-m', 'tools.tablecheck', *arguments,
                                                      stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await asyncio.wait_for(proc.communicate(), 5)
            return proc.returncode, stdout.decode(), stderr.decode()
        code, stdout, stderr = await cli(args)
        self.assertEqual(code, 0, stderr + stdout)
        self.assertEqual(sum(line.startswith('GREEN ') for line in stdout.splitlines()), 6)
        self.assertNotIn('RED ', stdout)
        self.settings['engine']['silent'] = True
        code, stdout, stderr = await cli(args)
        self.assertEqual(code, 1, stderr + stdout)
        self.assertIn('RED engine:', stdout)
        code, stdout, stderr = await cli(['--timeout', '9'])
        self.assertEqual(code, 2)
        self.assertIn('timeout must be', stderr)
