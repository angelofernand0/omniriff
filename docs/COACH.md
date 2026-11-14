# Coach: the AI side of OmniRiff (proposal, in progress)

Owner of the vision: **SM**. Written by SM's Claude, 2026-11-14. This is a scope for discussion. Nothing in it is built yet, and the pieces will be split across the team once the shape is agreed. Hours are rough guesses.

## 1. What OmniRiff is

**A practice rig with a teacher in the signal chain.**

- **User:** a guitarist who practises alone. Self-taught, or between weekly lessons. Beginner to intermediate.
- **Problem:** guitar apps can tell you *that* you made a mistake. They can't tell you *why*, and they can't run the fix with you. A teacher does both.
- **What only this rig can do:** it hears the guitar through the cable, sees your hands through the camera, and controls your looper and effects. So it can find the cause of a mistake and run the drill that fixes it, while your hands stay on the guitar.
- **Pitch:** "Every guitar app tells you that you were late. OmniRiff tells you it's because your strumming hand froze at the chord change, then loops the bar and drills it with you."

This is for the **"Best use of deepagents" special track** (LangChain; hacker packet p. 16). Suggestion, not decided: the main track could move from Entertainment and Media to **Education**. Only one is allowed and Angelo owns the submission.

### Why other AI coaches don't cover this

| Product | Does | Gap |
|---|---|---|
| Yousician, Simply Guitar, Rocksmith+, Fender Play | Listen and score against a fixed chart | Hear the result, not the technique. Can't see you. |
| Yousician "June" (Dec 2025) | Chat coach plus listening | Still chat plus listening |
| Positive Grid Spark AI | Describe a sound, get amp settings | Tone only |
| ROLI AI Music Coach (Feb 2026) | Watches hands and posture | Piano only |
| Camera guitar tutors | Track the fretting hand | Prototypes only, no mainstream product |

Sources and the full research are in section 10.

## 2. One session, start to finish

1. You play a strumming pattern with a chord change into the looper, four times.
2. **Ears:** the rig measures the gaps between strums. There's a long gap at every chord change.
3. **Eyes:** the camera shows the strumming hand stopped in those same moments.
4. **Coach:** "You're late on the change because your hand stops. Keep it swinging."
5. **Drill:** the coach sets up the rig (your own take loops quietly as a guide, effects off so you hear yourself dry) and asks for just the change, slowly.
6. **While you play:** a "hand moving" light and timing dots update live on the dashboard.
7. **Check:** you play the full pattern again. The dashboard shows before and after.
8. **Remember:** it logs what was wrong and what fixed it, and starts there next time.

The pedal and gestures are how you answer ("again", "next", "ok") without putting the guitar down.

## 3. How it works: two speeds

A deep agent takes seconds per step, so it can't react mid-strum. The job is split:

| Layer | Speed | Does | AI? |
|---|---|---|---|
| **Live layer** | Milliseconds | Detects each strum and hand movement, lights the dashboard as you play | No, plain code |
| **Coach** | Seconds, between takes | Reads the whole take, diagnoses, **writes the drill the live layer runs** | Yes, a deep agent |

```
guitar → audio engine → sound          real-time, unchanged, never waits for AI
            │
            ├─ finished loop saved as a take ─┐
camera → vision ─ hand movement log ──────────┤
                                              ▼
                                   Coach (separate process)
                                     │              │
              control messages (as "coach")     coach feed
                     ▼                              ▼
                  engine                        dashboard
```

Rules, same as the rest of the project:
- The coach is a separate process. If it crashes or the Wi-Fi drops, the instrument doesn't notice.
- It reaches the engine only through the existing validated control messages.
- Every piece of feedback comes from a measured number. No number, no claim.
- Changes to your live sound wait for your OK.

## 4. The deep agent

Built with LangChain's `deepagents` (0.7.38, needs Python 3.11+, `pip install deepagents`). Each part of the harness has a job:

