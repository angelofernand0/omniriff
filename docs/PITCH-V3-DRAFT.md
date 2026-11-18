# OmniRiff pitch v3 — working draft for the four humans

**Not a locked script.** SM asked for a product-led, upbeat demo in the voice of
his NouriSync pitch: introduce a person, show a real action, narrate what
changes, then land why it matters. Aditya performs the practice journey and
speaks to Riff; SM is the lead narrator and owns the AI/product explanation.
John (Joey) and Angelo each get a short line **over their feature working**,
not an engineering appendix. Each teammate should replace the suggested line
with words they would naturally say. Time the result against the *actual* rig.

The [official rules](https://hackprinceton-fall-26.devpost.com/rules) cap the
in-person judging presentation at two minutes. This four-voice pass maps to
**1:53**, leaving little margin; the rehearsal goal is **≤1:50**, and the
two-voice fallback below should be used if the live coach needs that time. The optional uploaded video has its own two-minute
cap and does not replace the live presentation.

## Live table: four-voice candidate (first pass, ~1:53)

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

## Optional product video: adapt the same story, don't reread the table pitch

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

## Inputs needed before this becomes the final script

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
