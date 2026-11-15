# Devpost 7:00 AM Submission Checklist

One-page field-by-field guide for submitting **OmniRiff** at HackPrinceton Fall '26.

- **Hard Deadline:** Sunday, Nov 15, 8:00 AM ET
- **Target Submission Time:** 7:00 AM ET (to leave 1 hr safety margin)
- **Submission Portal:** https://hackprinceton-fall-26.devpost.com/
- **Primary Source:** [`docs/DEVPOST-FORM.md`](DEVPOST-FORM.md) and [`docs/SUBMISSION.md`](SUBMISSION.md)

---

## 1. Project Overview Fields

| Devpost Field | Source / Value | Validation Rule |
|---|---|---|
| **Project Name** | `OmniRiff` | Exact match |
| **Tagline** | `A guitar teacher that lives in your signal chain.` | ≤ 60 chars (49 chars) |
| **Elevator Pitch** | `OmniRiff is a guitar teacher that lives in your signal chain: it hears and sees you play, finds why you stumbled, and sets up the drill, without you ever putting the guitar down.` | ≤ 200 chars (178 chars) |

---

## 2. Media Uploads (3:2 Aspect Ratio)

Upload files from `docs/media/` in this exact sequence:

1. **Cover / Thumbnail (Required):**
   - File: `docs/media/cover.png` (1500×1000, 3:2)
   - Visual: Big pixel Riff, OMNIRIFF wordmark, pink tagline, and an illustrated waveform with a red GAP marker (labeled ILLUSTRATION: a designed graphic, not a capture of the rig).
2. **Gallery Image 1:**
   - File: `docs/media/gallery-01-coach-3x2.png` (1024×683, padded 3:2)
   - Caption: *The OmniRiff practice dashboard mid-session: active loop playback (3.0s), real-time tone controls with simulated tone toggle, gesture knuckle tracking with parameter swap ('SWAPPED TO REVERB'), and AI Coach Riff assigning targeted Drill 1 ('Fix the measured cause') with pedal and voice controls.*
3. **Gallery Image 2:**
   - File: `docs/media/gallery-02-hand-3x2.png` (1920×1280, padded 3:2)
   - Caption: *Gesture control view (SIMULATED): generated hand landmarks engaging the filter sweep alongside the coach column. Synthetic hand feed, not webcam detection.*
4. **Gallery Image 3:**
   - File: `docs/media/gallery-03-evidence-3x2.png` (2361×1574, padded 3:2)
   - Caption: *Ears and Eyes evidence timeline on a SYNTHETIC FIXTURE: the real analyzers align planted 400 ms audio pauses with stationary wrist spans. Alignment doesn't establish a cause.*
5. **Gallery Image 4 (Architecture):**
   - File: `docs/media/architecture.png` (1500×1000, 3:2)
   - Caption: *OmniRiff cyber-physical architecture: dual sensor feeds (audio DI + camera), schema-gated control router, DSP engine, and LangChain deep agent coach.*

---

## 3. Video Demo (≤ 2 minutes)

- **Source File:** `runs/promo/omniriff.mp4` (assembled with `python -m tools.promo assemble docs/video/edl.json --assets . --out runs/promo/omniriff.mp4`), or the team's latest labeled cut.
- **Platform:** YouTube (Unlisted), Vimeo, or direct Devpost MP4 upload.
- **Verification:** Under 2 minutes, 1080p, captions legible. Every non-live clip is labeled on screen: `SIMULATED` / `SCRIPTED` for the simulator and scripted coach, `ANIMATION` for animated or motion-graphics segments (incl. any animated rig preview), `REPLAY` for replays. If there's no video by 7 AM, skip the field (it's optional).

---

## 4. Public Links

| Field | URL | Note |
|---|---|---|
| **GitHub Repository** | `https://github.com/angelofernand0/omniriff` | Must be Public |
| **Demo / Try It Out** | `https://omniriff.vercel.app/?source=simulator` | Zero-install browser simulator (SIMULATED). The hosted Riff coach needs the team passcode (shared privately, never in the form), so judges browsing see the instrument, not live AI coaching. |

---

## 5. Built With (Tags)

Paste comma-separated:
```text
python, numpy, scipy, sounddevice, portaudio, mediapipe, opencv, websockets, pyserial, jsonschema, javascript, typescript, vite, webaudio-api, html/css, arduino, focusrite-scarlett-solo, langchain deepagents, anthropic claude
```

---

## 6. Team & Discord Usernames

- **Team Members:** Angelo, SM, John, Aditya (Max 4 team members).
- **Discord Usernames:** (Required for HackPrinceton organizer contact — obtain live from Angelo):
  - Angelo: `[Angelo's Discord username]`
  - SM: `[SM's Discord username]`
  - John: `[John's Discord username]`
  - Aditya: `[Aditya's Discord username]`

---

## Measured results (hardware run)

Paste only lines that `runs/measure/*/results.md` reports as measured (latency, xruns, CPU, Ears on a real take). Anything it marks **not measured** stays out, or reads "not measured yet". Never a target or estimate.

## 7. Tracks to Tick & Statements

Check [`docs/DEVPOST-FORM.md` §7](DEVPOST-FORM.md#7-track-fit-statements-24-sentences-each) for exact statements:

**Leave every box unticked until a human confirms its prerequisite this morning.** Statements: DEVPOST-FORM.md.

1. [ ] **Main Track: Entertainment & Media**: human-only decision (Education only if the team agrees in person).
2. [ ] **LangChain: Best use of deepagents**: needs the coach running (hosted or local) for the demo.
3. [ ] **Amazon: Best Practical AI**: needs a working prototype demo at the table.
4. [ ] **Best Physical AI ($500)**: needs the coach acting on the rig/browser instrument after the player's approval.
5. [ ] **Best Hardware**: needs the footswitch + camera + Scarlett working at the table.
6. [ ] **Best Beginner Hack**: 3 of 4 of us are first-time hackers. **Check the prize's eligibility rule on Devpost first**; some require every member to be a first-timer. Tick only if eligible.

*Drop any track if its prerequisite is non-functional by 7:00 AM.*

---

## 8. Narrative Sections (Copy from `docs/DEVPOST-FORM.md` §8)

Copy each markdown section verbatim from [`docs/DEVPOST-FORM.md`](DEVPOST-FORM.md):
1. **Inspiration**
2. **What it does**
3. **How we built it**
4. **Challenges we ran into**
5. **Accomplishments that we're proud of**
6. **What we learned**
7. **What's next for OmniRiff**
8. **Charity (Conversations, not user studies)**
9. **Disclosures**

---

## 9. Final Honesty & Pre-Submission Audit

Run this 60-second check before hitting **Submit**:

- [ ] **No Unfilled Brackets:** Search the Devpost form for `[` or `]`. Replace any `[after the hardware run: ...]` or placeholder text with actual measurements or omit cleanly.
- [ ] **Label Transparency:** All non-hardware audio/video is explicitly identified as `SIMULATED` or `REPLAY`.
- [ ] **No Fake Latency or Study Claims:** Latency numbers state measurement technique (loopback/internal buffers, not fabricated round-trip). Player conversations are cited as informal venue chats, never formal user studies.
- [ ] **Disclosures Present:** MediaPipe, Claude Sonnet/Haiku, deepagents, board helper, Freeverb tunings, and AI coding agents (Claude Code, Codex, Gemini) are disclosed.
- [ ] **Repo is Public:** Test `https://github.com/angelofernand0/omniriff` in an incognito window.
- [ ] **Live Link Works:** Test `https://omniriff.vercel.app/?source=simulator` in an incognito window.