| Part | Job |
|---|---|
| **Todo list** | The session plan, shown on the dashboard |
| **Filesystem** | The practice journal: take reports, drill cards, session notes |
| **Subagent: Ears** | Reads a take's timing data, returns findings |
| **Subagent: Eyes** | Reads the hand-movement data, returns findings |
| **Main agent** | Combines both into one cause and picks a drill |
| **Skills** | The drill library, one markdown folder each. Writable without code. First four: isolate-and-loop, slow-then-speed-up, dry check, keep-the-hand-moving. |
| **Memory** | Player profile and progress on each piece |
| **Human-in-the-loop** | Rig changes pause for approval (pedal or button) |

### Tools the coach gets

| Tool | Does | Status |
|---|---|---|
| `get_rig_state` | Reads the engine's state feed | Feed exists; wrapper is new |
| `get_take_report` | Timing measurements for the last take | New |
| `get_hand_report` | Hand-movement measurements for the last take | New |
| `rig_control` | Loop, bypass, filter, reverb, sent as `coach` | Sending exists (`tools/sim`); needs `coach` allowed |
| `write_drill_card` | Tells the live layer and dashboard what the drill is | New |
| `say` | One short cue to the dashboard (and voice) | New |

### Model

| Role | Model | Why |
|---|---|---|
| Main coach | `anthropic:claude-sonnet-5-5` | Built for fast agent work with tools. $2 in / $10 out per million tokens. |
| Ears and Eyes subagents | `anthropic:claude-haiku-5-5` | Narrow reading jobs where speed matters most. $0.10 / $0.50. |

- A session should cost well under a few dollars. That's an estimate; nothing has been measured.
- SM is providing the Anthropic API key for now. It goes in a local `.env` as `ANTHROPIC_API_KEY`, never in a commit or on the board.
- Things to check on the first run, because Sonnet 5.5 is strict about them: it rejects a custom `temperature`, it rejects forced tool choice (LangChain's structured output can use that), and thinking can't be switched off (lower the effort setting instead, start at low or medium for speed).

## 5. The coach on screen

SM's direction: a small floating character on the dashboard. A circle with eyes that squashes, stretches and moves.

- It **moves to whatever it is operating**: over the looper when it arms a loop, over the filter when it changes the tone, over the hand panel when it's watching your hand. Every movement maps to something the agent is really doing, so it is never decoration.
- States: idle, listening (you're playing), thinking, speaking, pointing, pleased.
- It **speaks** short cues and you can **talk to it**. For this weekend, the browser's built-in speech (Web Speech API) does both with no extra service. Chrome's speech recognition needs internet. To keep the guitar from confusing it, it only listens when you hold the pedal or the guitar is quiet.
- Text cue and checklist stay on screen, so it works with the sound off.

## 6. What has to be built

| # | Piece | What it is | Guess |
|---|---|---|---|
| A | **Take capture** | When a loop finishes recording, save it to a WAV outside the real-time path | 1–2 h |
| B | **Ears analysis** | From a take: strum times, gaps, where you rush, drag or hesitate. Plain numpy/scipy, offline. No click track needed. | 2–3 h |
| C | **Eyes analysis** | Log wrist movement during a take; detect the hand stopping | 2–3 h |
| D | **Coach core** | The deep agent: prompt, tools, two subagents, four drill skills, journal, memory | 4–6 h |
| E | **Coach feed** | New loopback WebSocket from coach to dashboard: checklist, cue, drill card, avatar state and target | 1–2 h |
| F | **Dashboard coach layer** | Checklist, cue line, before/after, the avatar | 3–5 h |
| G | **Live layer** | Timing dots and "hand moving" light while you play | 2–3 h |
| H | **Voice** | Browser speech in and out | 1–2 h |
| I | **Control source** | Allow `coach` in `protocol/control.schema.json` and the engine router | <1 h |

### New contracts (need agreement on the board before dependent code merges)

- `coach` added to the control `source` list.
- **Take report** (JSON): strum times, gaps, flagged spots.
- **Hand report** (JSON): movement over time, stalls.
- **Drill card** (JSON): what to play, how many times, what counts as a pass, what the live layer watches.
- **Coach feed** (WebSocket, proposed 47803): todos, cue, drill card, avatar state.

## 7. Owners

SM keeps the vision and every user-facing piece. The rest is handed off because each piece sits behind a file format. SM confirmed the D, E, F and H claims on issue #1 (2026-11-14).

| Piece | Owner | Status |
|---|---|---|
| D Coach core (deep agent), E coach feed | SM (claimed) | SM owns the AI |
| F Dashboard layer and avatar, H voice | SM (claimed) | User-facing; SM decides direction |
| A Take capture | Angelo's Claude | Merged in #47 |
| B Ears analysis | John's Claude | Claimed on issue #1 (originally suggested for SM's Codex) |
| C Eyes analysis | John's Claude | Merged in #40 |
| I Control source | Angelo's side (Angelo's Codex) | Lives in `engine/` and the shared protocol; SM doesn't need it |
| G Live layer | Whoever finishes first | Depends on B and C |

