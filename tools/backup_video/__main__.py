"""Record the real dashboard and processed virtual guitar as a labelled MP4.

The capture is a fallback artifact, not proof of webcam, pedal, guitar or
interface operation. Browser/encoding dependencies are optional; see README.
"""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time

import numpy as np

from audio import Engine, EngineConfig
from audio.fileio import write_wav
from dashboard.__main__ import make_server
from engine.replay import Replay
from engine.runtime import Runtime
from tools.virtual_guitar.render import synthetic_signal


ROOT = Path(__file__).resolve().parents[2]
CONTROLS = ROOT / "engine" / "demo-controls.jsonl"
LABEL = "SIMULATED GUITAR + SCRIPTED CONTROLS / NO HARDWARE"
SAMPLERATE = 48000
BLOCKSIZE = 256


def validate_duration(seconds: float, replay: Replay) -> None:
    """Keep every scripted control on tape and meet the optional video limit."""
    if not 0 < seconds <= 120:
        raise ValueError("--seconds must be greater than 0 and at most 120")
    last = replay.entries[-1][0] / 1000
    if seconds < last + 0.5:
        raise ValueError(f"--seconds must be at least {last + 0.5:g} for the final control to appear")


def ffmpeg_executable() -> str:
    """Use a normal ffmpeg install or the optional local wheel binary."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError) as exc:
        raise RuntimeError("ffmpeg is required (on PATH or pip install imageio-ffmpeg)") from exc


def preflight(output: Path, browser_executable: str | None) -> None:
    if output.exists():
        raise ValueError(f"output already exists: {output}; choose a new filename")
    if output.suffix.lower() != ".mp4":
        raise ValueError("--output must end in .mp4")
    ffmpeg_executable()
    if browser_executable and not Path(browser_executable).is_file():
        raise ValueError(f"browser executable not found: {browser_executable}")
    try:
        import playwright.async_api  # noqa: F401 - optional runtime dependency
    except ImportError as exc:
        raise RuntimeError("Playwright is required: pip install playwright; see tools/backup_video/README.md") from exc


def audio_worker(audio: Engine, source: np.ndarray, output: np.ndarray,
                 start: threading.Event, abort: threading.Event, done: threading.Event,
                 errors: list[Exception]) -> None:
    """Pace precomputed audio through the production DSP; no disk/browser I/O here."""
    try:
        start.wait()
        deadline = time.monotonic()
        for pos in range(0, len(source), BLOCKSIZE):
            if abort.is_set():
                return
            end = min(len(source), pos + BLOCKSIZE)
            audio.process(source[pos:end], output[pos:end])
            deadline += (end - pos) / SAMPLERATE
            delay = deadline - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            elif delay < -0.5:
                deadline = time.monotonic()
    except Exception as exc:
        errors.append(exc)
    finally:
        done.set()


async def wait_for_socket(runtime: Runtime, timeout: float = 5) -> None:
    deadline = time.monotonic() + timeout
    while runtime.server is None and time.monotonic() < deadline:
        await asyncio.sleep(0.05)
    if runtime.server is None:
        raise RuntimeError("dashboard state WebSocket did not start")


async def capture(video_dir: Path, wav_path: Path, seconds: float, replay: Replay,
                  browser_executable: str | None) -> tuple[Path, float]:
    """Run one replay for the displayed state and the actual recorded DSP audio."""
    from playwright.async_api import async_playwright

    source = synthetic_signal(seconds, SAMPLERATE, blocksize=BLOCKSIZE)
    processed = np.zeros((len(source), 2), np.float32)
    audio = Engine(EngineConfig(samplerate=SAMPLERATE))
    runtime = Runtime(audio, udp_port=None, ws_port=0)
    http = make_server(0, sim="guitar")
    http_thread = threading.Thread(target=http.serve_forever, name="backup-video-http", daemon=True)
    start = threading.Event()
    abort = threading.Event()
    done = threading.Event()
    errors: list[Exception] = []
    worker = threading.Thread(target=audio_worker, args=(audio, source, processed, start, abort, done, errors),
                              name="backup-video-audio", daemon=True)
    replay_task = None
    video_path = None
    offset = 0.0
    try:
        http_thread.start()
        await runtime.start()
        await wait_for_socket(runtime)
        worker.start()
        async with async_playwright() as p:
            launch = {"headless": True}
            if browser_executable:
                launch["executable_path"] = browser_executable
            else:
                launch["channel"] = "chrome"
            browser = await p.chromium.launch(**launch)
            try:
                context = await browser.new_context(viewport={"width": 1280, "height": 720},
                                                    record_video_dir=str(video_dir),
                                                    record_video_size={"width": 1280, "height": 720})
                try:
                    page = await context.new_page()
                    video_start = time.monotonic()
                    url = (f"http://127.0.0.1:{http.server_port}/?sim=guitar"
                           f"&ws=ws://127.0.0.1:{runtime.ws_port}&hand=off&coach=off")
                    await page.goto(url, wait_until="load")
                    await page.wait_for_function("document.querySelector('#app')?.dataset.conn === 'live'",
                                                 timeout=10000)
                    # Keep the disclosure on screen even if the dashboard layout changes.
                    await page.evaluate("""label => {
                      const badge = document.createElement('div');
                      badge.id = 'backup-video-disclosure';
                      badge.textContent = label;
                      Object.assign(badge.style, {position:'fixed',bottom:'10px',right:'10px',
                        zIndex:'2147483647',padding:'7px 10px',background:'#160d1b',
                        color:'#ffcf64',border:'2px solid #ffcf64',font:'bold 13px monospace',
                        pointerEvents:'none'});
                      document.body.appendChild(badge);
                    }""", LABEL)
                    await page.wait_for_timeout(300)
                    # The page has a short, labelled pre-roll. Trim it when muxing.
                    offset = time.monotonic() - video_start
                    runtime.replay = replay
                    start.set()
                    replay_task = asyncio.create_task(replay.run(runtime.router))
                    await asyncio.to_thread(done.wait, seconds + 10)
                    if not done.is_set():
                        raise RuntimeError("audio render exceeded its real-time deadline")
                    if errors:
                        raise RuntimeError(f"audio processing failed: {errors[0]}")
                    await replay_task
                    if replay.state["status"] != "completed":
                        raise RuntimeError(f"control replay ended as {replay.state['status']}")
                    await page.wait_for_timeout(300)
                    video = page.video
                    if video is None:
                        raise RuntimeError("browser did not create a video recording")
                finally:
                    await context.close()
                video_path = Path(await video.path())
            finally:
                await browser.close()
        write_wav(wav_path, processed, SAMPLERATE)
        return video_path, offset
    finally:
        abort.set()
        start.set()  # never strand the worker on an early browser failure
        if replay_task is not None and not replay_task.done():
            replay_task.cancel()
            await asyncio.gather(replay_task, return_exceptions=True)
        await runtime.close()
        http.shutdown()
        http.server_close()
        await asyncio.to_thread(http_thread.join, 2)
        if worker.is_alive():
            await asyncio.to_thread(worker.join, 2)


def mux(video: Path, audio: Path, target: Path, seconds: float, offset: float) -> None:
    """Encode to a temporary MP4, then publish without overwriting an existing file."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="omniriff-mux-", dir=target.parent) as folder:
        staged = Path(folder) / "backup.mp4"
        command = [ffmpeg_executable(), "-hide_banner", "-loglevel", "error", "-nostdin",
                   "-ss", f"{offset:.3f}", "-i", str(video), "-i", str(audio),
                   "-t", f"{seconds:.3f}", "-map", "0:v:0", "-map", "1:a:0",
                   "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "21",
                   "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(staged)]
        subprocess.run(command, check=True)
        if not staged.is_file() or staged.stat().st_size == 0:
            raise RuntimeError("ffmpeg did not produce an MP4")
        os.link(staged, target)  # atomic no-clobber publish on the same filesystem


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record a clearly SIMULATED OmniRiff dashboard + processed guitar clip")
    parser.add_argument("--output", default="recordings/backup-simulated.mp4", help="new MP4 path; never overwritten")
    parser.add_argument("--seconds", type=float, default=10.0, help="clip duration, 7.5–120 s with the demo controls")
    parser.add_argument("--browser-executable", help="optional Chrome/Chromium executable path")
    args = parser.parse_args(argv)
    output = Path(args.output).expanduser().resolve()
    try:
        replay = Replay.load(CONTROLS)
        validate_duration(args.seconds, replay)
        preflight(output, args.browser_executable)
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="omniriff-capture-", dir=output.parent) as folder:
            temporary = Path(folder)
            video, offset = asyncio.run(capture(temporary, temporary / "processed.wav", args.seconds,
                                                replay, args.browser_executable))
            mux(video, temporary / "processed.wav", output, args.seconds, offset)
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"backup video: {exc}\n")
    print(f"SIMULATED backup clip: {output}")
    print("Not hardware, live webcam, pedal, guitar, latency or model validation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
