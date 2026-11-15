"""Before-each-judge readiness: local connections and paths, no rig controls."""
import argparse
import asyncio
from pathlib import Path
import time

from . import check


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name, default in [('engine', 47801), ('dashboard', 8080), ('hand', 47802), ('coach', 47803)]:
        parser.add_argument('--' + name + '-port', type=int, default=default)
    parser.add_argument('--take-dir', type=Path, default=Path('runs/takes'))
    parser.add_argument('--model', type=Path, default=Path('models/hand_landmarker.task'))
    parser.add_argument('--timeout', type=float, default=1.5, help='per-check concurrent deadline, 0.1..3 seconds')
    parser.add_argument('--no-vision', action='store_true', help='skip hand feed and model checks')
    parser.add_argument('--no-coach', action='store_true', help='skip coach feed check')
    args = parser.parse_args(argv)
    started = time.monotonic()
    try:
        results = asyncio.run(check(**vars(args)))
    except ValueError as exc:
        parser.error(str(exc))
    for result in results:
        print(f'{"GREEN" if result.green else "RED"} {result.name}: {result.detail}')
    if args.no_vision:
        print('SKIPPED vision: hand feed and model (--no-vision)')
    if args.no_coach:
        print('SKIPPED coach (--no-coach)')
    print(f'Checked in {time.monotonic() - started:.2f}s; no controls sent. GREEN is not an audible/hardware qualification.')
    return 0 if all(result.green for result in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
