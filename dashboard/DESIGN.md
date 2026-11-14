# OmniRiff dashboard design

The dashboard is a stage screen. The guitarist reads it from about 2 m away, mid-riff, with both hands busy, and a judge reads it over their shoulder.

**Look, voice, tokens, pixel-art rules and the coach character are in [BRAND_SPEC.md](../BRAND_SPEC.md).** This file covers how the page is built. The brand sheet at `/brand.html` shows every part.

## Principles

1. **Readable at 2 m.** Smallest text is 14 px and only for detail. Primary values are 48 px or larger.
2. **One thing big at a time.** When the hand has an effect, that effect takes the whole TONE zone.
3. **Few words.** A state word, a number and at most one hint.
4. **Hands-free first.** Pedal and hand are the inputs. On-screen controls are a fallback, closed by default.
5. **Square and stepped.** Pixel type, hard edges, stepped motion. Only Riff is round and smooth.
6. **Never lie.** The page shows engine state, not intent. No engine: it says so. Stale: values dim. Coach not running: `COACH OFF`.

## Files

| File | Job |
|---|---|
| `brand.css` | Tokens, fonts, shared parts: logo, label, LED, chip, key, fader, stamp, empty state |
| `brand.js` | Mark, wordmark and six icons as pixel grids. `node dashboard/brand.js --export` rewrites `brand/*.svg`. |
| `style.css` | Page layout and module styles |
| `app.js` | Engine socket, hand feed, rendering, manual controls |
| `juice.js`, `juice.css` | Feedback layer (stamps, hits, effect graphs, offline screen, keys). `?juice=off` disables it. |
| `riff.js`, `riff.css` | The coach character. Design only: no AI, no socket. |
| `brand.html` | Brand sheet |
| `fonts/`, `brand/` | Local fonts (OFL), exported logo files |

No build step. Load order in `index.html`: `brand.js`, `app.js`, `juice.js`, `riff.js`.

## Layout

