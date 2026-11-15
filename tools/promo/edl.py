"""Version-one Edit Decision List (EDL) compiler and validation for OmniRiff promo."""
import json
import math
from pathlib import Path

FPS = 30
WIDTH = 1920
HEIGHT = 1080
SCENES = (
    'hook',
    'collage',
    'logo',
    'rig',
    'goal',
    'diagnosis',
    'approval',
    'result',
    'memory',
    'failsafe',
    'architecture',
    'end',
)
MAX_JSON_BYTES = 1024 * 1024


def number(value, name, low=0.0, high=3600.0):
    """Validate that value is a finite number in [low, high]."""
    if type(value) is bool:
        raise ValueError(f'{name} must be a number, not a boolean')
    try:
        valid = type(value) in (int, float) and math.isfinite(value) and low <= value <= high
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f'{name} must be finite number in [{low}, {high}], got {value!r}')
    return float(value)


def frame(value, name):
    """Convert seconds to an integer frame count and verify 30 fps grid alignment."""
    result = number(value, name) * FPS
    rounded = round(result)
    if abs(result - rounded) > 1e-4:
        raise ValueError(f'{name} must align to the {FPS} fps frame grid: {value}s')
    return rounded


def asset_path(value, root=None):
    """Validate that asset path is relative, safe, and beneath root if specified."""
    if not isinstance(value, str) or not value.strip() or '\x00' in value or '://' in value:
        raise ValueError('asset must be a non-empty relative path string')
    if '\\' in value:
        raise ValueError('asset paths must use forward slashes')
    path = Path(value)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('asset must be a relative path and cannot contain ".."')
    if root is not None:
        root_path = Path(root).resolve()
        resolved = (root_path / path).resolve()
        if root_path != resolved and root_path not in resolved.parents:
            raise ValueError(f'asset {value} escapes assets root {root}')
        return resolved
    return path


def interval(item, duration, kind):
    """Validate start_s and end_s interval."""
    start = number(item.get('start_s'), f'{kind} start_s', low=0.0, high=duration)
    end = number(item.get('end_s'), f'{kind} end_s', low=0.0, high=duration)
    if start >= end:
        raise ValueError(f'{kind} start_s ({start}) must be strictly less than end_s ({end})')
    if end > duration + 1e-5:
        raise ValueError(f'{kind} end_s ({end}) cannot exceed timeline duration ({duration})')
    return frame(start, f'{kind} start_s'), frame(end, f'{kind} end_s')


def ordered(items, kind):
    """Sort items by start frame and ensure non-overlapping intervals."""
    items.sort(key=lambda item: item['start_f'])
    for a, b in zip(items, items[1:]):
        if a['end_f'] > b['start_f']:
            raise ValueError(f'{kind} intervals overlap: {a.get("id", "item")} ends at frame {a["end_f"]} but next starts at {b["start_f"]}')
    return items


