# Submission and demo checklist

These rules are summarized from the HackPrinceton Fall '26 on-site hacker packet. If anything conflicts, the organizers' Discord announcements and live schedule win. Angelo owns the Devpost submission.

## Deadlines (Eastern time)

| When | What |
|---|---|
| Sun Nov 15, **8:00 AM** | Devpost submission closes. Hard deadline: https://hackprinceton-fall-26.devpost.com/ |
| Sun ~8:00 AM | Table numbers and locations posted on Discord |
| Sun 9:30 AM – 2:30 PM | Judging. **The in-person demo is required**, max **2 minutes**. 3 judges per team, more if we enter special tracks. Lunch only after 3 main-track judges. Finalists get a second round. |

Our own targets, to leave slack: feature freeze **4:00 AM**, demo rehearsal and backup recording by **6:00 AM**, Devpost submitted by **7:00 AM**.

## Eligibility

- [x] Public GitHub repo created after the 8 PM Friday start: `angelofernand0/omniriff` was created at 9:18 PM ET Nov 13. **Do not submit the old `hackprinceton-2026` repo.** It's private and was created before the start.
- [x] Team of at most 4: Angelo, SM, Joey, Aditya. Nobody else can join.
- [ ] Everyone's **Discord username** is on the Devpost submission (organizers contact winners there).

## Tracks (Angelo, 2026-11-14: enter as many as we can credibly win)

**Timeline:** all software and most of the pitch must be done by **8 PM Saturday**, when Aditya is back and hardware bring-up starts. Hardware runs 8 PM onwards, then a full rehearsal, then Devpost by **8:00 AM Sunday**.

| Track | Status | What we must show | Owner |
|---|---|---|---|
| Main: **Entertainment & Media** | Entering, unless Angelo switches to Education (SM's suggestion; open) | A live instrument and performance demo | Angelo |
| **Best Physical AI Hack** ($500) | Entering | Off-the-shelf hand-landmark model → gesture control of a physical guitar rig, live at the table. Describe the model honestly (pretrained MediaPipe + our mapping) | Joey (vision), Angelo (integration) |
| **Best Hardware Hack** | Entering | Pedal (Arduino/Grove) + camera + Solo working live | Aditya (hardware) |
| **LangChain: Best use of deepagents** | Entering | A working deep agent (the practice coach, docs/COACH.md) that plans and acts between takes; the instrument never waits on it | SM |
| **Amazon: Best Practical AI Innovation** | Entering | Their list explicitly includes accessibility tools using voice/vision/gesture. Needs a working prototype, a clear use case and target user (players with limited mobility or dexterity; hands-busy musicians), basic docs and a pitch. Judged on creativity, usefulness, technical quality and UX | Angelo (pitch), everyone (prototype) |
| **Photon messaging agent** | Stretch, only if the coach lands early | Coach sends a practice summary or drill by message; needs a Photon beta signup by a human | SM, if time |
| **ChatOverflow agent leaderboard** | Waiting on Angelo's explicit OK | No project work; connects our coding agents to an outside network that shares agent-written insights | — |
| CoStar, Capital One Nessie, Arlequin, Peri | Skipping | No fit, or (Peri) needs a real business consulted with evidence | — |

Every special track adds judge visits. Prepare a **20-second track-specific angle** for each (in DEVPOST.md) on top of the shared 2-minute demo. Don't enter a track whose requirement isn't working by 7 AM Sunday.

## Judging criteria and our answer

| Criterion | What OmniRiff shows |
|---|---|
| Creativity | Live guitar shaped by a deliberate hand gesture and a foot pedal, without stopping playing |
| Utility | A real-time instrument that keeps playing if the camera, pedal or dashboard drops (manual bypass). Show measured latency, not targets. |
| Charity | Accessibility: control effects without taking your hands off the instrument or bending to small knobs. Useful for players with limited mobility or dexterity. **Don't claim user testing we didn't do.** |
| Avidity | Play it live and well. Polished Devpost page, plus clear next steps. |

## Devpost page

- [ ] Name, tagline, cover image
- [ ] Sections: inspiration, what it does, how we built it, challenges, accomplishments, what we learned, what's next
- [ ] Built with: Python, numpy, scipy, sounddevice/PortAudio, the vision model actually used (e.g. MediaPipe), Arduino, plus anything else actually used
- [ ] Repo link, plus the video link (optional, ≤2 min, uploaded to YouTube or similar)
- [ ] Disclosures:
  - the board helper adapted from azizu06/hackathon-agent-board
  - Freeverb public-domain tunings
  - third-party models and libraries
  - AI coding agents used
  - any synthetic or replayed audio, labeled as such
- [ ] Measured numbers only (latency, event rate), each with how it was measured
- [ ] Track selections match the list above
- [ ] Discord usernames for all four members

## Demo table kit

- [ ] Windows 11 laptop and charger, plus a power strip
- [ ] Scarlett Solo (3rd gen) and its USB cable
- [ ] Guitar and instrument cable (spare if possible)
- [ ] **Judges must hear it:** a small powered speaker or amp on the Solo's line outs, or a headphone splitter with 2+ headphones
- [ ] Webcam (borrowed from MLH or a laptop camera), positioned and lit as calibrated
- [ ] Arduino + Grove shield + buttons (borrowed from MLH) on its USB cable, flashed with `firmware/arduino/Footswitch`
- [ ] Laptop or second screen for the dashboard (optional)

## Before each judge

1. Plug in the Solo with **Direct Monitor off**, INST on, and the guitar in input 2.
2. Start the engine (`python -m engine` once it lands; until then `python -m audio --in Focusrite --out Focusrite --hostapi WASAPI --input-channel 2`). Check the levels, then the `b`, `l`, `f` and `r` keys.
3. Start vision and check that the clutch gesture moves the filter and that strumming doesn't.
4. Press both pedal switches once.
5. If anything fails, play on with the keyboard controls and say so. The backup recording is labeled as playback.

## 2-minute script

See the demo plan in [ARCHITECTURE.md](ARCHITECTURE.md): about 15 s problem (accessibility angle), 25 s dry guitar, 25 s pedal loop/bypass, 30 s gesture sweep (and reverb), 15 s dashboard if ready, 10 s how it stays reliable plus one honest limitation. Rehearse it to time at least twice.
