# Requires Pillow: pip install pillow (not part of the engine/dev requirements).
"""Pad gallery images to 3:2 aspect ratio with #0B0B10 for Devpost thumbnail safety.

Devpost cards and thumbnails use 3:2. Unpadded 16:9 screenshots get vertically
cropped by Devpost, clipping header meters or footer shortcuts. This script pads
each gallery image with #0B0B10 without altering the original screenshot pixels.
"""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "docs" / "media"
BG_COLOR = (11, 11, 16) # #0B0B10


def pad_to_3x2(src_path: Path, out_path: Path) -> None:
    img = Image.open(src_path).convert("RGB")
    w, h = img.size

    # 3:2 ratio: target_w / target_h = 1.5
    current_ratio = w / h
    target_ratio = 1.5

    if current_ratio > target_ratio:
        # Image is wider than 3:2 (e.g. 16:9 -> 1.777 > 1.5)
        # Pad top and bottom
        new_w = w
        new_h = int(round(w / target_ratio))
        canvas = Image.new("RGB", (new_w, new_h), BG_COLOR)
        offset_y = (new_h - h) // 2
        canvas.paste(img, (0, offset_y))
    else:
        # Image is taller than 3:2 (e.g. portrait 1280x1574)
        # Pad left and right
        new_h = h
        new_w = int(round(h * target_ratio))
        canvas = Image.new("RGB", (new_w, new_h), BG_COLOR)
        offset_x = (new_w - w) // 2
        canvas.paste(img, (offset_x, 0))

    canvas.save(out_path, format="PNG", optimize=True)
    print(f"Padded {src_path.name} ({w}x{h}) -> {out_path.name} ({canvas.size[0]}x{canvas.size[1]}, 3:2)")


def main():
    items = [
        ("gallery-01-coach.png", "gallery-01-coach-3x2.png"),
        ("gallery-02-hand.png", "gallery-02-hand-3x2.png"),
        ("gallery-03-evidence.png", "gallery-03-evidence-3x2.png"),
    ]
    for src, dst in items:
        src_path = MEDIA / src
        if src_path.exists():
            pad_to_3x2(src_path, MEDIA / dst)


if __name__ == "__main__":
    main()