def compile_plan(edl, assets_root=None):
    """Validate and compile raw EDL v1 dict into normalized timeline plan."""
    if not isinstance(edl, dict):
        raise ValueError('EDL root must be a JSON object')
    if type(edl.get('version')) is not int or edl['version'] != 1:
        raise ValueError('EDL version must be integer 1')
    if type(edl.get('width')) is not int or edl['width'] != WIDTH:
        raise ValueError(f'EDL width must be {WIDTH}')
    if type(edl.get('height')) is not int or edl['height'] != HEIGHT:
        raise ValueError(f'EDL height must be {HEIGHT}')
    if type(edl.get('fps')) is not int or edl['fps'] != FPS:
        raise ValueError(f'EDL fps must be {FPS}')

    duration = number(edl.get('duration_s'), 'duration_s', low=1.0 / FPS, high=3600.0)
    total_frames = frame(duration, 'duration_s')

    for key, maximum in [('segments', 128), ('audio', 256), ('captions', 512)]:
        if key in edl and (not isinstance(edl[key], list) or len(edl[key]) > maximum):
            raise ValueError(f'{key} must be an array with at most {maximum} entries')

    raw_segments = edl.get('segments', [])
    if not isinstance(raw_segments, list) or not raw_segments:
        raise ValueError('EDL must contain at least one segment')

    segments = []
    identities = set()
    for raw in raw_segments:
        if not isinstance(raw, dict):
            raise ValueError('Segment must be an object')
        ident = raw.get('id')
        if not isinstance(ident, str) or not ident.strip() or len(ident) > 80:
            raise ValueError('Segment id must be a non-empty string up to 80 chars')
        if ident in identities:
            raise ValueError(f'Duplicate segment id: {ident}')
        identities.add(ident)

        start_f, end_f = interval(raw, duration, f'Segment {ident}')
        kind = raw.get('kind')
        if kind not in ('motion', 'video'):
            raise ValueError(f'Segment {ident} kind must be "motion" or "video", got {kind!r}')

        scene = raw.get('scene')
        if scene is not None and (not isinstance(scene, str) or len(scene) > 80):
            raise ValueError(f'Segment {ident} scene must be a string up to 80 chars')
        if kind == 'motion':
            if not scene and not raw.get('asset'):
                raise ValueError(f'Segment {ident} of kind "motion" requires a scene or asset')
            if scene is not None and scene not in SCENES:
                raise ValueError(f'Segment {ident} motion scene {scene!r} not in approved scenes: {SCENES}')
        elif kind == 'video' and not raw.get('asset'):
            raise ValueError(f'Segment {ident} of kind "video" requires an asset')

        asset = raw.get('asset')
        if asset is not None:
            asset_path(asset, assets_root)
        fallback = raw.get('fallback_asset')
        if fallback is not None:
            asset_path(fallback, assets_root)

        source_start = number(raw.get('source_start_s', 0.0), f'Segment {ident} source_start_s', low=0.0, high=3600.0)

        segments.append({
            'id': ident,
            'start_f': start_f,
            'end_f': end_f,
            'start_s': start_f / FPS,
            'end_s': end_f / FPS,
            'duration_s': (end_f - start_f) / FPS,
            'kind': kind,
            'scene': scene,
            'asset': asset,
            'fallback_asset': fallback,
            'source_start_s': source_start,
            'beat': raw.get('beat'),
            'shot_number': raw.get('shot_number'),
            'description': raw.get('description'),
        })

    ordered(segments, 'segment')

    raw_audio = edl.get('audio', [])
    audio = []
    for idx, raw in enumerate(raw_audio):
        if not isinstance(raw, dict):
            raise ValueError(f'Audio track {idx} must be an object')
        ident = raw.get('id', f'audio_{idx}')
        kind = raw.get('kind', 'audio')
        if kind not in ('audio', 'voice', 'music', 'sfx'):
            raise ValueError(f'Audio track {ident} kind must be audio/voice/music/sfx, got {kind!r}')

        asset = raw.get('asset')
        if not asset:
            raise ValueError(f'Audio track {ident} missing required asset')
        asset_path(asset, assets_root)

        start_s = number(raw.get('start_s'), f'Audio track {ident} start_s', low=0.0, high=duration)
        duration_s = number(raw.get('duration_s'), f'Audio track {ident} duration_s', low=1.0 / 48000.0, high=duration)
        if start_s + duration_s > duration + 1e-4:
            raise ValueError(f'Audio track {ident} (end={start_s + duration_s:.3f}s) exceeds timeline duration ({duration}s)')

        source_start = number(raw.get('source_start_s', 0.0), f'Audio track {ident} source_start_s', low=0.0, high=3600.0)
        gain = number(raw.get('gain', 1.0), f'Audio track {ident} gain', low=0.0, high=10.0)

        raw_duck = raw.get('ducked_gain')
        if raw_duck is not None:
            ducked_gain = number(raw_duck, f'Audio track {ident} ducked_gain', low=0.0, high=gain)
        else:
            ducked_gain = None

        audio.append({
            'id': ident,
            'kind': kind,
            'asset': asset,
            'start_s': start_s,
            'duration_s': duration_s,
            'source_start_s': source_start,
            'gain': gain,
            'ducked_gain': ducked_gain,
            'speaker': raw.get('speaker'),
            'line': raw.get('line'),
        })

    raw_captions = edl.get('captions', [])
    captions = []
    for idx, raw in enumerate(raw_captions):
        if not isinstance(raw, dict):
            raise ValueError(f'Caption {idx} must be an object')
        start_f, end_f = interval(raw, duration, f'Caption {idx}')
        text = raw.get('text')
        if not isinstance(text, str) or not text.strip() or len(text) > 1024:
            raise ValueError(f'Caption {idx} text must be non-empty string up to 1024 chars')
        captions.append({
            'start_f': start_f,
            'end_f': end_f,
            'start_s': start_f / FPS,
            'end_s': end_f / FPS,
            'text': text,
            'speaker': raw.get('speaker'),
        })

    ordered(captions, 'caption')

    return {
        'version': 1,
        'width': WIDTH,
        'height': HEIGHT,
        'fps': FPS,
        'duration_s': duration,
        'frames': total_frames,
        'project': edl.get('project', 'OmniRiff Video Promo'),
        'brand_palette': edl.get('brand_palette', {}),
        'segments': segments,
        'audio': audio,
        'captions': captions,
    }


