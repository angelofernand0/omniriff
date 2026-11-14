"""Render a labeled synthetic scene demonstration using the existing audio DSP."""
import argparse
from pathlib import Path
import json
import numpy as np
from audio import Engine
from audio.fileio import make_test_signal, write_wav
from .scenes import SCENES, SceneMorph


def render(scene, output):
    sr, block = 48000, 128
    source = make_test_signal(12, sr)
    rendered = np.zeros((len(source), 2), np.float32)
    audio = Engine()
    morph = SceneMorph(SCENES[scene])
    next_update = 0
    for start in range(0, len(source), block):
        seconds = start / sr
        if seconds >= next_update:
            # 3s original scene, 6s continuous morph, 3s destination.
            amount = min(1, max(0, (seconds - 3) / 6))
            for event in morph.events(dict(version=1, source='vision', seq=0,
                    timestamp_ms=int(seconds * 1000), type='parameter',
                    control='filter', value=amount, confidence=1.0)):
                if not audio.submit(event):
                    raise RuntimeError('audio engine rejected scene event')
            next_update = seconds + .1
        audio.process(source[start:start + block], rendered[start:start + block])
    if not np.isfinite(rendered).all():
        raise RuntimeError('nonfinite render')
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    write_wav(output, rendered, sr)
    report = dict(label='SYNTHETIC AUDIO AND SCRIPTED MORPH', scene=morph.name,
                  seconds=12, peak=float(np.max(np.abs(rendered))),
                  clipped_samples=audio.snapshot()['clipped_samples'], events=morph.seq)
    output.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--scene', choices=sorted(SCENES), default='bloom')
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(render(args.scene, args.output)))


if __name__ == '__main__':
    main()
