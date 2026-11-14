"""Performer Stage HUD for live visual performance feedback in the terminal."""
import os
import sys
import time
from typing import Optional


class StageHUD:
    """Renders a clean, low-overhead ASCII dashboard in the terminal for stage monitoring."""

    def __init__(self, refresh_hz: float = 10.0, enabled: bool = True):
        self.refresh_hz = refresh_hz
        self.enabled = enabled
        self.last_render: float = -float('inf')

    def render_bar(self, value: Optional[float], width: int = 24) -> str:
        if value is None:
            return '[' + '-' * width + ']   N/A'
        val = min(1.0, max(0.0, value))
        filled = int(val * width)
        empty = width - filled
        pct = int(val * 100)
        return f"[{'=' * filled}{' ' * empty}] {pct:>3d}%"

    def format_status(
        self,
        armed: bool,
        active: bool,
        zone_status: str,
        primary_name: str,
        primary_val: Optional[float],
        secondary_name: Optional[str] = None,
        secondary_val: Optional[float] = None,
        scene_name: Optional[str] = None,
        setlist_info: Optional[str] = None,
        vibrato_active: bool = False,
        take_info: Optional[str] = None,
        event_count: int = 0,
        fps: float = 0.0,
    ) -> str:
        lines = []
        lines.append("=" * 60)
        title = " OMNIRIFF // AIRGUITARIST PRO - STAGE HUD "
        lines.append(f"{title:^60}")
        lines.append("=" * 60)

        # Zone status
        if zone_status == 'strum_zone':
            z_str = "STRUM ZONE (PROTECTED - FX MUTED)"
        elif zone_status == 'strum_motion':
            z_str = "RAPID STRUMMING DETECTED (FX MUTED)"
        elif zone_status == 'expression_zone':
            z_str = "AIR EXPRESSION ZONE (LIVE)"
        else:
            z_str = "NO HAND DETECTED"
        lines.append(f"  Zone Status:   {z_str}")

        # Clutch status
        if active:
            clutch_str = "ENGAGED [CLUTCH LOCKED]"
        elif armed:
            clutch_str = "ARMED (PINCH TO ENGAGE)"
        else:
            clutch_str = "DISARMED (OPEN HAND TO ARM)"
        lines.append(f"  Clutch State:  {clutch_str}")

        # Scene / Setlist info
        if setlist_info:
            lines.append(f"  Performance:   {setlist_info}")
        elif scene_name:
            lines.append(f"  Active Scene:  {scene_name}")

        lines.append("-" * 60)

        # Primary control
        p_bar = self.render_bar(primary_val)
        lines.append(f"  {primary_name.capitalize():<12} {p_bar}")

        # Secondary control (if dual-axis)
        if secondary_name:
            s_bar = self.render_bar(secondary_val)
            lines.append(f"  {secondary_name.capitalize():<12} {s_bar}")

        if vibrato_active:
            lines.append("  Expression:    * SPATIAL VIBRATO ACTIVE *")

        if take_info:
            lines.append(f"  Take Logger:   REC {take_info}")

        lines.append("-" * 60)
        lines.append(f"  Stats: Events={event_count} | Cam FPS={fps:.1f} | Hotkeys: [1-9] Scene, [Q]uit")
        lines.append("=" * 60)

        return "\n".join(lines)

    def update(self, **kwargs) -> Optional[str]:
        now = time.monotonic()
        if not self.enabled or (now - self.last_render < (1.0 / self.refresh_hz)):
            return None
        self.last_render = now
        text = self.format_status(**kwargs)
        return text