| Zone | Size | Contents |
|---|---|---|
| Faceplate | auto | logo, LEDs (ENGINE, CAM, PEDAL, COACH), chips (REPLAY, BYPASS), meter bridge (IN over OUT, dB, CLIP) |
| 01 LOOP | 1fr, left | state word + length + hint; waveform with playhead and a tick per second |
| 02 TONE | 2fr, left | FILTER and REVERB cards, or one engaged effect; BYPASS stamp |
| Right rail | 304 px | 03 HAND, 04 COACH (Riff's dock), 05 MANUAL |
| Footer | auto | diagnostics, keyboard legend |

Breakpoints: under 1440 px the "PRACTICE RIG" tag hides; under 1340 px the logo shows the mark only; under 1080 px the deck becomes one column and the page scrolls; under 700 px cards stack and the loop state becomes one row. Screens 820 px tall or less (720p projector, the play room iframe) use tighter padding, 72 px values and a shorter hand view.

## Parts and states

**LED.** `.led` plus `on` (green), `warn` (amber, blinking), `hot` (pink, blinking). `app.js` uses `online` and `active` on the CAM and PEDAL LEDs for the same looks.

| LED | Words |
|---|---|
| ENGINE | `LIVE` / `STALE` (no frame for 1 s) / `OFFLINE` |
| CAM | `ON` (seen in the last 3 s) / `PINCH` (accepted in the last 350 ms) / `IDLE` / `OFF` |
| PEDAL | `ON` / `IDLE` / `OFF` / `NO PORT` (engine started without a serial port) or the adapter status |
| COACH | `OFF` / `PREVIEW` |

**Meter bridge.** 24 segments from −60 to 0 dBFS, green to −18, amber to −6, red above. Peak hold 1.5 s. CLIP holds 2 s when input reaches −1 dBFS or `clipped_samples` rises.

**Loop** (engine states from `audio/looper.py`):

| Engine | Word | Colour | Hint |
|---|---|---|---|
| `idle` | READY | muted | Press pedal to record |
| `recording` | REC, blinking dot, red border | `--rec` | Press again to close |
| `playing` | PLAY | `--accent` | Press to clear |

The waveform is built in the browser from `input_peak_dbfs` frames captured while recording. Idle shows the empty state. If the loop was recorded before the page opened, a placeholder shape is drawn and a note says so. The playhead runs on the local clock using `loop.seconds`.

**Effect card.** Name, value (112 px), one detail line (`Low-pass 2681 Hz`, `Open`, `Wet mix`, `Dry`), the effect's curve, a 16-block meter. The card that last moved gets a pink border, pink graph and a `MOVED` tag. Any value change lights the card for 220 ms.

**Engaged.** While vision events are being accepted, the cards give way to one panel: effect name, a giant value, a 20-block tower, and the same curve large and faint behind.

**Bypass.** A square amber stamp over the TONE zone with "Effects off. Dry signal."; the cards dim to 25%. The header chip shows above 1340 px.

**Hand.** 21 joints from the optional feed (`ws://127.0.0.1:47802`), mirrored and follow-zoomed. Pink with the pinch boxed and a value rail while engaged. Empty states: `NO CAMERA` (no feed), `NO HAND` (feed, nothing in frame), `HAND VIEW OFF` (`?hand=off`).

**Coach dock.** A 72 px socket where Riff rests, a state line and a sub line. When Riff is away the socket is dashed and the sub line repeats the cue.

**Manual.** Two keys (`L` LOOP, `B` BYPASS) and two faders. Keys are disabled with no engine. A key turns pink when the socket took the event and nudges amber when it did not.

**Before the first frame.** `data-boot="true"` on `#app`: values read `--`, blocks and meter segments scan. After 1.5 s with no engine the offline screen covers the page.

## Feedback layer (`juice.js`)

Display only. Every effect fires on a real change in an engine frame (`app.js` re-dispatches each frame as the `omniriff:frame` window event) and lands on the element that changed.

- **Loop moments:** a stamp on the waveform (`REC`, `LOOP 4.0S`, `CLEARED`) and a border hit on the waveform panel in the event's colour.
- **Downbeat:** when the playhead wraps, the loop state panel pulses.
- **Effect graphs:** the filter as a low-pass magnitude curve on a log frequency axis (2-pole approximation from `cutoff_hz`); the reverb as a dry hit plus a tail that grows with wet.
- **Bypass:** the TONE zone shakes; `FX ON` stamps when effects return.
- **Clip:** the meter bridge rattles.
- **Offline screen:** logo, a scanning LED row (the page is retrying), `NO ENGINE · START ONE` with the two commands, or `ENGINE LOST · RETRYING` if it was live before.
- **Keys:** `F` fullscreen, `L` loop, `B` bypass. The on-screen key travels when its letter is pressed.

`prefers-reduced-motion` keeps stamps, graphs and the offline screen and drops hits and shakes.

## URL parameters

| Parameter | Effect |
|---|---|
| `?ws=ws://host:port` | Engine state socket (default `ws://127.0.0.1:47801`) |
| `?hand=ws://host:port` / `?hand=off` | Hand feed (default `ws://127.0.0.1:47802`) |
| `?juice=off` | No feedback layer |
| `?coach=off` | No Riff, dock or COACH LED |
| `?coach=preview` | Scripted tour of Riff's states, labelled on screen. Not AI. |

## Not in v1 (needs engine or contract work)

- **Armed state** (hand raised, not pinching): needs a vision status field.
- **Pinch target chosen on the guitar screen:** today the `MOVED` card is inferred from the last value change.
- **Overdub layers, loop position in state, BPM grid:** the engine has none of them.
- **Coach feed:** checklist, drill card, timing dots on the waveform and voice arrive with COACH pieces E, F, G and H. The dock, the LED and `OmniRiff.coach.set()` are the hooks for them.
