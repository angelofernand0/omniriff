#!/usr/bin/env python3
"""Animated OmniRiff logo: Riff looks around, hops, lands, and the letters get shoved right
by the landing and snap back together.

Reads the real pixels from dashboard/brand/logo.svg, so the animation can never drift from the
logo. One motion model (`pose`, `letter_offsets`) drives two outputs:

  dashboard/brand/logo-animated.gif        dark, for README, Devpost, social
  dashboard/brand/logo-animated-light.gif  light background
  dashboard/brand/logo-animated.svg        dark, tiny, scales crisply, for the site
  dashboard/brand/logo-animated-light.svg  light background
  dashboard/brand/logo-animated-bar.svg    dark, low hop, for the dashboard header (--bar)

Usage (Pillow is only needed for the GIFs):
  python tools/brand/animate_logo.py          # GIFs + SVGs
  python tools/brand/animate_logo.py --bar    # logo-animated-bar.svg, the dashboard header (low hop)

Brand rules kept (BRAND_SPEC.md): pixel grid, three colours, no decorative particles, letters
move in whole cells (the machine moves in steps), only Riff moves smoothly (squash and stretch).
"""
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRAND = ROOT / "dashboard" / "brand"

FPS = 25
DURATION = 4.2                    # seconds per loop
NFRAMES = round(FPS * DURATION)
SCALE = 8                         # GIF pixels per logo cell
PINK, INK, PAPER = "#FF5CCB", "#0B0B10", "#ECE9F5"
THEMES = {
    "": dict(bg="#0B0B10", pink=PINK, ink=INK, paper=PAPER, text=PAPER),
    "-light": dict(bg="#ECE9F5", pink=PINK, ink=INK, paper="#ECE9F5", text=INK),
}

# canvas in logo cells: room above for the hop, to the right for the shove
ML, MR, HEAD, MB = 4, 9, 13, 2
LOGO_W, LOGO_H = 68, 16
W, H = ML + LOGO_W + MR, HEAD + LOGO_H + MB
GROUND = HEAD + LOGO_H            # row just under Riff's feet
RIFF_CX = ML + 8                  # Riff's horizontal centre


# ---------------------------------------------------------------- source pixels
def read_logo():
    svg = (BRAND / "logo.svg").read_text()
    grid = {}
    for x, y, w, h, c in re.findall(
            r'<rect x="(\d+)" y="(\d+)" width="(\d+)" height="(\d+)" fill="(#[0-9A-Fa-f]+)"/>', svg):
        for i in range(int(w)):
            for j in range(int(h)):
                grid[(int(x) + i, int(y) + j)] = c.upper()
    return grid


def split(grid):
    """Riff sprite (16x16, eyes removed) and the eight letters, each as {(x, y): colour}."""
    body = {}
    for (x, y), c in grid.items():
        if x < 16:
            body[(x, y)] = PINK            # eye cells are filled; eyes are drawn per frame
    cols = sorted({x for (x, _) in grid if x >= 18})
    runs, start = [], cols[0]
    for a, b in zip(cols, cols[1:] + [None]):
        if b is None or b != a + 1:
            runs.append((start, a))
            start = b
    letters = [{(x, y): c for (x, y), c in grid.items() if lo <= x <= hi} for lo, hi in runs]
    assert len(letters) == 8, f"expected 8 letters, found {len(letters)}"
    return body, letters


# ---------------------------------------------------------------- motion model
def lerp(a, b, u):
    return a + (b - a) * u


def clamp01(u):
    return max(0.0, min(1.0, u))


def ease_out(u):
    u = clamp01(u)
    return 1 - (1 - u) ** 3


def ease_io(u):
    u = clamp01(u)
    return 3 * u * u - 2 * u ** 3


def seg(t, t0, t1):
    return clamp01((t - t0) / (t1 - t0))


# timeline, seconds
T_LOOK_L, T_LOOK_R, T_CENTRE = 0.55, 1.10, 1.62
T_CROUCH, T_LAUNCH, T_LAND = 1.72, 1.95, 2.60       # big hop: 0.65 s of air
T_HOP2, T_LAND2 = 2.95, 3.25                        # small echo hop
BIG_H, SMALL_H = 9.0, 3.0


