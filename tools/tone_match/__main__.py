"""Find an achievable OmniRiff tone from dry/reference recordings of the SAME performance."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import wave
import numpy as np
from audio.fileio import read_wav, write_wav
from .match import fit, effect, residual
from .report import page
from .morph import audition as morph_audition


def load(path):
    # Bound allocation before using the shared WAV decoder.
    with wave.open(str(path), 'rb') as info:
        if info.getnframes() > info.getframerate() * 30 or info.getnchannels() not in (1, 2):
            raise ValueError('use a mono/stereo PCM WAV no longer than 30 seconds')
        if not 8000 <= info.getframerate() <= 96000:
            raise ValueError('sample rate must be 8000..96000 Hz')
    data, rate = read_wav(path)
    return data.mean(axis=1), rate


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dry', required=True, type=Path)
    p.add_argument('--reference', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path, help='new result folder; refuses overwrite')
    p.add_argument('--name', default='Matched tone')
    p.add_argument('--seconds', type=float, default=4)
    p.add_argument('--evaluations', type=int, default=64)
    a = p.parse_args(argv)
    if a.output.exists():
        p.error('output folder already exists; choose a new folder')
    if not a.name.strip():
        p.error('scene name must be nonempty')
    try:
        dry, rate = load(a.dry)
        reference, ref_rate = load(a.reference)
        if rate != ref_rate:
            raise ValueError('paired WAVs must have the same sample rate; resample and align before fitting')
        result = fit(dry, reference, rate, evaluations=a.evaluations, seconds=a.seconds,
                     progress=lambda n, loss: print(f'evaluation {n}: best normalized residual {loss:.5f}', file=sys.stderr) if n % 8 == 0 else None)
        matched = effect(dry, rate, result.filter, result.reverb)
        baseline = effect(dry, rate, 1, 0)
        analysis_end = min(len(dry), int(a.seconds * rate))
        full_residual, _ = residual(matched, reference)
        # Validate on the remaining performance with the fitted state carried
        # through from its start, rather than resetting reverb at the split.
        remaining_residual = None
        if len(dry) - analysis_end >= rate // 2:
            tail = reference[analysis_end:]
            if float(np.mean(tail.astype(np.float64)**2)) >= 1e-10:
                remaining_residual, _ = residual(matched[analysis_end:], tail)
        a.output.mkdir(parents=True, exist_ok=False)
        scene = result.scene(a.name)
        morph_audio, morph_events = morph_audition(dry, rate, scene)
        (a.output/'scene.json').write_text(json.dumps(scene, indent=2) + '\n')
        report = dict(asdict(result), method='bounded offline search of existing filter/reverb DSP',
                      assumptions='paired sample-aligned same-performance audio; no amp, distortion, pitch or source separation',
                      source_rate=rate, input_seconds=len(dry)/rate,
                      analysis_seconds=min(len(dry)/rate, a.seconds),
                      full_recording_residual=full_residual,
                      remaining_recording_residual=remaining_residual,
                      validation_warning='Fit does not explain the remaining recording' if remaining_residual is not None and remaining_residual >= .25 else None,
                      note='residual is normalized waveform error, not perceived similarity or confidence; reference gain is comparison-only and not in the exported scene')
        (a.output/'report.json').write_text(json.dumps(report, indent=2) + '\n')
        (a.output/'index.html').write_text(page(a.name, report), encoding='utf-8')
        write_wav(a.output/'baseline.wav', baseline, rate)
        write_wav(a.output/'reference.wav', reference, rate)
        write_wav(a.output/'matched.wav', matched, rate)
        write_wav(a.output/'scripted-morph.wav', morph_audio, rate)
        (a.output/'scripted-morph-controls.jsonl').write_text(''.join(json.dumps(event)+'\n' for event in morph_events))
        # Shared attenuation preserves relative loudness for the sequenced audition.
        gap = np.zeros(rate // 2, np.float32)
        audition = np.concatenate([baseline, gap, reference, gap, matched])
        audition *= min(1., .8 / max(float(np.max(np.abs(audition))), 1e-10))
        write_wav(a.output/'audition-baseline-reference-match.wav', audition, rate)
        print(json.dumps(report, indent=2))
    except (ValueError, OSError, wave.Error) as exc:
        p.exit(2, f'tone-match: {exc}\n')


if __name__ == '__main__':
    main()
