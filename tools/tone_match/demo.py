"""Make a reproducible synthetic Tone Match demo with no guitar or camera."""
import argparse
import json
from pathlib import Path

from audio.fileio import write_wav
from tools.virtual_guitar.guitar import performance
from .match import effect
from .__main__ import main as match_main


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='new folder')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output already exists; choose a new folder')
    args.output.mkdir(parents=True)
    rate = 24000
    dry = performance(6, rate, seed=23)
    # These settings make the target, but are NOT passed to the optimizer.
    reference = effect(dry, rate, .31, .68)
    write_wav(args.output/'dry-synthetic.wav', dry, rate)
    write_wav(args.output/'target-synthetic.wav', reference, rate)
    (args.output/'provenance.json').write_text(json.dumps(dict(
        source='OmniRiff deterministic Karplus-Strong guitar synthesis; not a recording',
        seed=23, target_filter=.31, target_reverb=.68,
        purpose='closed-model demonstration, not proof of real-recording matching'), indent=2)+'\n')
    match_main(['--dry', str(args.output/'dry-synthetic.wav'),
                '--reference', str(args.output/'target-synthetic.wav'),
                '--output', str(args.output/'match'), '--name', 'Synthetic guitar · Velvet Space',
                '--seconds', '3', '--evaluations', '96'])
    print(f"Open {args.output/'match'/'index.html'} to audition the result.")


if __name__ == '__main__':
    main()