def hop(t, t0, t1, height):
    """Parabola lift and normalised speed (0 at the peak, 1 at the ends)."""
    u = seg(t, t0, t1)
    if t < t0 or t > t1:
        return 0.0, 0.0
    return height * 4 * u * (1 - u), abs(1 - 2 * u)


def landing(t, t_land, amp):
    """Underdamped squash after touchdown: starts squashed, overshoots tall, wobbles out."""
    d = t - t_land
    if d < 0:
        return 0.0
    return -amp * math.exp(-10 * d) * math.cos(24 * d)


def pose(t):
    """Riff at time t: lift (cells), sx, sy (scale about bottom centre), eye dx/dy, eye mode."""
    lift = 0.0
    sy = 1.0
    # crouch before launch (anticipation), then stretch in the air
    if T_CROUCH <= t < T_LAUNCH:
        sy = 1 - 0.26 * ease_io(seg(t, T_CROUCH, T_LAUNCH - 0.04))
    h, v = hop(t, T_LAUNCH, T_LAND, BIG_H)
    if h or v:
        lift = h
        sy = 1 + 0.22 * v ** 0.8 - 0.05 * (1 - v)
    h2, v2 = hop(t, T_HOP2, T_LAND2, SMALL_H)
    if h2 or v2:
        lift = h2
        sy = 1 + 0.12 * v2
    if T_HOP2 - 0.1 <= t < T_HOP2:
        sy = 1 - 0.10 * ease_io(seg(t, T_HOP2 - 0.1, T_HOP2))
    sy += landing(t, T_LAND, 0.32) + landing(t, T_LAND2, 0.12)
    sy = max(0.6, sy)
    sx = 1 / math.sqrt(sy)                           # keep the volume

    # eyes
    dx = dy = 0.0
    mode = "open"
    if t < T_LOOK_L:
        pass
    elif t < T_LOOK_R:
        dx = -1.0
    elif t < T_CENTRE:
        dx = 1.0
    if T_CROUCH <= t < T_LAUNCH:
        dx, dy = 0.0, -1.0                           # looks up at where it is going
    elif T_LAUNCH <= t < T_LAND - 0.25:
        dx, dy = 0.0, -1.0
    elif T_LAND - 0.25 <= t < T_LAND:
        dx, dy = 1.0, 1.0                            # sees the letters coming
    if 0.30 <= t < 0.42:                             # one blink at rest
        mode = "blink"
    if T_LAND <= t < T_LAND + 0.30:
        mode = "happy"
    if T_LAND2 <= t < T_LAND2 + 0.12:
        mode = "blink"
    if T_LAND + 0.30 <= t < T_HOP2:
        dx = 1.0 if t < T_LAND + 0.60 else 0.0       # glances after the letters
    return dict(lift=lift, sx=sx, sy=sy, dx=dx, dy=dy, mode=mode)


WAVES = [  # start (s), cells at the last letter, snap-back time (s)
    (T_LAND, 7.0, 0.62),
    (T_LAND2, 3.0, 0.38),
]
OUT = 0.10                        # shove out
STAGGER_OUT = 0.012               # the shove hits every letter almost at once, so the gap opens
STAGGER_BACK = 0.025              # the snap back ripples left to right, so letters never collide


def wave_value(tau, back_t, lag):
    """0 before, 1 at the peak, ease back to 0 with a small snap past home."""
    if tau <= 0:
        return 0.0
    if tau < OUT:
        return ease_out(tau / OUT)
    u = (tau - OUT - lag) / back_t
    if u <= 0:
        return 1.0
    if u >= 1:
        return 0.0
    c1 = 1.15
    back = 1 + (c1 + 1) * (u - 1) ** 3 + c1 * (u - 1) ** 2        # easeOutBack
    return 1 - back


def letter_offsets(t, n=8):
    """(dx, dy) in whole cells per letter."""
    out = []
    for i in range(n):
        dx = 0.0
        for t0, amp, back_t in WAVES:
            tau = t - t0 - i * STAGGER_OUT
            reach = 0.45 + 0.55 * i / (n - 1)       # further letters travel further: the gap opens
            dx += amp * reach * wave_value(tau, back_t, i * STAGGER_BACK)
        out.append([round(dx), 0])
    for i in range(1, n):                           # never let a letter pass the one to its right
        out[i][0] = max(out[i][0], out[i - 1][0])
    return [tuple(o) for o in out]


