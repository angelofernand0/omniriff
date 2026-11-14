# OmniRiff dashboard design language

The dashboard is a stage screen. The guitarist reads it from about 2 m away, mid-riff, with both hands busy. Everything below follows from that.

Canvas sketches: https://claude.ai/artifact/J8ZBdMoyx4eYyg5dngW58o (private until shared).

## Principles

1. **Readable at 2 m.** Smallest text is 14px and only for secondary labels. Primary values are 48px or larger. One glance gives the answer.
2. **One thing big at a time.** When the hand is controlling an effect, that effect takes over the whole bottom area. Everything else steps back.
3. **Few words.** A state word, a number and at most one short hint. No paragraphs, no instructions on the main screen.
4. **Hands-free first.** The pedal and the hand camera are the inputs. The on-screen controls are a fallback, tucked into "Manual controls".
5. **Retro and alive.** Pixel type, hard edges, blocky shadows. Motion moves in small steps (`steps()` easing), never a smooth glide. Things pulse when they change.
6. **Never lie.** The dashboard shows engine state, not intent. If the engine is gone, it says OFFLINE/STALE and stops animating values.

## Layout

| Zone | Height | Contents |
|---|---|---|
| Header | auto | brand, connection chip, bypass chip, IN meter (dB, clip light), OUT meter |
| Top third | 1fr | looper: state word + loop length + one hint; loop waveform with playhead |
| Bottom two thirds | 2fr | FX zone (filter and reverb cards, or one engaged effect), side column (hand cam, pedal, manual controls) |
| Footer | auto | diagnostics in one line (xruns, clipped, event counters) |

## Tokens

| Token | Value | Use |
|---|---|---|
| `--bg` | `#0B0B10` | page |
| `--bg-bar` | `#0F0F15` | header, footer |
| `--panel` / `--panel-2` | `#13121A` / `#1C1A26` | panels, buttons |
| `--line` / `--line-2` | `#23222E` / `#2C2B39` | borders |
| `--off` | `#24232E` | unlit meter blocks |
| `--text` / `--muted` | `#ECE9F5` / `#A6A3B6` | text (muted passes 4.5:1 on panels) |
| `--accent` | `#FF5CCB` | brand pink: playing, pinch target, engaged |
| `--accent-deep` | `#3B1A4F` | brand shadow |
| `--rec` | `#FF5A6E` | recording, clip, meter red zone |
| `--warn` | `#FFB547` | bypass, meter amber zone |
| `--ok` | `#8FE3A6` | live connection, online sources, meter green zone |

Purple (`#B57BFF`) is the tested alternative accent. Swap `--accent` only.

**Type:** `Silkscreen` (pixel) for state words, names and numbers. `JetBrains Mono` for everything else. Both load from Google Fonts with monospace fallbacks, so the page still works offline.

**Shape:** no rounded corners. Borders 2–3px. Shadows are solid offsets (`6px 6px 0`), never blurred, except for the accent glow ring on engaged or live elements.

## Components and states

**Input meter.** 24 segments from −60 to 0 dBFS. Green up to −18, amber to −6, red above. A peak-hold segment stays lit for 1.5 s. The CLIP light holds for 2 s when input reaches −1 dBFS or `clipped_samples` rises.

**Looper** (engine states from `audio/looper.py`):

| Engine | Word | Color | Hint |
|---|---|---|---|
| `idle` | READY | muted | tap pedal to record |
| `recording` | REC (blinking dot) | `--rec` | tap to close loop |
| `playing` | PLAY | `--accent` | tap to clear |

The waveform is built in the browser from `input_peak_dbfs` frames captured while recording (about 20 per second). Bars scroll in from the right during recording. During playback the played part is accent and the rest is grey, and a white playhead runs on the local clock using `loop.seconds`. If the loop was recorded before the page opened, the waveform shows a placeholder and says so.

**Effect cards (idle).** Name, a huge %, a 16-block meter and one detail line (cutoff Hz, or wet %). The card the hand last moved has an accent border and a PINCH tag. Any value change makes the card pulse (glow ring and accent number for about 220 ms). This is the "injection" feedback.

**Engaged.** While vision events are being accepted (the last one less than 350 ms old), the cards give way to one panel: effect name, a giant % and a 20-block tower that follows the hand. It pops in with stepped scaling. When the hand stops, it drops back to the cards.

**Bypass.** A BYPASS chip appears in the header and a tilted amber stamp sits over the FX zone. The cards dim to 25%.

**Sources.** HAND CAM and PEDAL tiles each show a dot: grey means offline or quiet, green means seen in the last 3 s, and blinking pink means active right now.

## Motion

- Use `steps(n)` easing for everything (pixel feel).
- Pop-in: 200–220 ms, scale from 0.94.
- Blink: 0.8 s for REC, 0.4 s for active sources.
- `prefers-reduced-motion` turns off all animation.

## Not in v1 (needs engine or contract work)

- **Armed state** (hand raised, not pinching): needs a vision status field in state v1, or a new event.
- **Pinch target chosen on the guitar screen:** today the target is inferred from the last-moved effect.
- **Overdub layers and selectable tracks:** the engine looper is single-track.
- **Loop scrubbing and loop position in state:** the playhead is estimated in the browser.
- **BPM and beat grid:** the engine has no tempo.
- **Juicier effect visuals:** particles flying into the waveform, flashes on change.
- **Voice coach:** captions in the footer and markers on the waveform. No chat box.
