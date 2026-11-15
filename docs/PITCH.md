# Pitch plan — OmniRiff

The talk track, openers by track, prepared answers, and the rehearsal plan for Sunday's judging (in person, **max 2 minutes**, 3+ judges per team, finalists present again). The beat-by-beat table and the failure table live in [DEMO.md §3–4](DEMO.md). This file covers *how we say it*. Facts and numbers come only from [DEVPOST.md](DEVPOST.md), [QA.md](QA.md) and measured runs; **no bracket is said out loud as a number.**

## What judges reward (sources, briefly)
- **A live, end-to-end run beats ambition.** A working demo removes doubt; slides don't. One complete path, shown working, wins over many features. ([dev.to: what judges actually score](https://dev.to/kurbaitaev/what-judges-actually-score-notes-from-a-year-of-hackathon-judging-3p4l), [AngelHack](https://angelhack.com/blog/10-tips-to-help-you-rock-your-next-hackathon-demo/))
- **Open with what it *is*, not market size or a long backstory.** The first 30 seconds largely set the score; rehearse them aloud. (dev.to)
- **A one-line identity** is what a judge remembers when ranking 30 teams later. (dev.to)
- **Name a specific weakness.** Honesty about limits raised scores; "nothing breaks" lowered them. (dev.to)
- **Expect:** *Who is this for, specifically? What did you build during the event? What breaks first?* (dev.to)
- **Plan the failure:** switch to the recorded backup, say what should happen, and resume live if it recovers. Walk the demo several times, hunting for where it breaks. ([Reskilll](https://blogs.reskilll.com/hackathon-demo-presentation-tips-pitch-3-minutes-win-2026/))
- **Not worth demo time:** stack and framework choices, polish beyond readable, slide decks (one screenshot as fallback). (dev.to)
- **Pick the clearest speaker,** not the most senior. ([Reskilll](https://blogs.reskilll.com/how-to-win-a-hackathon-15-tips-from-92000-team-registrations/))

## The identity line (memorize it)
> **OmniRiff is a guitar teacher that lives in your signal chain: it hears and sees you play, finds why you stumbled, and sets up the drill, without you ever putting the guitar down.**

Short form for the end: **"Never put the guitar down."**

## The 2-minute talk track (v3, SM's, with who says what)
Replaces the v2 table (identity first, one speaker). SM leads and owns the product/AI narration; Aditya performs the practice journey; John and Angelo each get one short line **over their feature working**. Each person replaces the suggested words with their own. **Not a locked script.** Time it against the real rig; the target is **≤1:50**, and the two-voice fallback in *Roles* below is the answer if the live coach needs the time. The [official rules](https://hackprinceton-fall-26.devpost.com/rules) cap judging at two minutes.

Rules kept from v2: say every number from the screen, never from memory. If the coach isn't on the real rig, run the scripted session and **say "this is our simulator"**, then show the live instrument (DEMO.md §3 fallback). The identity line above is still how SM opens.

### Four-voice table (first pass, ~1:53)

| Clock | Who / action | Suggested words |
| --- | --- | --- |
| 0:00–0:08 | **SM** opens. Aditya already has the guitar sounding. | “This is OmniRiff: a guitar teacher you play *through*. Aditya can ask for help without ever putting the guitar down.” |
| 0:08–0:18 | **Aditya** gives Riff the goal while a teammate holds on-screen TALK or **V**. This is the current microphone path, not a pedal-voice demo. | To Riff: “I'm working on this G-to-C change. I keep losing the rhythm right here.” **Aditya: replace with a passage you really play and words that sound like you.** If speech recognition is unreliable, omit this beat and let Riff infer a timing goal from the first take; do not imply it inferred the chord name. |
| 0:18–0:25 | **Aditya** shows the rig as he starts the first take. | To judges: “This pedal records my take. My hands stay on the guitar.” **Aditya: choose the hardware detail you actually want to own.** |
| 0:25–0:36 | **SM** narrates the first take; Aditya plays a deliberate hesitation. | “Watch the change—he hears that something slipped, but that isn't yet an explanation.” |
| 0:36–0:44 | **John** over the visible hand/pinch moment. | “The camera tracks his hand. Pinch to sweep; release to lock the tone while playing.” **John's agent verified this for the `--relative` path; use it only if that is the rehearsal setup. John should still make it his own.** |
| 0:44–0:52 | **Angelo** over guitar still sounding and engine state moving. | “The guitar stays on this laptop, not in the AI. Our engine keeps playing while Riff thinks.” **Angelo: pick the exact point you can prove live.** |
| 0:52–1:18 | **SM** takes the center as Riff analyzes. Show plan, Ears/Eyes, marked loop and drill. | “Now Riff listens back. Ears finds where the timing breaks. If the camera caught his hand, Eyes can show what happened there too. The important part isn't a score—it's the next move. Riff points to that moment, chooses one drill, and sets up the practice.” Use the **specific finding actually shown**, not a rehearsed diagnosis. If Eyes has no usable hand evidence, say only what Ears found. |
| 1:18–1:31 | **SM** narrates approval; Aditya holds the pedal (or a teammate presses Y on the dashboard) to approve, then he clears the old loop and records a fresh correction take. Pedal-hold approval is merged (#165) but not yet rehearsed on the real rig; use dashboard Y as the fallback. | “Riff asks before changing the rig. We approve, then Aditya records a fresh take with one thing to focus on.” Only say “it changed the sound” when the state confirms it. Do not call this an overdub or claim he recorded over the playing loop. |
| 1:31–1:41 | **SM** on result or next step. | If a genuine before/after is visible: “The first take had **[read value from screen]**; this one has **[read value]**. There's the next step.” Mention memory only if the final NEXT TIME card has actually appeared. If the comparison hasn't finished: “That's the practice loop: hear it, see it, fix one thing, play again.” Do not invent a result to fill the clock. |
| 1:41–1:49 | **Aditya** gives the guitarist's meaning. | “For me, that's the difference: it doesn't just say I missed it. It shows me what to fix.” **Aditya: make this genuinely yours; give us the specific frustration you recognize.** |
| 1:49–1:53 | **SM** closes. | “A teacher in your signal chain. **Never put the guitar down.**” |

This is deliberately **not** four equal speeches. SM carries the through-line;
the other voices appear where they add proof. If the coach needs more time,
move John and Angelo's lines to Q&A/sponsor-judge openers and let Aditya keep
only the goal and one authentic closing line. Do not speed-read to hit 2:00.

### SM's delivery notes

- Lead with the product in one sentence, not a stack list. Use “watch” and
  “now” to point to what a judge can see or hear *at that moment*.
- Make the AI the turn in the story: **a mistake → evidence → one reason → one
  drill → player approval → another take**. “The important part isn't a score—
  it's the next move” is the line to test in rehearsal.
- Keep a calm sentence ready for a slow agent: “The guitar is still playing
  locally while Riff thinks.” Do not narrate a result before it arrives.
- Current controls are **tap = loop**, **long hold = practice**, and **V / TALK
  = voice**. A long pedal hold does not activate the microphone. From a playing
  loop, one tap clears it and the next starts a new recording. Since #165 a
  loop tap or new recording no longer approves a pending change; a **pedal hold**
  (or Y on the dashboard) does. Rehearse the hold on the real rig before relying
  on it; keep Y as the fallback.
- The closing should be earned by Aditya still holding/playing the guitar,
  rather than by an isolated logo screen.

## Openers by track (≈20–30 s, added for sponsor judges)
Use after the identity line when the judge is there for a special track. Full angles are in [DEVPOST.md](DEVPOST.md#track-angles-20-seconds-each-on-top-of-the-shared-demo).
- **LangChain deepagents:** "Riff is a deep agent. That's its plan on screen. It hands the take to two subagents, Ears for timing and Eyes for the hand, drills are skills, the journal and player memory live on its filesystem, and holding the pedal is the human-in-the-loop approval before it touches the rig." Point at the live trace.
- **Amazon Practical AI:** "Who it's for: guitarists practising alone between lessons, and players with limited dexterity, for whom knobs and precise stomps are a barrier. It's agentic (acts on the rig), adaptive (remembers you), and needs no typing."
- **Best Physical AI:** "It perceives through a camera and the guitar cable, then *acts* on a physical rig: looper, effects, recording. It always waits for the player to hold the pedal (or press Y)."
- **Best Hardware:** "Footswitch, webcam, audio interface and guitar on one real-time engine. Unplug anything mid-song and the music keeps playing." Do it.
- **Entertainment & Media (main):** "Practice becomes a duet: the teacher plays the rig for you while your hands stay on the strings."

## Prepared answers (≤20 s each; fuller versions in QA.md)
- **Who is it for, specifically?** Guitarists practising alone between lessons, or who can't afford weekly lessons; and players with limited dexterity. We haven't run user studies, and we say so.
- **What did you build this weekend?** Everything in the repo. It was created after the 8 PM Friday start; the pretrained hand model (MediaPipe) and open-source libraries are disclosed. AI coding agents wrote much of the code under our direction and review, coordinating through a GitHub issue board with CI-gated PRs.
- **What breaks first?** Pick the true one after the hardware run. Candidates: tracking in poor light, latency on this laptop, an intended rest read as a hesitation, a noisy input floor (Ears recall halves at a −30 dBFS noise floor in our tests).
- **How do you know the diagnosis is right?** Every claim comes from a measured number: Ears' gaps from the audio, Eyes' stalls from the hand. No number, no claim.
- **Why not just a metronome app?** It scores timing; it can't see *why* (the hand), set up the drill on your rig, or wait for your foot.
- **Can the AI wreck my sound mid-song?** No. It proposes; nothing happens until you tap. Every action passes the same validation gate as the pedal, and bypass is always yours.
- **Latency?** Only the measured number from `tools.measure` (runs/measure/*/results.md), or "not measured yet".

## Roles (proposed by SM 2026-11-15; pending each person's OK and rehearsal timing)
- **Speaker / narration and close:** SM
- **Guitarist / the user journey:** Aditya: plays, talks to Riff, uses the pedal and pinch; one authentic guitarist line, plus the hardware explanation for the Hardware judge
- **Gesture explanation:** Joey
- **Audio engine explanation:** Angelo
- **Rig operator:** ___ (dashboard, camera, backup video on a second tab)

Timing caution: four voices in 2 minutes costs seconds at every handoff, and judges remember one clear speaker. In the main 2-minute run, keep it to **SM narrating + Aditya playing (one line)**. Joey and Angelo each get at most one ≤10 s line over the matching action, and own the gesture and audio questions in Q&A and in the sponsor-track openers (Physical AI / Hardware). Rehearse both versions and keep whichever fits under 1:50.

## Rehearsal plan (Saturday night after the rig works, then Sunday morning)
1. **Five timed run-throughs** at the table, stopwatch on; cut words until every run is ≤1:50.
2. **Say the first 30 seconds aloud ten times** until they're automatic.
3. **Failure drills, once each:** camera unplugged, pedal dead, coach slow or out of credit, guitar dead → switch to the labeled backup video ("Let me show you the recorded run while we fix this"), then resume live.
4. **Q&A drill:** a teammate fires the seven questions above in random order; answer each in ≤20 s.
5. **Per-track drill:** deliver each sponsor opener once in front of a teammate.
6. **Before each judge:** engine running, dashboard on the coach column, a fresh loop cleared, backup video cued in a second tab, guitar in tune. Run `python -m tools.tablecheck` (Windows: `.\scripts\windows\tablecheck.ps1`) before the manual stage reset; it never clears loops or sends controls.

## Assets (owners on issue #1)
- Labeled **coach-session backup video** ≤2 min (simulated guitar + scripted coach, visibly labeled) for the table and the Devpost fallback.
- **Devpost gallery:** a dashboard mid-session, the hand view, the evidence timeline, an architecture diagram. Simulated captures labeled as such.
- **Real-rig video** recorded after hardware bring-up. Preferred over the backup for Devpost if it works.
- **One screenshot** on the laptop as the last-resort fallback.

## Optional product video: SM's storyboard (for docs/VIDEO.md)

Target **75–100 seconds**, recorded from a real rig only after hardware
rehearsal. Use the same opening, user journey, AI turn and closing; edit the
waiting and playing passages, not the evidence. Suggested shot sequence:

1. **Wide / 3–5 s:** Aditya with guitar and the physical rig in frame; SM's
   opening as voiceover. Establish that this is a person playing an instrument.
2. **Medium + screen / 8–12 s:** Aditya states the goal through the current
   TALK control (or Riff infers a timing-only goal from the take), then plays the
   intentional stumble. Capture his natural reaction without staged claims
   about real users or personal history he has not endorsed.
3. **Pedal/hand inserts / 8–12 s:** close-up pedal tap and pinch; John and
   Angelo's short explanations over their corresponding real actions.
4. **Dashboard capture / 25–35 s:** Riff plan, Ears/Eyes evidence, marked
   moment, approval, a cleared loop and a fresh correction take. SM narrates the cause and next
   step. Use an *actual* response, and show only measurements produced in
   that recorded session. If multiple takes are edited together, caption it
   “edited real session”; don't imply one uninterrupted instant response.
5. **Aditya + result / 10–15 s:** he says, in his own words, what changes for
   him as a guitarist. Cut to the actual next-step/result card, then SM closes.

Capture guitar directly from the interface and speech separately. Screen-
record the dashboard and film a wide view plus short hand/pedal inserts; a
single phone can shoot inserts after the wide take if they accurately depict
the same working action. No need for four talking-head cuts. Keep text large
enough to read on a laptop. Do not publish raw private takes, credentials or
hardware identifiers. The short, visibly **SIMULATED** coach backup is a
separate 35–45-second fallback, not a substitute for a real-rig product video.

### Inputs needed before this becomes the final script

- **Aditya:** the passage he can reliably play with a deliberate pause; the
  practice frustration he would *actually* say; whether the goal/closing lines
  are natural for him; the hardware detail he most wants to own.
- **John:** which exact pinch/gesture action is stable in the room's lighting,
  and a shorter line he would say while demonstrating it.
- **Angelo:** the audio-path/safety fact he can show on the rehearsal laptop,
  and a shorter line he would say while it is audible.
- **SM:** which opening/AI/closing phrasing sounds most like him, and whether
  he wants Aditya's guitarist reflection before or after the measured result.
- **All:** actual coach timing; whether the hand evidence appears; whether
  approval matches the dashboard; which clip can be truthfully recorded.
  The Windows `start-demo.ps1 -Coach` wrapper now passes a shared hand log when
  the model is present (#155), but its first PowerShell/live launch is still
  unverified. Say Riff *saw* the hand only when that run shows usable evidence;
  Ears-only narration is the safe default otherwise.

Until the hardware and UI handoff, this is a rehearsal draft, not a claim that
the complete sequence has been demonstrated live.
