"""Command-line interface for OmniRiff promo video assembler."""
import argparse
from pathlib import Path
import sys

from .assemble import assemble
from .edl import FPS, HEIGHT, WIDTH, load_edl, missing_assets


def create_parser():
    parser = argparse.ArgumentParser(
        prog='python -m tools.promo',
        description='OmniRiff promo video tool: validates EDL v1 and builds single-graph ffmpeg assembly.'
    )
    subparsers = parser.add_subparsers(dest='command', help='Sub-commands')

    # assemble subcommand
    assemble_parser = subparsers.add_parser(
        'assemble',
        help='Assemble promo video from EDL v1 and asset files using ffmpeg.'
    )
    assemble_parser.add_argument(
        'edl',
        type=Path,
        help='Path to EDL v1 JSON file (e.g. docs/video/edl.json)'
    )
    assemble_parser.add_argument(
        '--assets',
        '--assets-root',
        dest='assets_root',
        type=Path,
        default=Path('.'),
        help='Root directory for recorded video/audio assets (default: current directory)'
    )
    assemble_parser.add_argument(
        '--out',
        '--output',
        dest='out',
        type=Path,
        default=Path('runs/promo/omniriff.mp4'),
        help='Output MP4 video path (default: runs/promo/omniriff.mp4)'
    )
    assemble_parser.add_argument(
        '--captions',
        type=Path,
        default=None,
        help='Path to SRT captions file (default: docs/video/captions.srt or adjacent to EDL)'
    )
    assemble_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Validate and print assembly plan, missing assets, and exact ffmpeg command without running ffmpeg'
    )
    assemble_parser.add_argument(
        '--allow-fallbacks',
        action='store_true',
        help='Allow fallback assets defined in EDL when primary recorded assets are missing'
    )

    # validate subcommand
    validate_parser = subparsers.add_parser(
        'validate',
        help='Check timing, schema, and asset existence without encoding.'
    )
    validate_parser.add_argument(
        'edl',
        type=Path,
        help='Path to EDL v1 JSON file'
    )
    validate_parser.add_argument(
        '--assets',
        '--assets-root',
        dest='assets_root',
        type=Path,
        default=Path('.'),
        help='Root directory for recorded assets'
    )
    validate_parser.add_argument(
        '--check-assets',
        action='store_true',
        help='Check and list any missing assets'
    )
    validate_parser.add_argument(
        '--allow-fallbacks',
        action='store_true',
        help='Allow fallback assets'
    )

    return parser


def main(argv=None):
    parser = create_parser()

    # If invoked directly with edl path without subcommand, default to assemble
    raw_args = list(argv if argv is not None else sys.argv[1:])
    if raw_args and not raw_args[0].startswith('-') and raw_args[0] not in ('assemble', 'validate', '-h', '--help'):
        raw_args.insert(0, 'assemble')

    args = parser.parse_args(raw_args)

    if not args.command:
        parser.print_help()
        return 2

    try:
        if args.command == 'validate':
            plan = load_edl(args.edl, args.assets_root)
            missing = missing_assets(plan, args.assets_root, allow_fallbacks=args.allow_fallbacks)
            print(f"VALID EDL v1: {plan['duration_s']:.1f}s ({plan['frames']} frames), {plan['width']}x{plan['height']}@{plan['fps']}fps")
            print(f"  Segments: {len(plan['segments'])}, Audio: {len(plan['audio'])}, Captions: {len(plan['captions'])}")
            if args.check_assets:
                if missing:
                    print(f"\nMissing assets ({len(missing)}):")
                    for m in missing:
                        print(f"  - {m}")
                    return 1
                else:
                    print("  All assets present on disk.")
            return 0

        elif args.command == 'assemble':
            assemble(
                edl_or_plan=args.edl,
                assets_root=args.assets_root,
                output_path=args.out,
                captions_path=args.captions,
                dry_run=args.dry_run,
                allow_fallbacks=args.allow_fallbacks,
            )
            return 0

    except Exception as exc:
        print(f"tools.promo error: {exc}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
