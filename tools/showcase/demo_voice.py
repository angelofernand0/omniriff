"""Render the demo coach's lines in Riff's ElevenLabs voice, into the website build.

Reads LINES from dashboard/browser/coach/demo-script.ts, writes demo-voice/<id>.mp3 next to it,
and rewrites each line's `ms` with the clip's real length, so the demo waits for Riff to finish
a sentence before the next beat. Needs ELEVENLABS_API_KEY (repo .env or ~/.config/omniriff/.env);
clips are cached by coach/voice.py, so re-running only renders changed lines.

    python -m tools.showcase.demo_voice
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from coach.voice import Voice

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "dashboard" / "browser" / "coach" / "demo-script.ts"
OUT = SCRIPT.parent / "demo-voice"
LINE = re.compile(r'^(\s*)(\w+): \{ text: (["\'])(.*?)\3, ms: (\d+) \},$', re.M)


def clip_ms(path: Path) -> int | None:
    try:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        ffmpeg = "ffmpeg"
    result = subprocess.run([ffmpeg, "-i", str(path), "-f", "null", "-"], capture_output=True, text=True)
    times = re.findall(r"time=(\d+):(\d+):(\d+\.\d+)", result.stderr)
    if not times:
        return None
    h, m, s = times[-1]
    return round((int(h) * 3600 + int(m) * 60 + float(s)) * 1000)


def main() -> int:
    voice = Voice.from_env()
    OUT.mkdir(exist_ok=True)
    source = SCRIPT.read_text()
    failed = 0

    def render(match: re.Match) -> str:
        nonlocal failed
        indent, line_id, quote, text, ms = match.groups()
        audio = voice.synthesize(text.replace("\\'", "'"))
        if not audio:
            failed += 1
            print(f"{line_id}: no audio ({voice.last_error})")
            return match.group(0)
        path = OUT / f"{line_id}.mp3"
        path.write_bytes(audio)
        length = clip_ms(path) or int(ms)
        print(f"{line_id}: {len(audio) // 1024} KB, {length} ms")
        return f"{indent}{line_id}: {{ text: {quote}{text}{quote}, ms: {length + 400} }},"

    SCRIPT.write_text(LINE.sub(render, source))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
