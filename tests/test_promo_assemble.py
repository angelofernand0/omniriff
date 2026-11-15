"""Tests for promo assembler: EDL validation, filter graph construction, missing asset reporting, and render."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.promo import (
    FPS,
    HEIGHT,
    WIDTH,
    assemble,
    build_ffmpeg_command,
    build_filter_graph,
    compile_plan,
    find_ffmpeg,
    load_edl,
    missing_assets,
)
from tools.promo.__main__ import main
from tools.promo.edl import asset_path


def tiny_edl():
    return {
        'version': 1,
        'width': 1920,
        'height': 1080,
        'fps': 30,
        'duration_s': 2.0,
        'project': 'Tiny Test EDL',
        'segments': [
            {
                'id': 'seg_1',
                'start_s': 0.0,
                'end_s': 1.0,
                'kind': 'motion',
                'scene': 'hook',
                'asset': 'raw/clip1.mp4',
                'source_start_s': 0.0,
            },
            {
                'id': 'seg_2',
                'start_s': 1.0,
                'end_s': 2.0,
                'kind': 'video',
                'scene': 'rig',
                'asset': 'raw/clip2.mp4',
                'source_start_s': 0.5,
            },
        ],
        'audio': [
            {
                'id': 'bed',
                'kind': 'music',
                'asset': 'audio/music.mp3',
                'start_s': 0.0,
                'duration_s': 2.0,
                'gain': 0.4,
                'ducked_gain': 0.15,
            },
            {
                'id': 'vo',
                'kind': 'voice',
                'asset': 'audio/voice.wav',
                'start_s': 0.5,
                'duration_s': 1.0,
                'gain': 1.0,
            },
        ],
        'captions': [
            {
                'start_s': 0.0,
                'end_s': 1.5,
                'text': 'Never put the guitar down.',
            }
        ],
    }


class TestPromoAssemble(unittest.TestCase):
    def test_edl_validation_happy_path(self):
        edl = tiny_edl()
        plan = compile_plan(edl)
        self.assertEqual(plan['version'], 1)
        self.assertEqual(plan['width'], 1920)
        self.assertEqual(plan['height'], 1080)
        self.assertEqual(plan['fps'], 30)
        self.assertEqual(plan['duration_s'], 2.0)
        self.assertEqual(plan['frames'], 60)
        self.assertEqual(len(plan['segments']), 2)
        self.assertEqual(len(plan['audio']), 2)
        self.assertEqual(len(plan['captions']), 1)

    def test_edl_validation_schema_errors(self):
        # Version error
        bad = tiny_edl()
        bad['version'] = 2
        with self.assertRaises(ValueError):
            compile_plan(bad)

        # Dimensions error
        bad = tiny_edl()
        bad['width'] = 1280
        with self.assertRaises(ValueError):
            compile_plan(bad)

        # FPS error
        bad = tiny_edl()
        bad['fps'] = 24
        with self.assertRaises(ValueError):
            compile_plan(bad)

        # Bad duration
        bad = tiny_edl()
        bad['duration_s'] = -1.0
        with self.assertRaises(ValueError):
            compile_plan(bad)

        bad = tiny_edl()
        bad['duration_s'] = float('nan')
        with self.assertRaises(ValueError):
            compile_plan(bad)

        # Overlapping segments
        bad = tiny_edl()
        bad['segments'][1]['start_s'] = 0.5
        with self.assertRaises(ValueError):
            compile_plan(bad)

        # Duplicate segment id
        bad = tiny_edl()
        bad['segments'][1]['id'] = 'seg_1'
        with self.assertRaises(ValueError):
            compile_plan(bad)

        # Invalid kind
        bad = tiny_edl()
        bad['segments'][0]['kind'] = 'unknown'
        with self.assertRaises(ValueError):
            compile_plan(bad)

        # Audio exceeds timeline duration
        bad = tiny_edl()
        bad['audio'][1]['start_s'] = 1.5
        bad['audio'][1]['duration_s'] = 1.0  # ends at 2.5 > 2.0
        with self.assertRaises(ValueError):
            compile_plan(bad)

        # Audio ducked_gain > gain
        bad = tiny_edl()
        bad['audio'][0]['gain'] = 0.5
        bad['audio'][0]['ducked_gain'] = 0.8
        with self.assertRaises(ValueError):
            compile_plan(bad)

        # Overlapping captions
        bad = tiny_edl()
        bad['captions'].append({
            'start_s': 1.0,
            'end_s': 2.0,
            'text': 'Overlap caption',
        })
        with self.assertRaises(ValueError):
            compile_plan(bad)

    def test_asset_path_security(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with self.assertRaises(ValueError):
                asset_path('../secret.txt', root)
            with self.assertRaises(ValueError):
                asset_path('/etc/passwd', root)
            with self.assertRaises(ValueError):
                asset_path('https://evil.com/video.mp4', root)
            with self.assertRaises(ValueError):
                asset_path('raw\\clip.mp4', root)

            valid = asset_path('runs/promo/scenes/hook.mp4', root)
            self.assertEqual(valid, (root / 'runs/promo/scenes/hook.mp4').resolve())

    def test_missing_asset_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = compile_plan(tiny_edl(), root)

            # Initially all assets are missing
            missing = missing_assets(plan, root)
            self.assertIn('raw/clip2.mp4', missing)
            self.assertIn('audio/music.mp3', missing)
            self.assertIn('audio/voice.wav', missing)

            # assemble should fail without dry_run
            with self.assertRaises(ValueError) as ctx:
                assemble(plan, assets_root=root, output_path=root / 'out.mp4', dry_run=False)
            self.assertIn('missing', str(ctx.exception).lower())
            self.assertIn('raw/clip2.mp4', str(ctx.exception))

            # Touch one asset and verify it drops from missing
            (root / 'raw').mkdir(parents=True)
            (root / 'raw/clip2.mp4').touch()
            missing_updated = missing_assets(plan, root)
            self.assertNotIn('raw/clip2.mp4', missing_updated)
            self.assertIn('audio/music.mp3', missing_updated)

    def test_generated_filter_graph_for_tiny_edl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            srt = root / 'captions.srt'
            srt.write_text('1\n00:00:00,000 --> 00:00:01,000\nHello\n', encoding='utf-8')

            plan = compile_plan(tiny_edl(), root)
            cmd, filter_graph, inputs = build_ffmpeg_command(
                plan, root, root / 'out.mp4', captions_path=srt
            )

            # Check single filter graph components
            self.assertIn('scale=1920:1080:force_original_aspect_ratio=decrease', filter_graph)
            self.assertIn('pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x0B0B10', filter_graph)
            self.assertIn('setsar=1', filter_graph)
            self.assertIn('fps=30', filter_graph)
            self.assertIn('concat=n=2:v=1:a=0', filter_graph)
            self.assertIn('subtitles=filename=', filter_graph)
            self.assertIn('asplit=2', filter_graph)
            self.assertIn('sidechaincompress=threshold=0.03:ratio=8', filter_graph)
            self.assertIn('adelay=500|500', filter_graph)
            self.assertIn('alimiter=limit=0.98', filter_graph)

            # Check command arguments
            cmd_str = ' '.join(cmd)
            self.assertIn('-c:v libx264', cmd_str)
            self.assertIn('-c:a aac', cmd_str)
            self.assertIn('-pix_fmt yuv420p', cmd_str)
            self.assertIn('-movflags +faststart', cmd_str)

    def test_dry_run_plan(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            edl_file = root / 'edl.json'
            edl_file.write_text(json.dumps(tiny_edl()), encoding='utf-8')

            result = assemble(edl_file, assets_root=root, output_path=root / 'test.mp4', dry_run=True)
            self.assertTrue(result['dry_run'])
            self.assertIn('command', result)
            self.assertIn('filter_graph', result)
            self.assertGreater(len(result['missing_assets']), 0)

    def test_cli_validate_and_assemble_dry_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            edl_file = root / 'edl.json'
            edl_file.write_text(json.dumps(tiny_edl()), encoding='utf-8')

            # Test validate subcommand
            code = main(['validate', str(edl_file), '--assets', str(root)])
            self.assertEqual(code, 0)

            # Test assemble subcommand with --dry-run
            code = main(['assemble', str(edl_file), '--assets', str(root), '--out', str(root / 'out.mp4'), '--dry-run'])
            self.assertEqual(code, 0)

    def test_real_render_if_ffmpeg_available(self):
        exe = find_ffmpeg()
        if not exe:
            self.skipTest('ffmpeg binary not found; skipping real encode test')

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw_dir = root / 'raw'
            audio_dir = root / 'audio'
            raw_dir.mkdir(parents=True)
            audio_dir.mkdir(parents=True)

            c1 = raw_dir / 'clip1.mp4'
            c2 = raw_dir / 'clip2.mp4'
            m1 = audio_dir / 'music.mp3'
            v1 = audio_dir / 'voice.wav'
            out_mp4 = root / 'rendered.mp4'

            # Generate synthetic 1s test media via ffmpeg
            res1 = subprocess.run([
                exe, '-y', '-f', 'lavfi', '-i', 'testsrc=duration=1:size=640x360:rate=30',
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(c1)
            ], capture_output=True)
            self.assertEqual(res1.returncode, 0)

            res2 = subprocess.run([
                exe, '-y', '-f', 'lavfi', '-i', 'testsrc=duration=1:size=640x360:rate=30',
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(c2)
            ], capture_output=True)
            self.assertEqual(res2.returncode, 0)

            res3 = subprocess.run([
                exe, '-y', '-f', 'lavfi', '-i', 'sine=frequency=220:duration=2',
                '-c:a', 'libmp3lame' if 'libmp3lame' in subprocess.run([exe, '-encoders'], capture_output=True, text=True).stdout else 'aac',
                str(m1)
            ], capture_output=True)
            self.assertEqual(res3.returncode, 0)

            res4 = subprocess.run([
                exe, '-y', '-f', 'lavfi', '-i', 'sine=frequency=880:duration=1',
                str(v1)
            ], capture_output=True)
            self.assertEqual(res4.returncode, 0)

            srt = root / 'captions.srt'
            srt.write_text('1\n00:00:00,000 --> 00:00:01,000\nTesting Render\n', encoding='utf-8')

            plan = compile_plan(tiny_edl(), root)
            result = assemble(
                plan,
                assets_root=root,
                output_path=out_mp4,
                captions_path=srt,
                dry_run=False,
            )

            self.assertFalse(result['dry_run'])
            self.assertTrue(out_mp4.is_file())
            self.assertGreater(out_mp4.stat().st_size, 1000)


if __name__ == '__main__':
    unittest.main()
