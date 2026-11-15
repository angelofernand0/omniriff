"""Render the promo's animated scenes to MP4, frame-accurately.

    python -m tools.promo.scenes.record                 # all scenes -> runs/promo/scenes/<scene>.mp4
    python -m tools.promo.scenes.record hook logo       # selected scenes
    python -m tools.promo.scenes.record --stills 1.3    # one PNG per scene at t=1.3 s (for review)

Each scene in scenes.html is a pure function of time, so every render is identical.
Frames are drawn with Playwright (your installed Chrome by default; --browser PATH
for another Chromium) and encoded with imageio-ffmpeg's bundled ffmpeg. Output goes
to runs/promo/ (git-ignored); existing files are refused unless --force.

Requires: pip install playwright imageio-ffmpeg (no Playwright browser download
needed when Google Chrome is installed).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BRAND = ROOT / "dashboard" / "brand"
FONTS = ROOT / "dashboard" / "fonts"
FPS = 30
SIZE = (1920, 1080)
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def build_page(out_dir: Path) -> Path:
    """Inline the brand SVGs and font paths into scenes.html (one brand source: dashboard/)."""
    html = (HERE / "scenes.html").read_text(encoding="utf-8")
    html = html.replace("{{FONT_DIR}}", FONTS.as_uri())
    html = html.replace("{{MARK_SVG}}", (BRAND / "mark.svg").read_text(encoding="utf-8").replace("`", ""))
    html = html.replace("{{WORDMARK_SVG}}", (BRAND / "wordmark.svg").read_text(encoding="utf-8").replace("`", ""))
    page = out_dir / "_scenes.html"
    page.write_text(html, encoding="utf-8")
    return page


def frame_times(duration: float, fps: int = FPS) -> list[float]:
    return [i / fps for i in range(int(round(duration * fps)))]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m tools.promo.scenes.record", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("scenes", nargs="*", help="scene names (default: all)")
    p.add_argument("--out", default=str(ROOT / "runs" / "promo" / "scenes"))
    p.add_argument("--browser", default=CHROME if Path(CHROME).exists() else None,
                   help="Chromium executable (default: installed Google Chrome)")
    p.add_argument("--stills", type=float, metavar="T", help="write one PNG per scene at time T instead of video")
    p.add_argument("--force", action="store_true", help="overwrite existing outputs")
    a = p.parse_args(argv)

    from playwright.sync_api import sync_playwright

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    page_path = build_page(out)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=a.browser) if a.browser else pw.chromium.launch()
        page = browser.new_page(viewport={"width": SIZE[0], "height": SIZE[1]}, device_scale_factor=1)
        page.goto(page_path.as_uri())
        page.evaluate("fontsReady()")
        available = page.evaluate("window.SCENES")
        names = a.scenes or list(available)
        unknown = [n for n in names if n not in available]
        if unknown:
            p.error(f"unknown scene(s): {', '.join(unknown)}; available: {', '.join(available)}")
        for name in names:
            if a.stills is not None:
                target = out / f"{name}-{a.stills:.2f}s.png"
                page.evaluate("([n, t]) => renderFrame(n, t)", [name, a.stills])
                page.screenshot(path=str(target))
                print(f"still: {target}")
                continue
            target = out / f"{name}.mp4"
            if target.exists() and not a.force:
                print(f"skip {target} (exists; --force to overwrite)")
                continue
            import subprocess
            import imageio_ffmpeg
            # PNG screenshots piped straight into ffmpeg (no image library needed).
            enc = subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
                                    "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "png", "-i", "-",
                                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-r", str(FPS), str(target)],
                                   stdin=subprocess.PIPE)
            times = frame_times(available[name])
            for i, t in enumerate(times):
                page.evaluate("([n, t]) => renderFrame(n, t)", [name, t])
                enc.stdin.write(page.screenshot(type="png"))
                if i % FPS == 0:
                    print(f"{name}: {t:4.1f}/{available[name]:.1f} s", flush=True)
            enc.stdin.close()
            if enc.wait() != 0:
                raise SystemExit(f"ffmpeg failed for {name}")
            print(f"wrote {target} ({len(times)} frames, {available[name]:.1f} s @ {FPS} fps)")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
