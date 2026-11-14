# OmniRiff brand spec

Owner: SM. Written by SM's Claude, 2026-11-14. This is the source of truth for how OmniRiff looks, sounds and what it is for. `dashboard/brand.css` holds the tokens in code, `dashboard/brand.html` shows everything built, and [docs/COACH.md](docs/COACH.md) holds the AI scope. Where this file and another disagree on look or wording, this file wins. Where they disagree on what is built, the code wins.

Status words used below: **built** (on this branch), **proposed** (needs the owner's yes), **not built**.

## 1. One line

**OmniRiff is a practice rig with a teacher in the signal chain.**

The idea underneath every feature: **never put the guitar down.** The pedal starts the loop, a pinch moves the tone, and the coach sets up the drill. Your hands stay on the strings.

| Length | Line |
|---|---|
| 5 words | Never put the guitar down. |
| 1 sentence | OmniRiff is a guitar rig you run with your foot and a pinch, with a coach that hears you, sees your hands and runs the drill. |
| 20 seconds | Guitar apps tell you that you were late. They can't tell you why, and you have to stop playing to use them. OmniRiff sits in your signal chain. It hears the guitar, sees your hands and controls your looper and effects, so it can find the cause and loop the bar with you while you keep playing. |

Say the coach lines only when the coach has shipped. Until then the sentence is: "OmniRiff is a guitar rig you run with your foot and a pinch. A coach that reads your takes is in progress."

## 2. Who it is for

**Primary: the guitarist who practises alone.** Self-taught or between weekly lessons, one to five years in, plays in a bedroom with headphones or a small amp, 20 to 40 minutes at a time. They already own or would buy an audio interface. They stall because nobody tells them why a passage keeps going wrong, and every tool they own makes them stop and reach for a knob, a mouse or a phone.

**Secondary: players for whom small knobs and precise stomps are a barrier.** Limited hand mobility or dexterity. A foot press and a hand gesture replace fine motor control. This is a design intent. We have run no user studies and never say we have.

**Who watches the screen: a judge, for two minutes, over a shoulder or on a projector.** They cannot hear an effect change unless they see it. The screen exists to make cause and effect visible from two metres.

Not for: studio producers, pedalboard collectors, people who want a DAW, or absolute first-week beginners who need chord charts.

## 3. Position

| Them | They do | We do |
|---|---|---|
| Yousician, Simply Guitar, Rocksmith+, Fender Play | Listen and score against a chart | Hear the take and see the hand, then name the cause |
| Chat-style AI coaches | Talk about practice | Operate the rig: loop the bar, take the effects off, run the drill |
| Multi-effects pedals and amp apps | Give you sounds | Give you control without taking a hand off the guitar |
| Loop pedals | Record and repeat | Record, repeat, and show what happened |

Sources for the competitor rows are in docs/COACH.md section 10.

**Three things we say, in this order:**
1. **Hands stay on the guitar.** Foot for the loop, pinch for the tone. Strumming never moves a control.
2. **It never stops the music.** Audio does not wait for the camera, the screen or the AI. Unplug any of them and it keeps playing.
3. **It finds the cause, then runs the fix.** The coach reads the take and the hand together and sets up the drill. *(In progress. Say so.)*

### What each judge is looking for

Criteria are from the hacker packet, pages 4 and 5 (main tracks) and 13 to 16 (special tracks).

| Judge asks | Our answer | Where they see it |
|---|---|---|
| **Creativity:** what is the "ah-ha"? | The rig sees your hands and controls your gear, so it can say *why* you were late, not only *that* you were. | Pinch moves the filter while the HAND panel shows the pinch. Riff travels to the control it is changing. |
| **Utility:** does it work, would you use it? | It is a playable instrument first. Loop, filter, reverb, bypass, with every input able to fail. | LEDs per input, live meters, the loop waveform, `xruns 0` in the footer. |
| **Charity:** who does it help? | People who practise without a teacher, and players for whom knobs and stomps are a barrier. No user studies yet. | Said in the pitch. Never shown as a result. |
| **Avidity:** is it finished and loved? | One look, one voice, a named character, an offline screen that tells you what to type. | The whole screen. This document. |
| **Hardware / Physical AI:** is the AI in a physical loop? | A pretrained hand model drives a real audio path through a clutch, a confidence gate and a manual override. | HAND panel, CAM LED, the engaged takeover. |
| **deepagents:** where is the agent? | A deep agent that plans a session, reads take and hand reports and acts on the rig. *(In progress.)* | The COACH module. Today it reads COACH OFF. |
| **Amazon Practical AI:** real user, real use? | Target user and use case above, working prototype, documentation in the repo. | README, docs/DEMO.md. |

## 4. Voice

Written like the legend on a pedal and the first page of its manual. The reader has a guitar on and both hands busy.

**Rules**

1. **Label first.** State, then number, then one instruction. `PLAY` · `4.0 s` · `Press to clear`.
2. **Verb first.** "Press pedal to record", not "You can press the pedal to start recording".
3. **A number where there is one**, with its unit. `Low-pass 2681 Hz`, `30 S MAX`, `4 of 4`.
4. **One instruction at a time.** If it needs three steps, write three short sentences: "Press pedal. Play. Press again."
5. **Say what is true now.** `COACH OFF`, `NO CAMERA`, `STALE`. Never a hopeful word for a missing thing.
6. **No exclamation marks, no apology, no "please", no "oops", no "just", no emoji.**
7. **Two cases only.** UPPERCASE for anything the machine prints as a label or state (pixel type). Sentence case with no full stop for a single hint; full stops only when there are two or more sentences.
8. **The coach speaks in two sentences at most:** the cause, then the fix. It never praises without a number. "Change landed. 4 of 4." not "Great job".
9. **Name the mode when the input is not live.** `REPLAY`, `SCRIPTED PREVIEW`, simulated audio. Always on screen, never only in the docs.

**Vocabulary.** One word per thing, everywhere: screen, docs, pitch.

| Use | Not | Means |
|---|---|---|
| LOOP | looper, loop station, track | The one recorded phrase and its module |
| TAKE | attempt, recording | One pass the coach reads |
| TONE | FX, effects section | The filter and reverb module |
| FILTER, REVERB | sweep, wah, space | The two effects |
| PINCH | clutch, grab, gesture | Thumb and index together: the hand has the control |
| HAND | gesture view, skeleton | The tracked hand and its module |
| PEDAL | footswitch, Arduino | The foot control |
| CAM | webcam, vision | The camera input |
| ENGINE | backend, server | The audio process |
| COACH | AI, assistant, bot, agent | The role. On screen and in the pitch. |
| Riff | the avatar, mascot | The coach's character. A name, so sentence case. |
| CUE | tip, feedback, message | One line from the coach |
| DRILL | exercise, lesson | What the coach sets up |
| BYPASS | mute, FX off | Dry signal straight through |

**Status words** (the only ones the LEDs use): `LIVE` `STALE` `OFFLINE` · `ON` `IDLE` `OFF` `PINCH` · `NO PORT` · `PREVIEW`.

## 5. Tokens

Exact values. Defined once in `dashboard/brand.css`.

### Colour

| Token | Hex | Job | Contrast on panel |
|---|---|---|---|
| `--accent` | `#FF5CCB` | **Pink. Alive:** loop playing, hand has the control, coach awake | 6.8:1 |
| `--accent-ink` | `#0B0B10` | Text on pink, amber or green fills | 7.1:1 on pink |
| `--accent-shade` / `--accent-low` | `#D63FA6` / `#B4318A` | Riff's ridges; Riff's body and ridges when asleep | |
| `--accent-deep` / `--accent-dim` | `#3B1A4F` / `#5A2A75` | Faint graph behind the engaged number | |
| `--rec` | `#FF5340` | Recording, clipping, meter red zone | 5.8:1 |
| `--warn` | `#FFB547` | Bypass, stale, replay, preview, meter amber zone | 10.6:1 |
| `--ok` | `#8FE3A6` | Connected and current, meter green zone | 12.1:1 |
| `--text` | `#ECE9F5` | Values and names | 15.5:1 |
| `--muted` | `#A6A3B6` | Labels and hints | 7.6:1 |
| `--faint` | `#868399` | Index numbers, off legends, empty-state hints | 5.1:1 |
| `--dim` | `#4A4858` | Unplayed loop, untouched graph | not for text |
| `--off` | `#24232E` | Unlit block | not for text |
| `--line` / `--line-2` | `#262532` / `#34323F` | Borders | |
| `--panel` / `--panel-2` | `#13121A` / `#1C1A26` | Module, raised key | |
| `--bg` / `--bg-bar` | `#0B0B10` / `#0F0F15` | Page, faceplate and footer | |
| `--shadow` | `#060609` | Hard shadow | |

Rules: dark only, no light theme. Pink is never used for a warning, a link in running text or decoration. Red was moved from `#FF5A6E` to `#FF5340` so that REC and PLAY cannot be confused. A signal colour never carries meaning alone: every LED has a word beside it.

### Type

| Token | Size | Face | Use |
|---|---|---|---|
| `--p6` | 112 px | Silkscreen | Effect value |
| `--p5` | 72 px | Silkscreen | Value on short screens, BYPASS |
| `--p4` | 48 px | Silkscreen | Loop state, stamp, engaged name |
| `--p3` | 32 px | Silkscreen | Effect name |
| `--p2` | 24 px | Silkscreen | Spare |
| `--p1` | 16 px | Silkscreen | Labels, LEDs, keys, chips |
| `--t3` | 20 px / 600 | JetBrains Mono | Coach cue, loop length |
| `--t2` | 16 px | JetBrains Mono | Hints, detail lines |
| `--t1` | 14 px | JetBrains Mono | Footer, captions. Nothing smaller. |

Silkscreen sizes are multiples of 8 so every stroke lands on a whole pixel. Numbers use tabular figures. Both fonts ship in `dashboard/fonts/` (SIL OFL 1.1); the page makes no network request for type.

### Space, line, shape

- Unit `--u` = 4 px. Gaps and padding use the named steps `--s1` to `--s6`: 4, 8, 12, 16, 24, 32. The one exception is 2 px, allowed for strokes and for the vertical padding of small legends (key letters, CLIP).
- Stroke 2 px. Emphasis 4 px (the engaged panel, stamps).
- No rounded corners, no gradients, no blur. Shadows are a solid 4 px offset. The one soft thing allowed is a 2 to 4 px solid ring around a lit LED or a moving card.

### Motion

| Token | Value | Use |
|---|---|---|
| `--tick` | 80 ms, `steps(1..2)` | Key travel, block on or off |
| `--beat` | 160 ms, `steps(2..3)` | State colour, reveal |
| `--bar` | 240 ms, `steps(4)` | Panel swap, pop-in, nudge |
| stamp | 1000 ms, `steps(2)` | Loop moments |
| blink | 0.8 s REC and STALE, 0.4 s active input | LEDs |

The machine moves in steps. Only Riff moves smoothly (section 7). `prefers-reduced-motion` removes all animation and makes Riff jump instead of travel.

## 6. Pixel art

1. **One pixel size per drawing, whole-number scaling only.** The mark is 16 cells and shows at 16, 32, 64, 96 or 128 px. Icons are 8 cells and show at 16, 24, 32 or 64 px. Never 20, never 1.5x.
2. **Drawn as string grids in `dashboard/brand.js`**, rendered as SVG rectangles with `crispEdges`. No raster files, no anti-aliasing, no curves.
3. **One colour per icon** (`currentColor`). The mark has three: pink body, ink eyes, one paper glint per eye.
4. **No icon without a word beside it.** Six icons exist: loop, tone, hand, coach, pedal, cam. Adding a seventh needs a reason.
5. **Canvas drawings snap to whole pixels**: bars are 6 px on a 2 px gap, and graph heights are quantised to 4 px.
6. **Nothing pixelated is rotated or skewed.** The old tilted BYPASS stamp is now square.
7. **The wordmark is drawn, not typed.** Seven rows, two-cell stems. `OMNI` in text colour, `RIFF` in pink. Do not set it in a font.

Logo files: `dashboard/brand/` (`logo.svg`, `mark.svg`, `wordmark.svg`, `logo-on-light.svg`, `favicon.svg`, `app-icon.svg`). Regenerate with `node dashboard/brand.js --export`. Clear space is one mark-width on every side.

## 7. Riff, the coach

**Built as a design only.** `dashboard/riff.js` draws and animates the character. It has no AI, opens no socket and sends nothing. COACH piece F drives it later through `OmniRiff.coach.set({ state, target, cue })`.

**The idea:** the machine is square and moves in steps. The teacher is the only round thing on the screen and the only thing that moves smoothly. You can always tell which one is talking.

**Form**
- A disc with eight soft ridges, like a knurled knob seen from above. Pink body, darker ridge marks.
- Two large white eyes with dark pupils and a glint. **No mouth.** What Riff says is printed beside it in a square box, because the machine does the printing.
- 72 px on the dashboard. The logo mark is Riff on a 16-cell grid.

**States.** Each one means something the coach is doing. No idle wandering, no decoration.

| State | Looks like | Means |
|---|---|---|
| `asleep` | Darker body, eyes shut, a stepped "z" | No coach running. The default today. |
| `idle` | Blinks, glances | Awake, waiting for a take |
| `listening` | Eyes wide on the waveform, body bobs with the **real** input level | You are playing |
| `thinking` | Eyes up, lids lowered, the body turns steadily | Reading the take |
| `pointing` | Travels to a control, gives it a quarter turn, looks at it, prints a cue | Operating the rig |
| `speaking` | Small fast pulse, cue shown | Giving one cue |
| `pleased` | Eyes become two arches, a short hop | The drill passed |

**Movement**
- Travel is a slightly underdamped spring: it stretches along the direction of travel (up to 28%), overshoots, then squashes on landing.
- It perches inside a corner of the thing it is operating (`data-perch`), so the value stays readable.
- The body turns like a knob; the eyes stay level.
- When it leaves its dock, the dock shows an empty dashed socket and repeats the cue as text, so the screen works with the sound off.
- Clicking Riff while asleep makes it peek and settle. That is the only thing it does unprompted.

**Honesty rules**
- Riff is asleep unless a coach process is driving it.
- `?coach=preview` runs a scripted tour for demos and design review. The COACH LED turns amber and reads `PREVIEW`, and the module label reads `SCRIPTED PREVIEW`, for as long as it runs. The cues in the tour are sample text. Never present the preview as the AI.
- `?coach=off` removes Riff, the dock and the LED.

## 8. Feedback ("juice")

SM rejected particles and asked for research first. The rules that came out of it:

1. **Feedback lands on the thing that changed.** A loop event hits the loop panel. A value change lights that card. Nothing flashes the whole screen.
2. **Every effect is caused by a real engine frame**, a real input, or the player's own click. Nothing animates to look busy.
3. **Answer at once.** A key travels on press, before the engine replies. It turns pink when the socket took the event and nudges amber when it could not.
4. **Size the response to the event.** A value tick is a colour change. A loop closing is a stamp. Bypass shakes the tone zone. Clipping rattles the meter. Nothing else shakes.
5. **Good on the thousandth time.** No effect lasts over a second or blocks reading a value.
6. **Waiting looks like waiting.** Before the first frame, numbers read `--` and the blocks scan. With no engine, a full screen says `NO ENGINE` and what to type. Stale values dim. Nothing shows a made-up number.
7. **Empty is designed.** Icon, one label, one instruction: `NO LOOP` · "Press pedal. Play. Press again."

Removed in this pass: the full-screen colour flash, the logo that pulsed with output level, the animated bars on the offline screen. Particles were removed earlier.

## 9. The screen

One page, `dashboard/index.html`. A faceplate, five numbered modules, a footer.

| Zone | Holds |
|---|---|
| Faceplate | Logo, four LEDs (ENGINE, CAM, PEDAL, COACH), mode chips (SIMULATED or SIM GUITAR, REPLAY, BYPASS), meter bridge (IN over OUT, dB, CLIP) |
| 01 LOOP | State word, length, one hint; the waveform with playhead and a tick per second |
| 02 TONE | FILTER and REVERB cards (name, value, the effect's curve, block meter). While the hand has the control, one effect takes the whole zone. |
| 03 HAND | The tracked hand, or why there is none |
| 04 COACH | Riff's dock and the current cue |
| 05 MANUAL | Fallback keys and faders, closed by default |
| Footer | Diagnostics, keyboard legend (`F` `L` `B`) |

Fits 1920x1080, 1280x720 and the play room's iframe without scrolling; stacks to one column under 1080 px wide. `dashboard/brand.html` is the brand sheet.

## 10. Scope

### On the label (what we show and pitch)

1. The loop, by foot.
2. Filter and reverb, by pinch.
3. The screen that shows cause and effect.
4. It keeps playing when anything is unplugged.
5. The coach. *(Only once it runs. Otherwise one sentence: in progress.)*

### In the box, off the label (works, stays in the repo, not in the two minutes)

| Feature | Why it is off the label |
|---|---|
| Scene Morph, setlists | A second gesture vocabulary. The pinch is the one gesture we teach. |
| DualAxis, Stage HUD, gesture looper | Performer features. They pull the story toward "stage instrument" and away from practice. |
| StrumGuard | Keep it on. Mention it only when a judge asks whether strumming moves the filter. |
| Tone Match | A separate product. One line in "what's next" at most. |
| Replay, virtual guitar, simulator | Backup and test tools. Always labelled when used. |
| Noise gate, limiter, latency tool | Engineering answers for Q&A, not features. |

### Cut from the dashboard in this pass

- HAND CAM and PEDAL status tiles. They are LEDs on the faceplate now.
- The `PINCH` tag on a card that only meant "last moved". It reads `MOVED`.
- Full-screen flash, pulsing logo, decorative offline bars.
- The Google Fonts request.
- Lower-case and mixed status text (`quiet`, `watching`, `serial disabled`).

### Not building

Chat box. Settings page. Light theme. Accounts. A second route beyond the brand sheet. Overdub layers, BPM grid, loop scrubbing (the engine has none of them). Any coach UI that is not driven by a real coach process.

## 11. Open, needs an owner's yes

| # | Proposal | Owner | Status |
|---|---|---|---|
| 1 | Use "Never put the guitar down" as the Devpost tagline and open the demo with it | Angelo | **Adopted** (PR #55): docs/DEVPOST.md and docs/DEMO.md |
| 2 | Lead the README with the one-line and a screenshot | Angelo | **Adopted** (PR #55). Screenshot added with this pass: `docs/img/dashboard.png` (simulator). |
| 3 | The two-minute story is pinch + pedal + coach; the rest stays for Q&A | Angelo | **Agreed** on issue #1; docs/DEMO.md says so |
| 4 | Re-skin the play room page (`tools/virtual_guitar/web/`) with these tokens so the page around the dashboard matches it | SM's Codex | **Handed to SM's Claude** on issue #1 (08:56Z). Built in the stabilisation PR: `dashboard/playroom.css` and a few lines of markup, no behaviour. Replaces the closed #57. |
| 5 | Main track stays Entertainment and Media (Angelo's final call). The practice story still fits: it is a new way to play and to learn to play. | Angelo | No change asked |
| 6 | Riff asleep is visible by default. If the coach does not ship, either leave it (honest: `COACH OFF`) or launch with `?coach=off`. | SM | SM to decide at freeze |

## 12. Sources

- Hacker packet (HackPrinceton Fall 2026 on-site handbook): judging criteria pp. 4 to 5, tracks pp. 10 to 18.
- Teenage Engineering as a reference for constraint as the look (monospace, few colours, hard grid). Secondary commentary, not the company's own guidelines: https://blakecrosley.com/guides/design/teenage-engineering , https://limitedhype.pages.dev/stories/0058-teenage-engineering-and-their-design-philosophy
- Game feel and animation principles (squash and stretch, immediacy, restraint): https://www.gamedeveloper.com/design/squeezing-more-juice-out-of-your-game-design- , https://gamejuice.pages.dev/articles/game-juice-checklist-30-techniques , https://mintlify.com/raphaelsalaja/userinterface-wiki/animation/12-principles-of-animation
- Pixel art practice (one pixel size, whole-number scaling, small palettes): https://gdg.mit.edu/style-guide , https://bugnet.io/blog/choosing-a-pixel-art-resolution-for-your-game
- Character reference for a ridged blob with large eyes (inspiration only, nothing copied): https://uxdesign.cc/sora-app-icon-a-visual-breakdown-179235bd7ab0 , https://designcompass.org/en/2025/10/08/an-app-where-users-voluntarily-contribute-their-data
- UX writing (voice against tone, second person, economy): https://www.apollographql.com/docs/ux-writing-style-guide
- Contrast ratios computed with the WCAG 2 formula against `--panel`.