# ---------------------------------------------------------------- eye shapes (cells, relative)
def eye_cells(mode):
    """List of (x, y, colour) for one eye whose top-left is (0, 0)."""
    if mode == "open":
        cells = [(0, j, "ink") for j in range(4)] + [(1, j, "ink") for j in range(4)]
        cells = [c for c in cells if c[:2] != (1, 0)] + [(1, 0, "paper")]
        return cells
    if mode == "blink":
        return [(0, 3, "ink"), (1, 3, "ink")]
    if mode == "happy":                              # ^ shape, three wide
        return [(1, 1, "ink"), (0, 2, "ink"), (2, 2, "ink")]
    raise ValueError(mode)


EYE_X = (4, 10)
EYE_Y = 5


# ---------------------------------------------------------------- raster for GIFs
def sprite_frame(body, p):
    """16x16 sprite with eyes drawn, as {(x, y): 'pink'|'ink'|'paper'}."""
    px = {k: "pink" for k in body}
    dx, dy = round(p["dx"]), round(p["dy"])
    for ex in EYE_X:
        for (cx, cy, col) in eye_cells(p["mode"]):
            x = ex + cx + dx
            y = EYE_Y + cy + dy
            if (x, y) in px:
                px[(x, y)] = col
    return px


def render_frame(body, letters, t, theme):
    from PIL import Image, ImageDraw
    p = pose(t)
    img = Image.new("RGB", (W * SCALE, H * SCALE), theme["bg"])
    draw = ImageDraw.Draw(img)
    colours = {"pink": theme["pink"], "ink": theme["ink"], "paper": theme["paper"]}

    def put(x, y, col):
        if 0 <= x < W and 0 <= y < H:
            draw.rectangle([x * SCALE, y * SCALE, (x + 1) * SCALE - 1, (y + 1) * SCALE - 1], fill=col)

    # Riff: nearest-neighbour resample of the 16x16 sprite into a w x h box, bottom centred
    spr = sprite_frame(body, p)
    w, h = max(1, round(16 * p["sx"])), max(1, round(16 * p["sy"]))
    left = RIFF_CX - w // 2
    top = GROUND - h - round(p["lift"])
    for Y in range(h):
        for X in range(w):
            sx_, sy_ = int((X + 0.5) * 16 / w), int((Y + 0.5) * 16 / h)
            c = spr.get((sx_, sy_))
            if c:
                put(left + X, top + Y, colours[c])
    # letters
    for (dx, dy), letter in zip(letter_offsets(t), letters):
        for (x, y), c in letter.items():
            col = theme["pink"] if c == PINK else theme["text"]
            put(ML + x + dx, HEAD + y + dy, col)
    return img


def write_gif(body, letters, name, theme):
    frames = [render_frame(body, letters, k / FPS, theme) for k in range(NFRAMES)]
    pal = frames[0].quantize(colors=4)
    frames = [f.quantize(palette=pal, dither=0) for f in frames]
    out = BRAND / f"logo-animated{name}.gif"
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=int(1000 / FPS),
                   loop=0, optimize=True, disposal=1)
    print(f"{out.relative_to(ROOT)}  {out.stat().st_size // 1024} KB  {W * SCALE}x{H * SCALE}  {NFRAMES} frames")


# ---------------------------------------------------------------- animated SVG
def runs(cells):
    """Merge a {(x, y): colour} dict into horizontal rects."""
    rects = []
    by_row = {}
    for (x, y), c in cells.items():
        by_row.setdefault((y, c), []).append(x)
    for (y, c), xs in sorted(by_row.items()):
        xs.sort()
        s = p = xs[0]
        for x in xs[1:] + [None]:
            if x is None or x != p + 1:
                rects.append((s, y, p - s + 1, c))
                s = x
            p = x
    return rects


def rect_svg(rects, cls=""):
    return "".join(f'<rect x="{x}" y="{y}" width="{w}" height="1" class="{cls or c}"/>' for x, y, w, c in rects)


