"""OmniRiff simulator.

  python -m tools.sim run [--demo]       real audio.Engine + engine.Runtime, synthetic guitar input,
                                         dashboard served on http://127.0.0.1:8080
  python -m tools.sim send loop|bypass   one action event over UDP 47800
  python -m tools.sim send filter 0.4    one parameter event (confidence 1.0 unless --confidence)

Everything here is simulated input; nothing measures hardware or latency.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import threading
import time


def _run(a) -> int:
    import numpy as np
    from audio import Engine, EngineConfig
    from engine.runtime import Runtime
    from dashboard.__main__ import make_server
    from .synth import SyntheticGuitar
    from .demo import run_demo

    audio = Engine(EngineConfig(samplerate=a.samplerate))
    guitar = SyntheticGuitar(a.samplerate, bpm=a.bpm, level=0.0 if a.silent else 0.28)
    stop = threading.Event()

    def work():
        out = np.zeros((a.blocksize, 2), dtype=np.float32)
        period = a.blocksize / a.samplerate
        nxt = time.monotonic()
        while not stop.is_set():
            audio.process(guitar.block(a.blocksize), out)
            nxt += period
            delay = nxt - time.monotonic()
            if delay > 0:
                stop.wait(delay)
            elif delay < -0.25:
                nxt = time.monotonic()  # fell far behind; don't spin to catch up

    runtime = Runtime(audio, udp_port=a.udp_port, ws_port=a.ws_port)
    http = None
    if a.http_port:
        http = make_server(a.http_port, sim='input')  # the page then reads SIMULATED
        threading.Thread(target=http.serve_forever, daemon=True, name='omniriff-http').start()

    async def main():
        threading.Thread(target=work, daemon=True, name='omniriff-sim-audio').start()
        await runtime.start()
        await asyncio.sleep(0.2)
        print(f'[sim] engine state ws://127.0.0.1:{runtime.ws_port}  control udp 127.0.0.1:{runtime.udp_port}')
        if http:
            print(f'[sim] dashboard http://127.0.0.1:{http.server_address[1]}/')
        print('[sim] SIMULATED input (synthetic guitar)' + (' + scripted demo' if a.demo else '') + '. Ctrl-C to stop.')
        view, hand_task = None, None
        if a.demo and a.hand_port:
            from .hand import HandState, serve_hand
            view = HandState()
            hand_task = asyncio.create_task(serve_hand(view, a.hand_port))
            print(f'[sim] SIMULATED hand view ws://127.0.0.1:{a.hand_port}')
        demo = asyncio.create_task(run_demo(runtime.udp_port, view=view)) if a.demo else None
        coach_task = None
        if a.coach_sim:
            from .coach import run_scripted_coach
            coach_task = asyncio.create_task(run_scripted_coach(
                a.coach_port, f'ws://127.0.0.1:{runtime.ws_port}', runtime.udp_port, voice=_voice(a)))
            print(f'[sim] SCRIPTED coach session ws://127.0.0.1:{a.coach_port} (no AI)')
        start = time.monotonic()
        try:
            while not (a.duration and time.monotonic() - start >= a.duration):
                await asyncio.sleep(0.1)
        finally:
            if demo:
                demo.cancel()
            if coach_task:
                coach_task.cancel()
            if hand_task:
                hand_task.cancel()
            stop.set()
            await runtime.close()
            if http:
                http.shutdown()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        stop.set()
    return 0


def _send(a) -> int:
    from .events import Sender
    s = Sender(a.source, port=a.udp_port)
    try:
        print(json.dumps(s.send(a.control, a.value, a.confidence)))
    finally:
        s.close()
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog='python -m tools.sim', description='OmniRiff simulator (simulated input only)')
    sub = p.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run', help='engine + synthetic guitar + dashboard server')
    r.add_argument('--demo', action='store_true', help='scripted pedal presses and pinch sweeps')
    r.add_argument('--silent', action='store_true', help='feed silence instead of the synthetic guitar')
    r.add_argument('--bpm', type=float, default=92)
    r.add_argument('--udp-port', type=int, default=47800)
    r.add_argument('--ws-port', type=int, default=47801)
    r.add_argument('--http-port', type=int, default=8080, help='0 disables the dashboard server')
    r.add_argument('--hand-port', type=int, default=47802,
                   help='with --demo: serve a simulated hand-view feed here (0 disables; vision uses the same port)')
    r.add_argument('--samplerate', type=int, default=48000)
    r.add_argument('--blocksize', type=int, default=256)
    r.add_argument('--duration', type=float)
    r.add_argument('--coach-sim', action='store_true',
                   help='serve a SCRIPTED coach session on --coach-port (no AI; labelled on screen)')
    r.add_argument('--coach-port', type=int, default=47803)
    r.add_argument('--no-voice', action='store_true', help="with --coach-sim: browser voice only, no ElevenLabs")
    c = sub.add_parser('coach', help='SCRIPTED coach session against a running engine (no AI; labelled on screen)')
    c.add_argument('--port', type=int, default=47803)
    c.add_argument('--engine-ws', default='ws://127.0.0.1:47801')
    c.add_argument('--udp-port', type=int, default=47800, help='where approved bypass goes (0: never touch the rig)')
    c.add_argument('--no-voice', action='store_true', help="don't render cues with ElevenLabs (browser voice only)")
    s = sub.add_parser('send', help='send one control event over UDP')
    s.add_argument('control', choices=['loop', 'bypass', 'filter', 'reverb'])
    s.add_argument('value', type=float, nargs='?')
    s.add_argument('--confidence', type=float)
    s.add_argument('--source', default='manual', choices=['manual', 'vision', 'sensecap'])
    s.add_argument('--udp-port', type=int, default=47800)
    a = p.parse_args(argv)
    if a.cmd == 'send':
        if (a.control in ('filter', 'reverb')) != (a.value is not None):
            p.error('filter/reverb need a value in [0, 1]; loop/bypass take none')
        return _send(a)
    if a.cmd == 'coach':
        return _coach(a)
    return _run(a)


def _voice(a):
    if a.no_voice:
        return None
    from coach.voice import Voice
    v = Voice.from_env()
    print('[sim] coach voice: ' + ('ElevenLabs (cached)' if v.api_key else 'no ELEVENLABS_API_KEY, browser voice only'))
    return v


def _coach(a) -> int:
    from .coach import run_scripted_coach
    print(f'[sim] SCRIPTED coach session ws://127.0.0.1:{a.port} (no AI) following {a.engine_ws}. Ctrl-C to stop.')
    try:
        asyncio.run(run_scripted_coach(a.port, a.engine_ws, a.udp_port or None, voice=_voice(a)))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