Don't start D, E, F or H without checking with SM on issue #1.

## 8. Order and timing

This has to start before the hardware run, so it's built against simulation first:
- **Takes:** the virtual guitar renders patterns with timing mistakes on purpose.
- **Hands:** the simulator's fake hand can be made to stall.
- **Rig:** `tools.sim run` is the real engine with a synthetic guitar.

| Step | Result |
|---|---|
| 1. A + B + D with one drill | Play (or render) a pattern → rhythm diagnosis → drill → before/after. Demoable alone. |
| 2. E + F | It's on the dashboard with the checklist and avatar |
| 3. C + G | The cause ("your hand stopped") and live lights |
| 4. H, memory, approvals | Voice and long-term memory. Memory can be described in the demo if it isn't finished. |

Team feature freeze is 4:00 AM Sunday. Devpost closes 8:00 AM Sunday.

## 9. Not verified

- **Detecting the hand stall with a real guitar in frame.** The hand feed runs at 20 updates a second, which should show a hand stopping for a third of a second. Untested. This is the riskiest piece and the main differentiator, so it's first on the list for the hardware night. If it fails, steps 1 and 2 still stand.
- **Strum timing on a real guitar signal.** Research says guitar strums are comparatively easy to detect. Untested here.
- **Agent speed and cost.** Not measured.
- **Venue Wi-Fi.** The coach and Chrome's speech recognition need internet. The instrument doesn't. Plan a hotspot and a labelled backup recording.
- **The hardware baseline.** The instrument hasn't run on the real setup yet. The coach is a separate process and can be dropped without touching it.

## 10. Research sources

- Hacker packet, pp. 4–5, 16, 19 (track text, judging)
- Deep Agents: https://docs.langchain.com/oss/python/deepagents/overview (plus the subagents, skills, backends, human-in-the-loop, event-streaming and frontend/todo-list pages), https://pypi.org/project/deepagents/
- Competitors: https://www.guitarworld.com/features/best-online-guitar-lessons , https://aitoolsbakery.com/blog/best-ai-guitar-apps/ , https://play.google.com/store/apps/details?id=com.yousician.lessons , https://www.guitarworld.com/gear/plugins-apps/positive-grid-bias-x-launch
- Camera coaching: https://newatlas.com/music/roli-ai-music-coach-piano/ , https://github.com/manbr21/Computer-Vision-Guitar-Tutor , https://doi.org/10.1109/tvcg.2023.3320266
- Apps vs teachers: https://violetrecording.com/yousician-review/ , https://www.lessonface.com/node/108850
- Practice research: https://discovery.ucl.ac.uk/id/eprint/1507397/1/Barry2002Practicing151.pdf , https://www.npr.org/sections/deceptivecadence/2017/03/06/518777865/the-most-practical-tips-for-practicing-according-to-science
- Strumming hand: https://community.justinguitar.com/t/keep-your-strumming-hand-moving/159231 , https://www.musictheoryforguitar.com/Master-The-Pendulum-Strum-Technique
- Quit rate (Fender's claim, no published method): https://www.musicradar.com/news/90-of-beginner-guitar-players-give-up-within-a-year-says-fender
- Strum detection: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3729570/