def write_svg(body, letters, name, theme):
    frames = [k / FPS for k in range(NFRAMES)]
    poses = [pose(t) for t in frames]
    offs = [letter_offsets(t) for t in frames]
    pct = lambda k: f"{k * 100 / NFRAMES:.3f}".rstrip("0").rstrip(".")

    def track(name_, values):
        """CSS keyframes, only where the value changes. step-end holds each value."""
        out, last = [], None
        for k, v in enumerate(values):
            if v != last:
                out.append(f"{pct(k)}%{{{v}}}")
                last = v
        return f"@keyframes {name_}{{{''.join(out)}}}"

    css = []
    # Riff: matrix about bottom centre, then lift
    cx, gy = RIFF_CX, GROUND
    riff = []
    for p in poses:
        sx, sy = p["sx"], p["sy"]
        lift = round(p["lift"] * 2) / 2
        riff.append(f"transform:matrix({sx:.3f},0,0,{sy:.3f},{cx - sx * cx:.2f},{gy - sy * gy - lift:.2f})")
    css.append(track("riff", riff))
    # eyes: one group shifted by the look direction, three shapes toggled by mode
    css.append(track("look", [f"transform:translate({round(p['dx'])}px,{round(p['dy'])}px)" for p in poses]))
    for m in ("open", "blink", "happy"):
        css.append(track(f"m-{m}", [f"opacity:{1 if p['mode'] == m else 0}" for p in poses]))
    for i in range(8):
        css.append(track(f"l{i}", [f"transform:translate({o[i][0]}px,{o[i][1]}px)" for o in offs]))

    anim = f"{DURATION}s step-end infinite"
    style = (
        f".bg{{fill:{theme['bg']}}}.pink{{fill:{theme['pink']}}}.ink{{fill:{theme['ink']}}}"
        f".paper{{fill:{theme['paper']}}}.text{{fill:{theme['text']}}}"
        "g{transform-origin:0 0}"
        f"#riff{{animation:riff {anim}}}#look{{animation:look {anim}}}"
        + "".join(f"#e-{m}{{animation:m-{m} {anim}}}" for m in ("open", "blink", "happy"))
        + "".join(f"#l{i}{{animation:l{i} {anim}}}" for i in range(8))
        + "".join(css)
        + "@media (prefers-reduced-motion:reduce){#riff,#look,#e-open,#e-blink,#e-happy,"
          + ",".join(f"#l{i}" for i in range(8)) + "{animation:none}#e-blink,#e-happy{opacity:0}}"
    )

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W * 4}" height="{H * 4}" '
             'shape-rendering="crispEdges" role="img" aria-label="OmniRiff"><style>' + style + "</style>",
             ]   # no background rect: the SVGs are transparent so they sit on any page
    # Riff body in logo coordinates, then shifted into the canvas by the outer group
    sh = lambda cells: {(x + ML, y + HEAD): c for (x, y), c in cells.items()}   # into canvas cells
    parts.append('<g id="riff">')
    parts.append(rect_svg(runs(sh({k: "pink" for k in body}))))
    parts.append('<g id="look">')
    for m in ("open", "blink", "happy"):
        cells = {}
        for ex in EYE_X:
            for (x, y, c) in eye_cells(m):
                cells[(ex + x, EYE_Y + y)] = c
        parts.append(f'<g id="e-{m}">' + rect_svg(runs(sh(cells))) + "</g>")
    parts.append("</g></g>")
    for i, letter in enumerate(letters):
        cells = sh({k: ("pink" if c == PINK else "text") for k, c in letter.items()})
        parts.append(f'<g id="l{i}">' + rect_svg(runs(cells)) + "</g>")
    parts.append("</svg>")
    svg = "".join(parts)
    out = BRAND / f"logo-animated{name}.svg"
    out.write_text(svg)
    print(f"{out.relative_to(ROOT)}  {len(svg) // 1024} KB")


def configure_bar():
    """Dashboard header variant: the bar sits a few px from the window top, so the hop is low.
    The landing and the shove are unchanged."""
    global HEAD, H, GROUND, BIG_H, SMALL_H
    HEAD, BIG_H, SMALL_H = 5, 2.0, 1.0
    H = HEAD + LOGO_H + MB
    GROUND = HEAD + LOGO_H


def main():
    import sys
    if "--bar" in sys.argv:
        configure_bar()
        body, letters = split(read_logo())
        write_svg(body, letters, "-bar", THEMES[""])
        return
    body, letters = split(read_logo())
    for name, theme in THEMES.items():
        write_svg(body, letters, name, theme)
        try:
            write_gif(body, letters, name, theme)
        except ImportError:
            print("Pillow not installed: skipped GIFs (python -m pip install pillow)")


if __name__ == "__main__":
    main()
