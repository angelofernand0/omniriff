"""A portable local audition page: no server, uploads, or external assets."""
from html import escape


def page(name, report):
    name = escape(name)
    assessment = escape(report['assessment'])
    validation = escape(report.get('validation_warning') or 'Listen to the whole comparison before using this scene.')
    return f'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{name} · OmniRiff Tone Match</title>
<style>
:root{{color-scheme:dark;font:17px/1.6 system-ui;background:#10141e;color:#edf1fa}}
body{{max-width:940px;margin:auto;padding:40px 24px}} h1{{font-size:clamp(36px,7vw,64px);line-height:1.05;margin:20px 0}}
.eyebrow{{color:#8ef0cd;letter-spacing:.16em;font-size:12px;text-transform:uppercase}}
.muted{{color:#a7b3c9}} .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px;margin:30px 0}}
article,.result{{border:1px solid #344057;border-radius:18px;padding:22px;background:#192130}}
article h2{{margin:0;font-size:21px}} audio{{width:100%;margin-top:20px}} a{{color:#8ef0cd}}
strong{{color:#fff}} .numbers{{display:flex;gap:32px;flex-wrap:wrap}} .numbers b{{font-size:30px;display:block}}
code{{overflow-wrap:anywhere}} button{{background:#8ef0cd;color:#102219;border:0;border-radius:8px;padding:10px 18px;font:inherit;cursor:pointer}}
</style>
<p class="eyebrow">OmniRiff / Tone Match → Gesture Scene</p><h1>{name}</h1>
<p class="muted">Hear a target. Find an achievable effect. Put the transition in your hand.</p>
<div class="result"><strong>{assessment}</strong><div class="numbers">
<p><b>{report['filter']:.3f}</b>Filter</p><p><b>{report['reverb']:.3f}</b>Reverb</p>
<p><b>{report['residual']:.5f}</b>Normalized waveform error</p></div>
<p>Lower error means a closer fit to this paired recording. It is not a perceptual score or a confidence percentage.</p><p>{validation}</p></div>
<div class="cards">
<article><h2>01 · Original</h2><p class="muted">Open filter, no reverb.</p><audio controls preload="none" src="baseline.wav"></audio></article>
<article><h2>02 · Target</h2><p class="muted">Your paired reference.</p><audio controls preload="none" src="reference.wav"></audio></article>
<article><h2>03 · Matched</h2><p class="muted">Rendered by the real engine.</p><audio controls preload="none" src="matched.wav"></audio></article>
</div>
<button id="stop" type="button">Stop audio</button>
<p>Continuous comparison: original → target → matched, with half-second gaps and shared attenuation.</p>
<audio controls preload="none" src="audition-baseline-reference-match.wav"></audio>
<h2>Hear the transition</h2><p>Scripted preview: original for the first quarter, a smooth morph through the middle half, then the fitted tone. This is automated movement, not a recorded hand performance.</p>
<audio controls preload="none" src="scripted-morph.wav"></audio>
<p><a href="scripted-morph-controls.jsonl" download>Download scripted controls</a> for engine replay or the virtual guitar’s <code>--controls</code> option.</p>
<h2>Make it a gesture</h2><p><a href="scene.json" download>Download the scene</a> · <a href="report.json">Fit diagnostics</a></p>
<p>From the OmniRiff checkout, use the full path to this scene:</p>
<p><code>python -m vision --model /path/to/hand_landmarker.task --scene-file /path/to/scene.json</code></p>
<p class="muted">Start the engine separately. Open your hand to arm, then pinch to engage and move vertically to morph. Release to hold the last value.</p>
<h2>What this match means</h2>
<p>Both inputs must be sample-aligned recordings of the same performance. This searches only OmniRiff’s filter and reverb; it cannot copy an amplifier, distortion, another performance, or a full song mix. Stereo inputs are averaged to mono.</p>
<p>Analysis uses the first {report['analysis_seconds']:.2f} seconds. Recording-gain adjustment ({report['reference_gain']:.3f}×) is used only in scoring; the scene and matched audio retain engine output levels. A similar score does not guarantee similar loudness.</p>
<p>Full-recording error: {report['full_recording_residual']:.5f}. Different settings may sound equivalent on this source, especially above its useful frequency range; the fitted knobs are not guaranteed to be the original settings.</p>
<p class="muted">{report['evaluations']} engine renders · {report['elapsed_seconds']:.2f} seconds fitting time on this machine.</p>
<script>
const players=[...document.querySelectorAll('audio')];
players.forEach(a=>a.addEventListener('play',()=>players.forEach(b=>{{if(b!==a)b.pause()}})));
document.querySelector('#stop').onclick=()=>players.forEach(a=>a.pause());
</script></html>'''
