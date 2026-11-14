"""One launcher for audio plus independently failing control adapters."""
from __future__ import annotations
import argparse
import asyncio
import json
import logging
import threading
import time
from .runtime import Runtime


def main(argv=None):
    p = argparse.ArgumentParser(description='OmniRiff audio/control runtime')
    p.add_argument('--replay', metavar='CONTROLS.JSONL', help='explicit labeled one-shot control replay; disables UDP and serial input')
    p.add_argument('--headless', action='store_true', help='process silence without any audio hardware')
    p.add_argument('--duration', type=float, help='stop after this many seconds')
    p.add_argument('--serial-port', help='e.g. COM3; omitted = disabled')
    p.add_argument('--udp-port', type=int, default=47800)
    p.add_argument('--ws-port', type=int, default=47801)
    p.add_argument('--state-hz', type=float, default=20)
    p.add_argument('--stale-ms', type=int, default=250)
    p.add_argument('--samplerate', type=int, default=48000)
    p.add_argument('--blocksize', type=int, default=128)
    p.add_argument('--input-channel', type=int, default=2)
    p.add_argument('--out-channels', type=int, default=2)
    p.add_argument('--in', dest='in_dev')
    p.add_argument('--out', dest='out_dev')
    p.add_argument('--hostapi')
    p.add_argument('--exclusive', action='store_true')
    p.add_argument('--latency', default='low')
    p.add_argument('--gain-db', type=float, default=0)
    p.add_argument('--no-keyboard', action='store_true')
    p.add_argument('--take-dir', help='save each finished loop take as WAV + JSON for the practice coach (audio/takes.py)')
    p.add_argument('--check', action='store_true', help='preflight: packages, Focusrite, Arduino, free ports; opens no audio')
    a = p.parse_args(argv)
    if a.check:
        from .check import main_check
        return main_check(udp_port=a.udp_port, ws_port=a.ws_port, input_channel=a.input_channel)
    if min(a.samplerate, a.blocksize, a.input_channel, a.out_channels, a.stale_ms) <= 0:
        p.error('rates, sizes, channels and stale window must be positive')
    if a.duration is not None and a.duration <= 0: p.error('duration must be positive')
    replay = None
    if a.replay:
        if a.serial_port: p.error('--replay cannot be combined with --serial-port')
        from .replay import Replay
        try: replay = Replay.load(a.replay)
        except (OSError, ValueError) as exc: p.error(str(exc))
        logging.basicConfig(level=logging.WARNING, format='%(levelname)s %(message)s')
    from audio import Engine, EngineConfig
    audio = Engine(EngineConfig(samplerate=a.samplerate, input_gain_db=a.gain_db))
    takes = None
    if a.take_dir:
        from audio.takes import TakeWriter
        takes = TakeWriter(audio, a.take_dir).start()
    stop = threading.Event()
    errors = []
    if a.headless:
        def work():
            import numpy as np
            mono = np.zeros(a.blocksize, dtype=np.float32)
            out = np.zeros((a.blocksize, a.out_channels), dtype=np.float32)
            period = a.blocksize / a.samplerate
            deadline = time.monotonic()
            while not stop.is_set():
                audio.process(mono, out)
                # Pace against a monotonic deadline so headless runs at real time
                # (sleeping one period per block drifts slow by the processing time).
                deadline += period
                delay = deadline - time.monotonic()
                if delay > 0:
                    stop.wait(delay)
                elif delay < -0.5:
                    deadline = time.monotonic()  # fell far behind (e.g. machine suspended): resync
    else:
        from audio import stream
        in_dev = stream.resolve_device(a.in_dev, a.hostapi, 'input')
        out_dev = stream.resolve_device(a.out_dev, a.hostapi, 'output')
        try: latency = float(a.latency)
        except ValueError: latency = a.latency
        def work():
            stream.run_live(audio, in_dev, out_dev, a.input_channel, a.out_channels, a.blocksize, latency, a.exclusive, stop)
    def guarded_audio():
        try: work()
        except Exception as exc: errors.append(exc)
        finally: stop.set()
    worker = threading.Thread(target=guarded_audio, name='omniriff-audio', daemon=True)
    if not a.no_keyboard:
        from audio.__main__ import _keyboard
        threading.Thread(target=_keyboard, args=(audio, stop), daemon=True).start()
    runtime = Runtime(audio, udp_port=None if replay else a.udp_port, ws_port=a.ws_port, serial_port=a.serial_port, hz=a.state_hz, stale_ms=a.stale_ms, replay=replay)
    async def run():
        worker.start()
        await runtime.start()
        start = time.monotonic()
        try:
            while not stop.is_set():
                if a.duration and time.monotonic() - start >= a.duration: break
                await asyncio.sleep(0.05)
        finally:
            stop.set()
            await runtime.close()
            await asyncio.to_thread(worker.join, 2)
        print(json.dumps(runtime.snapshot(), allow_nan=False))
    try: asyncio.run(run())
    except KeyboardInterrupt: stop.set(); worker.join(2)
    finally:
        if takes:
            takes.stop()
            print(f'saved {len(takes.saved)} take(s) to {takes.directory}', flush=True)
    if errors: raise SystemExit(f'audio failed: {errors[0]}')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
