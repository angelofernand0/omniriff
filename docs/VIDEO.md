# Devpost video — "Never put the guitar down"

A ≤2-minute (target **~90 s**) promo for the Devpost video slot (YouTube link). Tone: an energetic tech-YouTuber review crossed with an animated short. Fast cuts, kinetic captions, Riff as the animated host, punch-in zooms on real footage. **16:9, 1920×1080, 30 fps**, burned-in captions (most judges watch muted first); an optional 9:16 cut for social.

**Honesty rules (non-negotiable):** every simulated or scripted clip keeps its on-screen SIMULATED / SCRIPTED label; every number is read off a real screen or measured run (no invented stats, no "X% of beginners quit"); real-rig shots come only from tonight's hardware run. If the real rig doesn't work, the video is the labeled simulated cut and says so in the first caption it appears under.

## Cast and sound
- **Host: Riff**, the pixel mascot (dashboard/brand, animated logo from #141). It pops, squashes, points, and talks with its mouth (riff.js already animates it). Voice: a designed, warm, slightly mischievous synthetic voice (not a clone of a real person).
- **Music:** an original generated bed, indie guitar-driven, upbeat ~110 BPM, ducked under the voice; a drop at the reveal.
- **SFX:** real sounds where we have them, recorded tonight: the footswitch click, a guitar stumble, a clean strum. Plus whoosh / pop / record-scratch transitions.
- **Captions:** kinetic, word-by-word, brand pink `#FF5CCB` on near-black `#0B0B10`, key words in the dashboard's pixel font.

## Beat sheet (~90 s)
| # | Time | Picture | Voice (Riff) / caption | Sound |
|---|---|---|---|---|
| 1 | 0:00–0:03 | **HOOK.** Black. A real guitar take with an audible stumble; the waveform freezes on the gap; a red marker slams onto it. | Caption: **"You messed up."** Riff pops in: *"…but do you know WHY?"* | Stumble, record scratch, silence |
| 2 | 0:03–0:10 | Fast collage: someone pausing to tap a phone app, rewinding a video lesson, a metronome. Animated, no stock brands. | *"Practising alone, every tool makes you stop playing. Apps grade your notes. A teacher tells you the cause, every week, for money."* | Beat starts low |
| 3 | 0:10–0:16 | **REVEAL.** The animated OmniRiff logo hop + letter shockwave (#141); the tagline types on. | *"So we built a teacher that lives in your signal chain."* Caption: **NEVER PUT THE GUITAR DOWN** | Drop |
| 4 | 0:16–0:24 | Real rig, wide: guitar → Scarlett → laptop, webcam, footswitch. Callout labels pop onto each part. | *"Guitar in. Camera on. One footswitch. That's it."* | Pedal click |
| 5 | 0:24–0:30 | Real: player says the goal (hold V); the GOAL card fills on screen. | Player (real voice): *"My G to C change."* Riff: *"Got it."* | |
| 6 | 0:30–0:44 | Real take with the planted stumble → the dashboard: plan steps tick, the Ears and Eyes trace lights up, the mark lands on the loop. Punch-in on the gap number. | *"I listen with **Ears**… watch your hand with **Eyes**… and that ___ ms gap? Your strumming hand froze right at the change."* (only if the HAND panel shows data; otherwise the timing-only line) | Typing blips, a ding on the number |
| 7 | 0:44–0:56 | Riff plays the take back, proposes the drill, and **waits**; a big "HOLD TO APPROVE" bubble; a close-up of a foot holding the switch. | *"I set up the drill, but I never touch your sound until you say so."* | Footswitch click (real) |
| 8 | 0:56–1:08 | Real fresh drill take → before/after numbers side by side, the GAP bar turning green. | *"Next take: ___ ms. Look at that."* (read off screen) Caption: **BEFORE ___ → AFTER ___** | Rising synth, success chime |
| 9 | 1:08–1:16 | The result card + NEXT TIME line; a memory "file" flies into Riff. | *"And next session, I remember where we left off."* | Pop |
| 10 | 1:16–1:24 | Real: a hand pinches and sweeps the filter in the air (hand skeleton overlay); then the camera cable gets yanked and the music keeps going. | *"Pinch to shape your tone. Unplug the camera, and the music doesn't care."* | Filter sweep, cable-yank thud, music continues |
| 11 | 1:24–1:32 | Animated architecture (docs/media/architecture.svg) assembling box by box, super fast. | *"Real-time audio engine, hand tracking, and a LangChain deep agent with subagents, skills and memory, built this weekend by four of us."* | Whooshes |
| 12 | 1:32–1:36 | Logo + tagline + repo URL. Riff waves. | *"OmniRiff. Never put the guitar down."* | Final strum, ring out |

Cut list if long: drop beat 11 to a 2 s flash, then beat 2 to 4 s.

## Shot list for tonight (humans, phone in landscape, 1080p+, steady)
Record each 5–10 s, several takes; also save the dashboard screen at the same time (Joey's Codex captures it).
1. Wide establishing shot of the whole rig on the table (good light).
2. Close-up: guitar cable into the Scarlett, input 2.
3. Close-up: the foot tapping, then **holding** the footswitch (capture the click audio too).
4. The player saying the goal while holding V (clean voice).
5. A full take with a planted stumble, with the guitar audio recorded clean via `--take-dir` (use that audio, not the phone mic).
6. The fresh drill take afterwards.
7. The pinch-and-sweep gesture, front-lit, hand clearly visible.
8. The camera USB being unplugged mid-song while the music continues (one clean take).
9. Faces: the four of you, a quick wave or nod (optional, 2 s).

## Production (who / what)
- **Script, voice, music, motion graphics, edit:** Angelo's Claude (Creative Claw: designed Riff voice, generated music bed, HTML/HyperFrames motion graphics, assembly with captions).
- **Dashboard screen captures:** Joey's Codex, from the final UI (after #140/#144), the scripted session segments 6–9 as backups, labeled SIMULATED, plus a live-rig dashboard capture tonight in sync with the phone footage.
- **Real footage:** the humans tonight, per the shot list.
- **Review:** SM (brand), the whole team (honesty pass) before upload.