def load_edl(path, assets_root=None):
    """Load EDL JSON file with strict size bounds and compile."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f'EDL file not found: {p}')
    if p.stat().st_size > MAX_JSON_BYTES:
        raise ValueError(f'EDL file size exceeds {MAX_JSON_BYTES} bytes')
    try:
        content = json.loads(p.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        raise ValueError(f'Invalid JSON in EDL file {p}: {exc}') from exc
    return compile_plan(content, assets_root)


def resolve_segment_asset(segment, assets_root, allow_fallbacks=False):
    """Resolve the file path for a segment or return None if missing."""
    root = Path(assets_root).resolve()
    if segment['kind'] == 'motion':
        candidates = []
        if segment.get('scene'):
            candidates.append(f"runs/promo/scenes/{segment['scene']}.mp4")
        if segment.get('asset'):
            candidates.append(segment['asset'])
        for c in candidates:
            target = (root / c).resolve()
            if target.is_file():
                return target
        return None

    # kind == 'video'
    if segment.get('asset'):
        target = (root / segment['asset']).resolve()
        if target.is_file():
            return target
    if allow_fallbacks and segment.get('fallback_asset'):
        target = (root / segment['fallback_asset']).resolve()
        if target.is_file():
            return target
    return None


def resolve_audio_asset(audio_track, assets_root):
    """Resolve the file path for an audio track or return None if missing.
    Accepts either .m4a or .mp3 transparently (e.g. ElevenLabs exports .mp3 while EDL lists .m4a),
    preferring whichever exists on disk.
    """
    root = Path(assets_root).resolve()
    asset = audio_track.get('asset')
    if not asset:
        return None

    # Check primary listed path
    primary = (root / asset).resolve()
    if primary.is_file():
        return primary

    # Check alternate extension for audio (.m4a <-> .mp3)
    p_obj = Path(asset)
    ext = p_obj.suffix.lower()
    if ext == '.m4a':
        alt = (root / p_obj.with_suffix('.mp3')).resolve()
        if alt.is_file():
            return alt
    elif ext == '.mp3':
        alt = (root / p_obj.with_suffix('.m4a')).resolve()
        if alt.is_file():
            return alt

    return None


def missing_assets(plan, root, allow_fallbacks=False):
    """Return sorted unique list of relative asset paths required by plan that do not exist."""
    root_path = Path(root).resolve()
    missing = set()

    for seg in plan['segments']:
        resolved = resolve_segment_asset(seg, root_path, allow_fallbacks=allow_fallbacks)
        if resolved is None:
            if seg['kind'] == 'motion':
                primary = f"runs/promo/scenes/{seg['scene']}.mp4" if seg.get('scene') else seg.get('asset')
                missing.add(primary or f"runs/promo/scenes/{seg['id']}.mp4")
            else:
                missing.add(seg.get('asset') or seg['id'])

    for aud in plan['audio']:
        resolved = resolve_audio_asset(aud, root_path)
        if resolved is None:
            asset = aud.get('asset')
            missing.add(asset or aud['id'])

    return sorted(missing)
