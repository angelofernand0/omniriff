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

## The 2-minute talk track (v2, identity first)
The guitarist plays; the speaker talks. Lines are targets, not a script to read. Keep the guitar sounding the whole time.

| Time | Say (≈) | Show |
|---|---|---|
| 0:00–0:10 | "OmniRiff is a guitar teacher that lives in your signal chain. Watch: I'm not going to put this guitar down." | Already playing; dashboard visible; Riff idle |
| 0:10–0:25 | "Practising alone, you know you messed up but not *why*. Apps score notes; a teacher tells you the cause. Lessons cost money every week." | Keep playing; tell Riff the goal (hold V: "my chord changes") |
| 0:25–1:15 | "Here's a take with a real stumble." … "Riff heard a ___-millisecond gap (read it off the screen) *and* saw my strumming hand freeze at the change, so the cause is the hand, not the chord. [Only if the HAND panel shows wrist data for that take; otherwise say: "Riff heard a ___-millisecond hesitation at the change."] It played my take back and set up a drill, and it waits for my foot." **Tap.** Record a fresh drill take (the looper records, plays and clears; no overdub). "This take: the gap is down to ___." | Plan + Ears/Eyes trace on screen; mark on the loop; tap the pedal; before/after numbers |
| 1:15–1:30 | "Next session it starts with *last time*: it remembers what you worked on." | Result card / NEXT TIME line |
| 1:30–1:50 | "Safe by design." Unplug the camera: music keeps playing. "The AI never changes my sound without my tap. Honest limit: ___." | Camera shows offline; audio continues |
| 1:50–2:00 | "Built this weekend by four of us. **Never put the guitar down.**" | Logo / Riff |

Rules: say every number from the screen, never from memory. If the coach isn't on the real rig, run the scripted session and **say "this is our simulator"**, then show the live instrument (DEMO.md §3 fallback).

## Openers by track (≈20–30 s, added for sponsor judges)
Use after the identity line when the judge is there for a special track. Full angles are in [DEVPOST.md](DEVPOST.md#track-angles-20-seconds-each-on-top-of-the-shared-demo).
- **LangChain deepagents:** "Riff is a deep agent. That's its plan on screen. It hands the take to two subagents, Ears for timing and Eyes for the hand, drills are skills, the journal and player memory live on its filesystem, and my foot tap is the human-in-the-loop approval before it touches the rig." Point at the live trace.
- **Amazon Practical AI:** "Who it's for: guitarists practising alone between lessons, and players with limited dexterity, for whom knobs and precise stomps are a barrier. It's agentic (acts on the rig), adaptive (remembers you), and needs no typing."
- **Best Physical AI:** "It perceives through a camera and the guitar cable, then *acts* on a physical rig: looper, effects, recording. It always waits for the player's tap."
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
6. **Before each judge:** engine running, dashboard on the coach column, a fresh loop cleared, backup video cued in a second tab, guitar in tune.

## Assets (owners on issue #1)
- Labeled **coach-session backup video** ≤2 min (simulated guitar + scripted coach, visibly labeled) for the table and the Devpost fallback.
- **Devpost gallery:** a dashboard mid-session, the hand view, the evidence timeline, an architecture diagram. Simulated captures labeled as such.
- **Real-rig video** recorded after hardware bring-up. Preferred over the backup for Devpost if it works.
- **One screenshot** on the laptop as the last-resort fallback.
