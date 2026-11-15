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
   - Visual: Big pixel Riff, OMNIRIFF wordmark, pink tagline, and audio waveform with red GAP marker.
2. **Gallery Image 1:**
   - File: `docs/media/gallery-01-coach-3x2.png` (1920×1280, padded 3:2)
   - Caption: *Practice dashboard mid-session drill card ("Keep the hand moving"), 430 ms gap marker, Ears & Eyes checks, and session checklist.*
3. **Gallery Image 2:**
   - File: `docs/media/gallery-02-hand-3x2.png` (1920×1280, padded 3:2)
   - Caption: *Gesture control view showing synthetic hand landmarks engaging the tone filter sweep (FILTER 67%) alongside coach session.*
4. **Gallery Image 3:**
   - File: `docs/media/gallery-03-evidence-3x2.png` (2361×1574, padded 3:2)
   - Caption: *Ears and Eyes evidence timeline aligning planted 400 ms audio pauses with stationary wrist spans.*
5. **Gallery Image 4 (Architecture):**
   - File: `docs/media/architecture.png` (1500×1000, 3:2)
   - Caption: *OmniRiff cyber-physical architecture: dual sensor feeds (audio DI + camera), schema-gated control router, DSP engine, and LangChain deep agent coach.*

---

## 3. Video Demo (≤ 2 minutes)

- **Source File:** `runs/promo/omniriff.mp4` (or latest local cut `Documents/Codex/OmniRiff Video/OmniRiff - Animated rig preview.mp4`).
- **Platform:** YouTube (Unlisted), Vimeo, or direct Devpost MP4 upload.
- **Verification:** Ensure playback is under 2 minutes, letterboxed 1080p, captions legible, and `SIMULATED` / `SCRIPTED` badges visible.

---

## 4. Public Links

| Field | URL | Note |
|---|---|---|
| **GitHub Repository** | `https://github.com/angelofernand0/omniriff` | Must be Public |
| **Demo / Try It Out** | `https://omniriff.vercel.app/?source=simulator` | Deployed zero-install browser simulator |
| **Backup Demo URL** | `https://omniriff-dashboard.vercel.app/` | If Angelo's Vercel deployment is active |

---

## 5. Built With (Tags)

Paste comma-separated:
```text
python, numpy, scipy, sounddevice, portaudio, mediapipe, opencv, websockets, pyserial, jsonschema, javascript, typescript, vite, webaudio-api, html/css, arduino, focusrite-scarlett-solo, langchain deepagents, anthropic claude
```

---

## 6. Team & Discord Usernames

- **Team Members:** Angelo, SM, Joey, Aditya (Max 4 team members).
- **Discord Usernames:** (Required for HackPrinceton organizer contact — obtain live from Angelo):
  - Angelo: `[Angelo's Discord username]`
  - SM: `[SM's Discord username]`
  - Joey: `[Joey's Discord username]`
  - Aditya: `[Aditya's Discord username]`

---

## 7. Tracks to Tick & Statements

Check [`docs/DEVPOST-FORM.md` §7](DEVPOST-FORM.md#7-track-fit-statements-24-sentences-each) for exact statements:

1. [x] **Main Track: Entertainment & Media** (Duet with AI teacher inside instrument signal chain).  
   *(Fallback: Education track only if agreed in person by team).*
2. [x] **LangChain: Best use of deepagents** (Ears/Eyes subagents, planning graph, skill drills, pedal approval).
3. [x] **Amazon: Best Practical AI** (Frictionless hands-free practice, gesture tone, push-to-talk, failsafe).
4. [x] **Best Physical AI ($500)** (Concurrent guitar DI + camera perception acting on physical looper and DSP).
5. [x] **Best Hardware** (Arduino footswitch + camera + Scarlett Solo + guitar; failsafe bypass).

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
