"""Promo video assembler: validates EDL v1, builds single ffmpeg filter graph, and encodes or dry-runs."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

from .edl import (
    FPS,
    HEIGHT,
    WIDTH,
    compile_plan,
    load_edl,
    missing_assets,
    resolve_segment_asset,
)


def find_ffmpeg():
    """Locate ffmpeg binary on PATH or through imageio-ffmpeg or standard local directories."""
    # 1. PATH lookup
    path_bin = shutil.which('ffmpeg') or shutil.which('ffmpeg.exe')
    if path_bin:
        return str(Path(path_bin).resolve())

    # 2. imageio-ffmpeg
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).is_file():
            return str(Path(exe).resolve())
    except (ImportError, Exception):
        pass

    # 3. Common macOS / Linux installation locations
    common_locations = [
        '/opt/homebrew/bin/ffmpeg',
        '/usr/local/bin/ffmpeg',
        Path.home() / '.local/bin/ffmpeg',
    ]
    for loc in common_locations:
        p = Path(loc)
        if p.is_file() and os.access(p, os.X_OK):
            return str(p.resolve())

    return None


def escape_filter_path(path):
    """Escape file path for inclusion inside ffmpeg filter graph strings."""
    s = str(Path(path).resolve().as_posix())
    # In ffmpeg filter arguments: escape colons, backslashes, single quotes, and brackets
    s = s.replace('\\', '/')
    s = s.replace("'", "'\\''")
    s = s.replace(':', '\\:')
    s = s.replace('[', '\\[')
    s = s.replace(']', '\\]')
    return s


def build_filter_graph(plan, assets_root, captions_path=None, allow_fallbacks=False):
    """Build a single unified ffmpeg filter graph for video concatenation, captions, and audio ducking."""
    root = Path(assets_root).resolve()
    inputs = []
    filter_chains = []

    # 1. Process Video Segments
    v_clip_labels = []
    cursor_s = 0.0
    gap_counter = 0

    for idx, seg in enumerate(plan['segments']):
        seg_start = seg['start_s']
        seg_end = seg['end_s']
        seg_dur = seg_end - seg_start

        # Check for gap before this segment
        if seg_start > cursor_s + (0.5 / FPS):
            gap_dur = seg_start - cursor_s
            gap_label = f'v_gap_{gap_counter}'
            gap_counter += 1
            filter_chains.append(
                f'color=c=0x0B0B10:s={WIDTH}x{HEIGHT}:d={gap_dur:.4f}:r={FPS}[{gap_label}]'
            )
            v_clip_labels.append(f'[{gap_label}]')

        # Resolve asset
        resolved = resolve_segment_asset(seg, root, allow_fallbacks=allow_fallbacks)
        if resolved is None:
            # Placeholder reference for dry-run or mock
            asset_ref = seg.get('asset') or f"runs/promo/scenes/{seg.get('scene', seg['id'])}.mp4"
            resolved = (root / asset_ref).resolve()

        in_idx = len(inputs)
        inputs.append(str(resolved))

        v_seg_label = f'v_seg_{idx}'
        source_start = seg.get('source_start_s', 0.0)
        filter_chains.append(
            f'[{in_idx}:v]trim=start={source_start:.4f}:duration={seg_dur:.4f},'
            f'setpts=PTS-STARTPTS,fps={FPS},'
            f'scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,'
            f'pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=0x0B0B10,setsar=1[{v_seg_label}]'
        )
        v_clip_labels.append(f'[{v_seg_label}]')
        cursor_s = seg_end

    # Check for tail gap
    if cursor_s < plan['duration_s'] - (0.5 / FPS):
        gap_dur = plan['duration_s'] - cursor_s
        gap_label = f'v_gap_end'
        filter_chains.append(
            f'color=c=0x0B0B10:s={WIDTH}x{HEIGHT}:d={gap_dur:.4f}:r={FPS}[{gap_label}]'
        )
        v_clip_labels.append(f'[{gap_label}]')

    # Video concatenation
    concat_label = 'v_concat'
    filter_chains.append(
        f"{''.join(v_clip_labels)}concat=n={len(v_clip_labels)}:v=1:a=0[{concat_label}]"
    )

    # Subtitles / Captions burn-in
    if captions_path and Path(captions_path).is_file():
        esc_srt = escape_filter_path(captions_path)
        filter_chains.append(
            f"[{concat_label}]subtitles=filename='{esc_srt}':"
            f"force_style='FontSize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H80000000,BorderStyle=3,Outline=2,MarginV=48'[v_out]"
        )
        v_final_label = '[v_out]'
    else:
        v_final_label = f'[{concat_label}]'

    # 2. Process Audio Tracks
    audio_tracks = plan.get('audio', [])
    voice_labels = []
    music_labels = []
    sfx_labels = []

    for a_idx, aud in enumerate(audio_tracks):
        asset = aud.get('asset')
        p = (root / asset).resolve() if asset else None
        if p is None or not p.is_file():
            p = (root / (asset or f'audio_{a_idx}.wav')).resolve()

        in_idx = len(inputs)
        inputs.append(str(p))

        raw_a_label = f'a_raw_{a_idx}'
        start_s = aud.get('start_s', 0.0)
        dur_s = aud.get('duration_s', 1.0)
        src_start = aud.get('source_start_s', 0.0)
        gain = aud.get('gain', 1.0)
        delay_ms = int(round(start_s * 1000.0))

        filter_chains.append(
            f'[{in_idx}:a]atrim=start={src_start:.4f}:duration={dur_s:.4f},'
            f'asetpts=PTS-STARTPTS,volume={gain:.4f},'
            f'aformat=channel_layouts=stereo:sample_rates=48000,'
            f'adelay={delay_ms}|{delay_ms}[{raw_a_label}]'
        )

        kind = aud.get('kind', 'audio')
        if kind == 'voice':
            voice_labels.append(f'[{raw_a_label}]')
        elif kind == 'music':
            music_labels.append(f'[{raw_a_label}]')
        else:
            sfx_labels.append(f'[{raw_a_label}]')

    # Group Voice
    if len(voice_labels) > 1:
        filter_chains.append(
            f"{''.join(voice_labels)}amix=inputs={len(voice_labels)}:normalize=0:dropout_transition=0[all_voice]"
        )
        voice_group = '[all_voice]'
    elif len(voice_labels) == 1:
        voice_group = voice_labels[0]
    else:
        voice_group = None

    # Group Music
    if len(music_labels) > 1:
        filter_chains.append(
            f"{''.join(music_labels)}amix=inputs={len(music_labels)}:normalize=0:dropout_transition=0[all_music]"
        )
        music_group = '[all_music]'
    elif len(music_labels) == 1:
        music_group = music_labels[0]
    else:
        music_group = None

    # Group SFX / other audio
    if len(sfx_labels) > 1:
        filter_chains.append(
            f"{''.join(sfx_labels)}amix=inputs={len(sfx_labels)}:normalize=0:dropout_transition=0[all_sfx]"
        )
        sfx_group = '[all_sfx]'
    elif len(sfx_labels) == 1:
        sfx_group = sfx_labels[0]
    else:
        sfx_group = None

    # Audio Mixing and Voice Ducking
    final_mix_components = []
    if music_group and voice_group:
        # Split voice for mix and sidechain ducking
        filter_chains.append(
            f'{voice_group}asplit=2[voice_for_mix][voice_for_ducking]'
        )
        # Duck music ~-12dB using sidechain compression (ratio=8, threshold=0.03, makeup=1)
        filter_chains.append(
            f'{music_group}[voice_for_ducking]sidechaincompress=threshold=0.03:ratio=8:attack=50:release=300:makeup=1[ducked_music]'
        )
        final_mix_components.append('[ducked_music]')
        final_mix_components.append('[voice_for_mix]')
    elif music_group:
        final_mix_components.append(music_group)
    elif voice_group:
        final_mix_components.append(voice_group)

    if sfx_group:
        final_mix_components.append(sfx_group)

    if len(final_mix_components) > 1:
        filter_chains.append(
            f"{''.join(final_mix_components)}amix=inputs={len(final_mix_components)}:normalize=0:dropout_transition=0,"
            f'alimiter=limit=0.98[a_out]'
        )
        a_final_label = '[a_out]'
    elif len(final_mix_components) == 1:
        filter_chains.append(
            f'{final_mix_components[0]}alimiter=limit=0.98[a_out]'
        )
        a_final_label = '[a_out]'
    else:
        # Silence generator
        filter_chains.append(
            f'aevalsrc=0:d={plan["duration_s"]:.4f}:s=48000:c=stereo[a_out]'
        )
        a_final_label = '[a_out]'

    filter_graph = ';'.join(filter_chains)
    return inputs, filter_graph, v_final_label, a_final_label


def build_ffmpeg_command(plan, assets_root, output_path, captions_path=None, ffmpeg_bin=None, allow_fallbacks=False):
    """Construct the exact ffmpeg command array for assembling the promo video."""
    exe = ffmpeg_bin or find_ffmpeg() or 'ffmpeg'
    inputs, filter_graph, v_label, a_label = build_filter_graph(
        plan, assets_root, captions_path=captions_path, allow_fallbacks=allow_fallbacks
    )

    cmd = [exe, '-y', '-hide_banner', '-loglevel', 'info']
    for inp in inputs:
        cmd.extend(['-i', str(inp)])

    cmd.extend([
        '-filter_complex', filter_graph,
        '-map', v_label,
        '-map', a_label,
        '-t', f"{plan['duration_s']:.4f}",
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-crf', '19',
        '-pix_fmt', 'yuv420p',
        '-c:a', 'aac',
        '-b:a', '192k',
        '-ar', '48000',
        '-movflags', '+faststart',
        str(Path(output_path).resolve())
    ])

    return cmd, filter_graph, inputs


def assemble(edl_or_plan, assets_root='.', output_path='runs/promo/omniriff.mp4',
             captions_path=None, dry_run=False, allow_fallbacks=False, ffmpeg_bin=None):
    """Validate EDL v1, resolve assets, build filter graph, and run or dry-run assembly."""
    root = Path(assets_root).resolve()
    out = Path(output_path).resolve()

    if isinstance(edl_or_plan, dict):
        plan = compile_plan(edl_or_plan, root)
    else:
        plan = load_edl(edl_or_plan, root)

    # Check for missing assets
    missing = missing_assets(plan, root, allow_fallbacks=allow_fallbacks)

    # Auto-detect captions file if not specified
    if captions_path is None:
        candidate_srt = root / 'docs/video/captions.srt'
        if candidate_srt.is_file():
            captions_path = candidate_srt
        elif isinstance(edl_or_plan, (str, Path)):
            adj_srt = Path(edl_or_plan).parent / 'captions.srt'
            if adj_srt.is_file():
                captions_path = adj_srt

    # Build command and filter graph
    cmd, filter_graph, input_paths = build_ffmpeg_command(
        plan, root, out, captions_path=captions_path, ffmpeg_bin=ffmpeg_bin, allow_fallbacks=allow_fallbacks
    )

    cmd_str = ' '.join(shlex.quote(arg) for arg in cmd)

    if dry_run:
        print('=== OmniRiff Promo Assembly Plan (DRY RUN) ===')
        print(f"Project:    {plan.get('project', 'OmniRiff Video Promo')}")
        print(f"Format:     {plan['width']}x{plan['height']} @ {plan['fps']} fps, {plan['duration_s']}s ({plan['frames']} frames)")
        print(f"Output:     {out}")
        print(f"Assets Root:{root}")
        print(f"Captions:   {captions_path or 'None (skipped)'}")
        print(f"\n--- Segments ({len(plan['segments'])}) ---")
        for s in plan['segments']:
            resolved = resolve_segment_asset(s, root, allow_fallbacks=allow_fallbacks)
            disp_asset = s.get('asset') or (f"runs/promo/scenes/{s['scene']}.mp4" if s.get('scene') else None)
            status_tag = " [PRESENT]" if (resolved and resolved.is_file()) else " [MISSING]"
            print(f"  [{s['start_s']:5.1f}s - {s['end_s']:5.1f}s] {s['id']:<20} ({s['kind']}) scene={s.get('scene')} asset={disp_asset}{status_tag}")
        print(f"\n--- Audio Tracks ({len(plan['audio'])}) ---")
        for a in plan['audio']:
            duck_info = f", duck={a['ducked_gain']}" if a.get('ducked_gain') is not None else ""
            print(f"  [{a['start_s']:5.1f}s + {a['duration_s']:4.1f}s] {a['id']:<18} ({a['kind']}) gain={a.get('gain')}{duck_info} asset={a.get('asset')}")
        print(f"\n--- Missing Assets ({len(missing)}) ---")
        if missing:
            for m in missing:
                print(f"  MISSING: {m}")
        else:
            print("  ALL ASSETS PRESENT!")

        print('\n--- Exact FFmpeg Command ---')
        print(cmd_str)
        print('=============================================')
        return {
            'plan': plan,
            'command': cmd,
            'command_str': cmd_str,
            'filter_graph': filter_graph,
            'missing_assets': missing,
            'dry_run': True,
        }

    # Non dry-run execution
    if missing:
        msg = f"Cannot assemble promo: missing {len(missing)} required recorded assets:\n"
        msg += '\n'.join(f"  - {m}" for m in missing)
        raise ValueError(msg)

    exe = find_ffmpeg() if ffmpeg_bin is None else ffmpeg_bin
    if not exe:
        raise RuntimeError('ffmpeg executable not found on PATH or via imageio-ffmpeg. Cannot encode media.')

    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"Executing promo assembly ({plan['duration_s']:.1f}s, {plan['width']}x{plan['height']}@30fps)...")
    print(f"FFmpeg command:\n{cmd_str}\n")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        err = result.stderr[-1500:] if result.stderr else 'unknown error'
        raise RuntimeError(f"FFmpeg assembly failed with return code {result.returncode}:\n{err}")

    if not out.is_file() or out.stat().st_size == 0:
        raise RuntimeError(f"Output file was not created or is empty: {out}")

    print(f"Successfully assembled promo video: {out} ({out.stat().st_size} bytes)")
    return {
        'plan': plan,
        'command': cmd,
        'command_str': cmd_str,
        'output_path': str(out),
        'bytes': out.stat().st_size,
        'dry_run': False,
    }
