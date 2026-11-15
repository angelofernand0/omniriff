# OmniRiff Video Edit Plan

This directory contains the production assets and timeline definitions for the OmniRiff Devpost promotional video (~90 seconds, 1920x1080 @ 30 fps), derived from [VIDEO.md](../VIDEO.md).

## Files in this Directory

- **`edl.json`**: Machine-readable Edit Decision List (EDL v1) conforming to the assembler contract for `python -m tools.promo assemble edl.json`. Defines all 12 video segments, audio layers (voice, music, SFX), and caption timing.
- **`captions.srt`**: Standard SubRip subtitle track with millisecond-accurate timestamps matching the 12 beats.
- **`SCRIPT.md`**: Timed voiceover script for SM as the narrator host (target ≤ 2.7 words/second), with placeholders (`___`) for measured hardware numbers.

---

## Timeline & Asset Overview

| Beat | Time | Duration | Segment Type | Asset / Scene | Voice Speaker & Line |
|---|---|---|---|---|---|
| **1** | 0:00–0:03 | 3.0s | Motion | `hook` | SM: *"…but do you know why?"* |
| **2** | 0:03–0:10 | 7.0s | Motion | `collage` | SM: *"Practising alone, every tool makes you stop..."* |
| **3** | 0:10–0:16 | 6.0s | Motion | `logo` | SM: *"So we built a teacher that lives in your signal chain."* |
| **4** | 0:16–0:24 | 8.0s | Video | Shot 1 & 2 (`rig`) | SM: *"Guitar in. Camera on. One pedal. That’s it."* |
| **5** | 0:24–0:30 | 6.0s | Video | Shot 4 (`goal`) | Player: *"My G to C change."* / Riff: *"Got it."* |
| **6** | 0:30–0:44 | 14.0s | Video | Shot 5 + UI (`diagnosis`) | SM: *"Riff listens with Ears, watches your hand with Eyes..."* |
| **7** | 0:44–0:56 | 12.0s | Video | Shot 3 + UI (`approval`) | SM: *"It sets up the drill, plays your take back..."* |
| **8** | 0:56–1:08 | 12.0s | Video | Shot 6 + UI (`result`) | SM: *"A fresh drill take. Look at that: down to ___ ms."* |
| **9** | 1:08–1:16 | 8.0s | Video | UI (`memory`) | SM: *"And next session, it remembers right where you left off."* |
| **10** | 1:16–1:24 | 8.0s | Video | Shot 7 & 8 (`failsafe`) | SM: *"Pinch to shape your tone. Unplug the camera..."* |
| **11** | 1:24–1:32 | 8.0s | Motion | `architecture` | SM: *"Real-time audio engine, hand tracking, and a LangChain deep agent..."* |
| **12** | 1:32–1:36 | 4.0s | Motion | `end` | SM: *"OmniRiff. Never put the guitar down."* |

---

## Brand & Production Guidelines

- **Color Palette:** Pink `#FF5CCB` on `#0B0B10` dark canvas. Red `#FF5340` is reserved strictly for **REC** (recording) indicators.
- **Approved Terminology:**
  - Say **PEDAL** (never "footswitch").
  - Say **CAM** (never "webcam").
  - Use badge **`PINCH = TONE`** (the word "clutch" is strictly banned per BRAND_SPEC §10).
- **Truthful Status Representation:**
  - Beat 9 (`saved to filesystem`) and Beat 11 (`deep agent with subagents, skills, memory`) are used only if fully shipped when filming; otherwise fall back to the in-progress prototype phrasing documented in [SCRIPT.md](SCRIPT.md).
  - Every `___` placeholder is filled from measured values on the live hardware screen.

---

## Instructions for SM (Voiceover & Audio Generation)

The voiceover script is ready in [SCRIPT.md](SCRIPT.md). Two options are supported for voice delivery:

### Option A: ElevenLabs Voice Generation (Primary if account available)

If you have an ElevenLabs account:
1. **Voice Selection:** Use a stock or designed voice (energetic, friendly tech-reviewer tone). Do **not** clone any person's voice without their explicit consent.
2. **Export Format:** Export one MP3 per line/beat, named `vo-<beat>-<take>.mp3` (e.g. `vo-02-1.mp3`, `vo-06-1.mp3`), into the team shared folder (`runs/promo/audio/` locally).
3. **Sound Effects (SFX):** Use ElevenLabs sound-effects generator for transition cues (whoosh, pop, record scratch) if needed.
4. **Music Bed:** Use ElevenLabs music generator (or royalty-free guitar bed) for the ~110 BPM indie guitar groove.
5. **License Link:** Ensure your plan's license permits commercial/demo use, and keep a link to your license page in your submission notes.

### Option B: Phone Recording (Authentic Fallback)

1. Record each line on a phone in a quiet room (phone 15–20 cm away).
2. Read with an energetic, friendly tech-reviewer tone, smiling while talking.
3. Save 3 takes per line with 1 second of silence before and after.
4. Name files: `vo-<beat>-<take>.m4a` (e.g. `vo-06-2.m4a`).
5. Share in the team shared folder.

> [!IMPORTANT]
> Audio and video media files belong in `runs/promo/` (git-ignored) and must **never** be committed to git.

---

## Assembler Specification

The EDL v1 format matches `tools.promo` specification:
```json
{
  "version": 1,
  "width": 1920,
  "height": 1080,
  "fps": 30,
  "duration_s": 96.0,
  "segments": [...],
  "audio": [...],
  "captions": [...]
}
```
