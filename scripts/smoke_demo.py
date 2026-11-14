"""Run before bring-up: python scripts/smoke_demo.py

Synthetic/silence inputs only. No audio stream, camera, browser or serial port
is opened. Device failures in preflight are reported, not hardware validation.
"""
from __future__ import annotations

import asyncio
import json
import math
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import time
import wave

ROOT = Path(__file__).resolve().parents[1]


def run_python(args, timeout=30):
    """Native subprocess.run kills and reaps a child on timeout, on Windows too."""
    try:
        result = subprocess.run([sys.executable, *map(str, args)], cwd=ROOT,
                                capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f'command timed out after {timeout}s: {args}') from exc
    if result.returncode:
        raise RuntimeError(f'exit {result.returncode}: {args}\n{result.stdout[-3000:]}\n{result.stderr[-3000:]}')
    return result.stdout


def objects(output):
    decoder, found, offset = json.JSONDecoder(), [], 0
    while (start := output.find('{', offset)) >= 0:
        try:
            value, size = decoder.raw_decode(output[start:])
        except ValueError:
            offset = start + 1
        else:
            found.append(value)
            offset = start + size
    return found


def state_from(output):
    for value in reversed(objects(output)):
        if 'controls' in value and 'xruns' in value:
            check_state(value)
            return value
    raise RuntimeError('command returned no engine state')


def check_state(state):
    if state['xruns'] != 0 or state['clipped_samples'] != 0:
        raise RuntimeError('simulated engine reported xruns or clipping')
    drops = {k: v for k, v in state['controls'].items() if k != 'accepted' and v}
    if drops:
        raise RuntimeError(f'unexpected control drops: {drops}')
    if any(item['errors'] for item in state['adapters'].values()):
        raise RuntimeError('adapter reported an error')


def preflight_ok(output, code):
    """Hardware absence is expected; missing dependencies/ports are failures."""
    failures = [line for line in output.splitlines() if line.startswith('FAIL')]
    if (not any(line.startswith(('PASS ', 'WARN ', 'FAIL ')) for line in output.splitlines())
            or code not in (0, 1) or (code == 1 and not failures)):
        return False
    return all(line.startswith('FAIL  audio ') for line in failures)


def preflight():
    result = subprocess.run([sys.executable, '-m', 'engine', '--check', '--udp-port', '0', '--ws-port', '0'],
                            cwd=ROOT, capture_output=True, text=True, timeout=30)
    print(result.stdout, end='', flush=True)
    if not preflight_ok(result.stdout, result.returncode):
        raise RuntimeError(f'unexpected preflight failure\n{result.stderr[-3000:]}')


def launcher():
    state_from(run_python(['-m', 'engine.demo', '--headless', '--no-keyboard', '--duration', '3',
                           '--http-port', '0', '--udp-port', '0', '--ws-port', '0']))


def replay_and_ears(directory):
    session, takes = directory/'session.jsonl', directory/'takes'
    state = state_from(run_python(['-m', 'engine', '--headless', '--no-keyboard', '--duration', '4',
                                  '--udp-port', '0', '--ws-port', '0', '--replay', 'engine/demo-controls.jsonl',
                                  '--session-log', session, '--take-dir', takes]))
    if state['controls']['accepted'] < 4 or state['replay']['status'] == 'error':
        raise RuntimeError('replay did not reach the recorded-loop portion')
    records = [json.loads(line) for line in session.read_text().splitlines()]
    controls = [r for r in records if r['kind'] == 'control']
    if records[0]['kind'] != 'start' or records[-1]['kind'] != 'stop' or len(controls) != state['controls']['accepted']:
        raise RuntimeError('session log is incomplete')
    wavs = list(takes.glob('*.wav'))
    if len(wavs) != 1 or not wavs[0].with_suffix('.json').is_file():
        raise RuntimeError('expected one captured take and sidecar')
    reports = objects(run_python(['-m', 'tools.ears', wavs[0]]))
    if not reports or reports[-1].get('source') != 'tools.ears' or reports[-1].get('strum_count') != 0:
        raise RuntimeError('Ears did not report the captured silence take correctly')


def free_port(kind=socket.SOCK_STREAM):
    with socket.socket(socket.AF_INET, kind) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


async def read_sim_state(port):
    from websockets.asyncio.client import connect
    deadline = time.monotonic() + 7
    while time.monotonic() < deadline:
        try:
            async with connect(f'ws://127.0.0.1:{port}', open_timeout=.5) as ws:
                while time.monotonic() < deadline:
                    state = json.loads(await asyncio.wait_for(ws.recv(), 1))
                    check_state(state)
                    if state['controls']['accepted'] > 0:
                        return state
        except OSError:
            await asyncio.sleep(.05)
    raise RuntimeError('simulator did not publish an accepted control over WS')


def simulator():
    udp, ws = free_port(socket.SOCK_DGRAM), free_port()
    command = [sys.executable, '-m', 'tools.sim', 'run', '--demo', '--duration', '5',
               '--udp-port', str(udp), '--ws-port', str(ws), '--http-port', '0', '--hand-port', '0']
    child = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        asyncio.run(asyncio.wait_for(read_sim_state(ws), 10))
        output, errors = child.communicate(timeout=15)
        if child.returncode:
            raise RuntimeError(f'simulator exit {child.returncode}\n{output}\n{errors}')
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=5)


def cpu_cost():
    reports = objects(run_python(['-m', 'tools.latency', '--engine-only']))
    if not reports or reports[-1].get('mode') != 'engine-only' or not reports[-1].get('results'):
        raise RuntimeError('missing engine-only CPU report')


def levels(directory):
    path = directory/'synthetic.wav'
    rate = 48000
    samples = (int(3276 * math.sin(2 * math.pi * 440 * n / rate)) for n in range(rate))
    with wave.open(str(path), 'wb') as wav:
        wav.setparams((1, 2, rate, rate, 'NONE', 'not compressed'))
        wav.writeframes(b''.join(struct.pack('<h', sample) for sample in samples))
    reports = objects(run_python(['-m', 'audio', '--level-check', '--input-wav', path]))
    if not reports or reports[-1].get('advice') != 'good' or reports[-1].get('clipped_samples') != 0:
        raise RuntimeError('unexpected level result for generated -20 dBFS sine')


def main():
    print('SMOKE: synthetic/silence inputs; no audio I/O, camera or pedal. Hardware remains unverified.', flush=True)
    failures = 0
    with tempfile.TemporaryDirectory(prefix='omniriff-smoke-') as temporary:
        directory = Path(temporary)
        steps = [('preflight (audio-device FAILs reported but expected off-laptop)', preflight),
                 ('engine.demo headless', launcher),
                 ('replay + session log + take + Ears', lambda: replay_and_ears(directory)),
                 ('simulator WS state (synthetic input)', simulator),
                 ('engine CPU cost (not I/O latency)', cpu_cost),
                 ('level check on generated WAV', lambda: levels(directory))]
        for name, function in steps:
            try:
                function()
            except Exception as exc:
                failures += 1
                print(f'FAIL {name}: {type(exc).__name__}: {exc}', flush=True)
            else:
                print(f'PASS {name}', flush=True)
    print(f'SMOKE: {len(steps)-failures}/{len(steps)} passed. Live Windows/Solo/Arduino checks are separate.', flush=True)
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
