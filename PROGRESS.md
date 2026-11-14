# Progress: brand and dashboard pass

SM's Claude, 2026-11-14. Branch `sm/claude/brand-pass`. Three passes, run in order: brand architecture, dashboard overhaul, design critique. The rules are in [BRAND_SPEC.md](BRAND_SPEC.md); this file is what changed and what was checked.

**The AI is not implemented.** The coach character is drawn and animated, with no agent, no socket and no control messages behind it.

## How to look at it

```bash
python -m tools.sim run --demo        # then open the three pages below
```

| Page | Shows |
|---|---|
| http://127.0.0.1:8080/ | The dashboard |
| http://127.0.0.1:8080/?coach=preview | The same, with a scripted and labelled tour of the coach character |
| http://127.0.0.1:8080/brand.html | The brand sheet: logo, colour, type, voice, parts, icons, Riff's states |

## Pass 1: brand architecture and scope

**Research first** (SM's standing feedback after the particles). References and what was taken from each are in BRAND_SPEC section 12: constraint as the look (monospace, few colours, a hard grid), game-feel rules (answer at once, reinforce the thing that changed, restraint), pixel-art practice (one pixel size, whole-number scaling), terse second-person interface writing, and the hacker packet's judging criteria.

**New: `BRAND_SPEC.md`**
- One line: "a practice rig with a teacher in the signal chain", under the idea "never put the guitar down", with 5-word, 1-sentence and 20-second versions.
- Audience: the guitarist who practises alone; players for whom knobs and stomps are a barrier (stated as intent, no user studies); the judge watching for two minutes.
- A table mapping each judging criterion and special track to our answer and where it shows on screen.
- Voice: nine rules, a one-word-per-thing vocabulary, the fixed list of status words.
- Tokens: every colour with its job and measured contrast, the type scale, spacing, strokes, motion timings.
- Pixel-art rules, the Riff character sheet, feedback rules, the screen map, scope (on the label, in the box, cut, not building), open decisions.

**New: logo.** A 16-cell pixel mark (Riff's face: a ridged blob with two eyes) and a hand-drawn pixel wordmark, `OMNI` in text colour and `RIFF` in pink. Defined as string grids in `dashboard/brand.js` and exported to `dashboard/brand/` as `logo.svg`, `mark.svg`, `wordmark.svg`, `logo-on-light.svg`, `favicon.svg`, `app-icon.svg`.

**New: six pixel icons** (loop, tone, hand, coach, pedal, cam), 8 cells each, same file.

**New: Riff, the coach character** (`dashboard/riff.js`, `riff.css`). A pink disc with eight ridges, large eyes and no mouth. Seven states: asleep, idle, listening, thinking, pointing, speaking, pleased. It travels on a spring with squash and stretch, turns like a knob when it reaches a control, perches in a corner of what it is operating and prints its cue in a square box. `OmniRiff.coach.set({ state, target, cue })` is the hook for COACH piece F. `OmniRiff.portrait(state)` returns a still for docs.

**New: unified shell** (`dashboard/brand.css`). Tokens, local fonts, and the shared parts every page uses: logo, module label, LED, chip, key, fader, stamp, empty state.

**Changed: `docs/COACH.md` section 5** now describes Riff as designed and says plainly that it is not wired.

**Colour changes:** REC red moved from `#FF5A6E` to `#FF5340` so it cannot be confused with the pink PLAY state. `--faint` added for index numbers and off legends, then raised to `#868399` to pass 4.5:1 on panels. Hard-coded greys and purples in canvas code became tokens (`--dim`, `--accent-dim`, `--accent-low`).

## Pass 2: dashboard overhaul

**Structure (`index.html`, `style.css`)**
- **Faceplate header:** logo, four LEDs (ENGINE, CAM, PEDAL, COACH), mode chips, and a meter bridge with input stacked over output.
- **Five numbered modules** with silk-screen labels and icons: 01 LOOP, 02 TONE, 03 HAND, 04 COACH, 05 MANUAL.
- **Right rail** holds hand, coach and manual. The HAND CAM and PEDAL tiles are gone; they are LEDs now.
- **Effect cards** rebuilt: name, 112 px value, one detail line, the effect's curve filling the card, a thin block meter. The old layout left most of each card empty.
- **Tall screens (1080p and up):** the loop spans the full width; the rail sits beside TONE only.
- **Coach dock:** a socket where Riff rests, a state line and a sub line. Reads `COACH OFF` · "Not running. The rig plays without it."
- **Footer:** diagnostics on the left, a keyboard legend on the right.

**Empty, waiting and failed states**
- No loop: pedal icon, `NO LOOP`, "Press pedal. Play. Press again."
- No camera feed / no hand in frame / hand view switched off: three different empty states.
- Before the first frame: values read `--` and blocks scan, instead of showing `100%` and `0%` as if they were real.
- No engine: full-screen logo, a scanning LED row, `NO ENGINE · START ONE` and the two commands (`python -m engine.demo --open`, `python -m tools.sim run --demo`), selectable in one click. After a drop: `ENGINE LOST · RETRYING`.
- Stale: the ENGINE LED blinks amber and the deck and meters dim to half, so frozen numbers are not read as current.

**Micro-interactions**
- Keys travel 4 px on press. They turn pink when the engine socket took the event and nudge amber when it could not. They are disabled with no engine.
- Pressing `L` or `B` on the keyboard makes the on-screen key travel too.
- Faders have a block cap, a pink fill and a live percentage.
- The manual panel opens with a stepped reveal; its marker is a pixel plus that becomes a minus.
- Loop events stamp the waveform and flash that panel's border in the event's colour.
- Clicking Riff while it sleeps makes it peek and settle.

**Removed** (BRAND_SPEC section 8: feedback lands on the thing that changed): the full-screen colour flash, the logo that scaled with output level, the animated bars on the offline screen, the tilted BYPASS stamp, the Google Fonts request.

**Copy, rewritten to the voice rules**

| Before | After |
|---|---|
| tap pedal to record / tap to close loop / tap to clear | Press pedal to record / Press again to close / Press to clear |
| no loop | `NO LOOP` + "Press pedal. Play. Press again." |
| HAND CAM · watching / quiet / offline | CAM · `ON` / `IDLE` / `OFF` / `PINCH` |
| PEDAL · serial disabled | PEDAL · `NO PORT` |
| NO FEED / HAND SEEN | `NO CAMERA` / `SEEN` |
| PINCH (tag meaning "last moved") | `MOVED` |
| 9662 Hz low-pass / open / wet 79% / dry | Low-pass 9662 Hz / Open / Wet mix / Dry |
| loop recorded before this page opened | Recorded before this page opened. Shape not shown. |
| WAITING FOR ENGINE / ENGINE OFFLINE · RECONNECTING | NO ENGINE · START ONE / ENGINE LOST · RETRYING |
| waiting for engine… | No engine yet |
| Manual controls | 05 MANUAL |

**Other owners' work.** Posted on issue #1 and waited. Angelo's Claude adopted the tagline in docs/DEVPOST.md and docs/DEMO.md, rewrote the README intro, and agreed the two-minute story is pinch + pedal + coach (PR #55). With that approval this pass adds one screenshot and caption to README.md. Nothing in `audio/`, `engine/`, `vision/`, `protocol/` or `tools/` was edited. The play room page re-skin was proposed to SM's Codex; no reply, so it is offered as a separate PR (#57: an override stylesheet plus a few lines of markup, no behaviour) and is not part of this one.

## Pass 3: critique and fixes

Every page was rendered in headless Chrome at 1920x1080, 1280x720, 1436x780 (the play room's frame), 900 wide and 390 wide, in these states: no engine, first frame, idle with no loop, recording, playing, hand engaged, bypass, stale, manual open, coach preview, `?juice=off`, `?coach=off`, reduced motion. What that found and what was done:

| Found | Fix |
|---|---|
| Header wrapped to two rows at 1280 whenever a label got longer (BYPASS chip, `PREVIEW`) | Input and output meters stacked into one bridge; logo drops to the mark under 1340 px |
| Riff's eyes too small to read from a distance | Eyes enlarged about 25%, second glint added |
| Loop and tone icons unreadable | Redrawn |
| Fully open filter drew a wall of white bars | Untouched graphs use `--dim`; pink only on the card that moved |
| Idle waveform drew a line through the `NO LOOP` text | Idle draws nothing; the empty state speaks |
| `CLEARED` stamp landed on top of the empty state | Empty state hides while a stamp is showing |
| Loop state panel changed width between READY and PLAY, so the waveform jumped | Fixed at 264 px |
| Right rail had dead space at 1080p; a first attempt made the hand view a tall empty column | Loop takes the full width on tall screens; hand view fills what the rail has left |
| Riff covered the module label when pointing at the hand panel | Perch moved inside a corner, set per target with `data-perch` |
| Riff would drift behind its dock on scroll in narrow layouts | Docked Riff follows the socket rigidly |
| Giant engaged number used a fluid size, putting pixel type off the 8 px grid | Fixed steps: 144 px, 200 px on large screens |
| Offline screen logo rendered small (a header rule leaked) | Rule scoped to the header |
| `?coach=off` left an empty dock and LED on screen | `[hidden]` now wins over layout rules |
| `NO HAND` showed a camera icon | Hand icon for no hand, camera icon for no camera |
| Stale state left the level meters bright with frozen values | Meters dim with the deck |
| CAM LED read `IDLE` while the hand panel showed a tracked hand | LED is `ON` whenever hand frames are arriving |
| Gap between the manual panel's header and body | Joined |
| Spacing values off the 4 px scale (20 px padding and gaps, 6 and 10 px legend padding) | Replaced with the named steps |
| `--faint` text at 4.4:1 on panels | Raised to 5.1:1 |
| Dead code left by the rewrite (unused level helper, unreachable idle branch, unused colour) | Removed |
| Default browser scrollbar in the narrow layout | Thin, in brand colours |

## Checks

This repo has no `package.json`, so there is no `npm run build`, lint or typecheck to run. The dashboard is plain HTML, CSS and JS with no build step. These are the repo's real checks, all run on the final commit:

| Check | Result |
|---|---|
| `python -m unittest discover -s tests` (what CI runs) | 165 tests, OK |
| `bash -n board.sh scripts/*.sh` (what CI runs) | OK |
| `node --check` on `app.js`, `juice.js`, `riff.js`, `brand.js` | OK |
| Every element id the scripts look up exists in `index.html` | none missing |
| Every CSS variable used is defined | none undefined (`--i` and `--hit` are set from JS) |
| Every class in `index.html` has a rule | none missing |
| Browser console during all renders above | no script errors and no failed file requests (the refused socket in the no-engine test is expected) |
| Fonts load from `dashboard/fonts/` with no network | confirmed with `document.fonts.check` |
| No horizontal or vertical overflow at 1920x1080, 1280x720, 1436x780 | confirmed by measuring scroll size |
| Manual key, fader and keyboard shortcut reach the engine | clicked BYPASS: engine went to bypass and the key lit; fader set the filter to 40%; `B` toggled bypass back |
| Tests that read `app.js` for exact lines (`tests/test_sim.py`) | still pass; those lines were kept |

## Not checked, and limits

- **Real hardware.** Everything above ran against `tools.sim` (synthetic guitar, scripted hand). No real engine, camera or pedal.
- **Browsers.** Headless Chrome only. The fader has Firefox rules that were not tested. Safari was not tested.
- **The play room with sound and camera.** The dashboard was rendered inside the running play room in headless mode (no speaker output) and fits its frame. It was not checked with speakers on or with the webcam started.
- **Two metres.** Readability was judged from screenshots, not from across a room on the projector.
- **Riff's motion** was checked in stills and by reading its state from the page, not by watching it move. SM should watch `?coach=preview` once.
- **The preview cues are sample text**, not coach output. The screen says `SCRIPTED PREVIEW` while it runs.

## Left for SM

1. Watch `?coach=preview` and say whether Riff's look and movement are right before piece F is built on it.
2. Decide at freeze whether Riff asleep stays visible if the coach does not ship (`?coach=off` hides it).
3. ~~The play room re-skin is PR #57.~~ Done in the stabilisation pass below.

## Stabilisation pass (2026-11-14, branch `sm/claude/stabilize`)

A release-engineering sweep of all of `main`, not a redesign. Audit and tickets are on issue #1.

- **Play room skin** (was the closed PR #57): `dashboard/playroom.css` over the play room's own stylesheet, the logo, and two labels. The camera label reads `CAM · LIVE HAND TRACKING`. No behaviour changed.
- **`SIMULATED` chip** (voice rule 9, backlog B8): the simulator's page and the play room's embedded dashboard now say on screen that the guitar is synthetic. Set by a URL flag, `?sim=`; no protocol or state change. Under 1440 px the wordmark folds to the mark while the chip shows, so the meters stay on the top row.
- **Font licences** travel with the fonts: `dashboard/fonts/OFL-*.txt`.
- Two unused imports removed in `tools/virtual_guitar/guitar.py` and `tests/test_virtual_guitar.py`.
- **Checked:** 166 tests; in headless Chrome on the simulator, the play room (`--live --headless`) and `engine.demo --headless --replay`: every button, both keys, the faders, engine offline, replay, coach preview and coach hidden, at 1920x1080, 1280x720 and the play room's iframe width. No page errors apart from the browser logging the hand socket as refused while no camera is running.
- **Not checked:** real hardware, a real webcam (no hand model in this checkout), audible output, Firefox or Safari.

## Files

| File | Change |
|---|---|
| `BRAND_SPEC.md`, `PROGRESS.md` | new |
| `dashboard/brand.css`, `brand.js`, `brand.html`, `riff.js`, `riff.css` | new |
| `dashboard/brand/*.svg`, `dashboard/fonts/*` | new |
| `dashboard/index.html`, `style.css`, `juice.css` | rewritten |
| `dashboard/app.js`, `juice.js` | edited: copy, states, key feedback, tokens; behaviour toward the engine unchanged |
| `dashboard/DESIGN.md`, `dashboard/README.md` | rewritten to match |
| `docs/COACH.md` | section 5 |
| `README.md`, `docs/img/dashboard.png` | screenshot and caption |
