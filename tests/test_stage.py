"""Tests for StageHUD rendering and stage formatting."""
import unittest
from vision.stage import StageHUD


class StageHUDTests(unittest.TestCase):
    def test_render_bar_limits(self):
        hud = StageHUD()
        self.assertIn('0%', hud.render_bar(0.0))
        self.assertIn('100%', hud.render_bar(1.0))
        self.assertIn('50%', hud.render_bar(0.5))
        self.assertIn('N/A', hud.render_bar(None))
        # Clamps out of bounds safely
        self.assertIn('100%', hud.render_bar(1.5))
        self.assertIn('0%', hud.render_bar(-0.5))

    def test_format_status_contains_key_elements(self):
        hud = StageHUD()
        text = hud.format_status(
            armed=True,
            active=False,
            zone_status='expression_zone',
            primary_name='filter',
            primary_val=0.75,
            secondary_name='reverb',
            secondary_val=0.30,
            scene_name='Bloom',
            setlist_info='Scene 1/3: Bloom',
            vibrato_active=True,
            take_info='take_001.jsonl (15 events)',
            event_count=42,
            fps=30.0,
        )
        self.assertIn('OMNIRIFF // AIRGUITARIST PRO', text)
        self.assertIn('AIR EXPRESSION ZONE', text)
        self.assertIn('ARMED', text)
        self.assertIn('Filter', text)
        self.assertIn('Reverb', text)
        self.assertIn('SPATIAL VIBRATO ACTIVE', text)
        self.assertIn('Scene 1/3: Bloom', text)
        self.assertIn('take_001.jsonl', text)
        self.assertIn('Events=42', text)

    def test_strum_zone_warning_rendered(self):
        hud = StageHUD()
        text = hud.format_status(
            armed=False,
            active=False,
            zone_status='strum_zone',
            primary_name='filter',
            primary_val=None,
        )
        self.assertIn('STRUM ZONE (PROTECTED - FX MUTED)', text)

    def test_rate_limiting(self):
        hud = StageHUD(refresh_hz=2.0)
        # First call updates
        out1 = hud.update(armed=False, active=False, zone_status='no_hand', primary_name='filter', primary_val=0.5)
        self.assertIsNotNone(out1)
        # Immediate next call should be rate-limited and return None
        out2 = hud.update(armed=False, active=False, zone_status='no_hand', primary_name='filter', primary_val=0.5)
        self.assertIsNone(out2)
