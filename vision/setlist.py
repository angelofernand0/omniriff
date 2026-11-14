"""Prevalidated scene selection with one continuous output sequence."""
from .scenes import SceneMorph


class Setlist:
    def __init__(self, data):
        if not isinstance(data, dict) or set(data) != {'scenes'}:
            raise ValueError('setlist requires a scenes array')
        scenes = data['scenes']
        if not isinstance(scenes, list) or not 1 <= len(scenes) <= 9:
            raise ValueError('setlist must contain 1..9 scenes')
        self.scenes = [SceneMorph(scene) for scene in scenes]
        self.index = 0

    @property
    def current(self):
        return self.scenes[self.index]

    def select(self, index):
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(self.scenes):
            raise ValueError('scene index is outside the setlist')
        if index == self.index:
            return False
        sequence = self.current.seq
        self.index = index
        self.current.seq = sequence
        return True

    def key(self, key):
        """Return whether selection changed; unknown/unavailable keys do nothing."""
        if key == ord('n'):
            return self.select((self.index + 1) % len(self.scenes))
        if key == ord('p'):
            return self.select((self.index - 1) % len(self.scenes))
        if ord('1') <= key < ord('1') + len(self.scenes):
            return self.select(key - ord('1'))
        return False


def main(argv=None):
    """Build a setlist in positional order without importing camera packages."""
    import argparse
    import json
    from pathlib import Path
    from .scenes import SCENES

    parser = argparse.ArgumentParser(description='Combine preset names and scene JSON files into a performance setlist.')
    parser.add_argument('scenes', nargs='+', help='bloom, rise, or a scene JSON path, in performance order')
    parser.add_argument('--output', required=True, type=Path, help='new JSON file; refuses overwrite')
    args = parser.parse_args(argv)
    try:
        if not 1 <= len(args.scenes) <= 9:
            raise ValueError('choose 1..9 scenes')
        data = {'scenes': [SCENES[item] if item in SCENES else json.loads(Path(item).read_text()) for item in args.scenes]}
        bank = Setlist(data)
        with args.output.open('x', encoding='utf-8') as file:
            file.write(json.dumps(data, indent=2) + '\n')
        for i, scene in enumerate(bank.scenes, 1):
            print(f'{i}: {scene.name}')
        print(f'Saved {args.output}')
    except (ValueError, OSError) as exc:
        parser.exit(2, f'setlist: {exc}\n')


if __name__ == '__main__':
    main()
