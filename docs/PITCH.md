# Pitch plan — OmniRiff

This is the spoken in-person cut, the LangChain-judge swap, and the recording plan. The beat-by-beat/failure runbook is [DEMO.md §3–4](DEMO.md). Only quote facts and numbers from an observed run, [DEVPOST.md](DEVPOST.md), or [QA.md](QA.md); bracketed cues below are **not** spoken aloud.

## The identity line (memorize it)
> **OmniRiff is a guitar teacher that lives in your signal chain: it hears and sees you play, finds why you stumbled, and sets up the drill, without you ever putting the guitar down.**

Short form for the end: **"Never put the guitar down."**

## The two-minute in-person pitch (rehearsal cut)

SM tells the product/AI story; Aditya plays and supplies the guitarist's point of view; John and Angelo get one proof line each. **Aim to finish by 1:50**, leaving ten seconds for a slow screen or handoff. The [official rules](https://hackprinceton-fall-26.devpost.com/rules) cap the in-person presentation at two minutes. Do not add a separate technology introduction before this script.

The planned playing test is the `Em → Cmaj7 → G → Dsus2` progression from Claude's [PR #196 test sheet](https://github.com/angelofernand0/omniriff/pull/196), with the ring finger deliberately landing last. **A seeded synthetic-hand test produced the specific ring-finger diagnosis; a real guitar/webcam has not verified it yet.** The exact diagnosis, before/after result, and chosen approval gesture must be locked from a real rehearsal. Never recite synthetic numbers as live results.

| Clock | Speaker and live action | Say |
| --- | --- | --- |
| 0:00–0:08 | **SM.** Aditya and the guitar are already in view. | “OmniRiff is a guitar teacher for solo practice: it finds why you stumbled and sets up the fix.” |
| 0:08–0:15 | **Aditya.** Guitar, interface and camera in view. Say this to Riff through a rehearsed TALK control; if speech recognition is unreliable, the operator sets the goal and Aditya says it to the judges without claiming Riff heard him. | “Riff, my chord changes feel clunky. What's slowing me down?” |
| 0:15–0:28 | **Aditya.** Record one 10–13 s take with a deliberate late ring finger; stop the take so Riff can analyze it. **SM** points to the visible stumble, then leaves space for the playing. | “Watch this change. You can hear the pause—but the pause isn't the cause.” |
| 0:28–0:34 | **Angelo.** Guitar still audible; show a moving audio meter. | “The guitar keeps playing through the audio path while the coach works between takes.” |
| 0:34–0:40 | **John.** Point to a real hand trace; demonstrate only the gesture mapping that passed the final camera rehearsal. | “The webcam follows his hands, so he can control the rig without reaching for a mouse.” |
| 0:40–0:57 | **SM.** Point to Riff's actual plan and evidence while the agent thinks. | “This is where the teacher takes over. Riff is a LangChain Deep Agent: Ears measures timing, Eyes measures the hands, and it chooses one drill for the cause it found. Not another score—the next move.” |
| 0:57–1:09 | **SM.** Point at the actual cue and drill card. | **If the real run confirms it:** “Riff says his ring finger lands last. So instead of ‘play it again,’ the drill is: lead with that finger.” **If only timing evidence is valid:** “Riff found the late strum and gave him a timing drill. The camera didn't give it enough evidence to name a finger.” |
| 1:09–1:16 | **Aditya** approves by the control verified for this demo—website thumbs-up, local pedal hold, or dashboard button—then clears the old take and starts a fresh one. **SM** narrates. | “Riff asks before changing the rig. Aditya approves, then tries that one correction.” |
| 1:16–1:31 | **Aditya.** Play a fresh 10–15 s correction take. No claim that this is an overdub on the old loop. | *(Let the guitar speak.)* |
| 1:31–1:40 | **SM.** Point to the actual comparison, if ready. | **If measured:** “The gap changed from **[read screen]** to **[read screen]**. That's the practice loop: find the cause, work the fix, check the next take.” **If not ready:** “That's the practice loop: find the cause, work the fix, and check the next take—not just replay the mistake.” |
| 1:40–1:46 | **Aditya.** Keep the guitar in hand; approve the line as genuinely his before the pitch. | “One thing to fix—not just another score. That's what I need when I practise.” |
| 1:46–1:50 | **SM.** | “OmniRiff. Never put the guitar down.” |

This is one story, not four mini-pitches. If the agent or camera needs more time, **drop John's and Angelo's lines first** (they own those points in Q&A), then omit Aditya's final line if needed. Keep the first take, actual feedback, approval and second take; don't speed-read or invent a result. If the live coach is unavailable, visibly label the backup **SIMULATED** or **RECORDED**, say that aloud, and show the live instrument separately. Never describe a website thumbs-up as a pedal tap or the browser audio path as the Python engine.

### LangChain judge swap (same two minutes, not a second pitch)

Keep the same guitarist, mistake, drill and retake. Replace SM's 0:40–0:57 line with: “Riff is built with LangChain Deep Agents. Its plan reads the timing and hand reports together, opens a drill skill, and a memory-keeper subagent saves what matters for next time. Before a rig change, it waits for Aditya's approval.” Point to the live trace and approval state. This is the technical answer **inside** the product story; don't append another 20-second opener on top. Plain report reads are parallel tools on the lead agent; Ears/Eyes subagents are reserved for a confusing report, not invoked for every take. The full proof/limits are in [PITCH-LANGCHAIN.md](PITCH-LANGCHAIN.md). If a trace element is absent, name only what is visible and show the deeper architecture in Q&A.

### Recording cut

Use the same words and speaker assignments for the optional product video. Film a wide shot of Aditya and the rig, a readable screen capture of Riff's actual cue, and short camera/hand/pedal inserts under John and Angelo's lines. Editing may remove waiting time, but caption a stitched run **edited real session** and keep the before/after from that same session. If the take or coach is simulated, keep **SIMULATED** on screen and say it in voiceover. No fabricated reaction, evidence or live-performance claim.

## Sponsor-judge follow-up (Q&A, not extra speech)

For LangChain judges, use the swap *inside* the two-minute script above; [PITCH-LANGCHAIN.md](PITCH-LANGCHAIN.md) has the deeper proof table. Do not add 20 seconds to an already full pitch. Other track angles are short answers if a judge asks; details are in [DEVPOST.md](DEVPOST.md#track-angles-20-seconds-each-on-top-of-the-shared-demo).
- **Amazon Practical AI:** "Who it's for: guitarists practising alone between lessons, and players with limited dexterity, for whom knobs and precise stomps are a barrier. It's agentic (acts on the rig), adaptive (remembers you), and needs no typing."
- **Best Physical AI:** "It perceives through the camera and the guitar audio, then proposes a drill and rig action. The player approves before any sound change." Only say this if that action is visible in the chosen demo path.
- **Best Hardware:** "We built software around an ordinary guitar, audio interface, webcam and footswitch; no custom guitar is required. The audio continues if the camera, pedal, dashboard or coach disconnects—not if the audio interface does." Show only the disconnect rehearsed safely.
- **Entertainment & Media (main):** "Practice becomes a duet: the teacher plays the rig for you while your hands stay on the strings."

## Prepared answers (≤20 s each; fuller versions in QA.md)
- **Who is it for, specifically?** Guitarists practising alone between lessons, or who can't afford weekly lessons; and players with limited dexterity. We haven't run user studies, and we say so.
- **What did you build this weekend?** Everything in the repo. It was created after the 8 PM Friday start; the pretrained hand model (MediaPipe) and open-source libraries are disclosed. AI coding agents wrote much of the code under our direction and review, coordinating through a GitHub issue board with CI-gated PRs.
- **What breaks first?** Pick the true one after the hardware run. Candidates: tracking in poor light, latency on this laptop, an intended rest read as a hesitation, a noisy input floor (Ears recall halves at a −30 dBFS noise floor in our tests).
- **How do you know the diagnosis is right?** Every claim comes from a measured number: Ears' gaps from the audio, Eyes' stalls from the hand. No number, no claim.
- **Why not just a metronome app?** It tells you when you drift. This practice loop uses audio and, when available, hand evidence to propose a specific fix and checks the next take.
- **Can the AI wreck my sound mid-song?** It proposes rig changes and waits for approval through the verified demo control. The audio path stays independent, and manual bypass remains available.
- **Latency?** Only the measured number from `tools.measure` (runs/measure/*/results.md), or "not measured yet".

## Roles and rehearsal
- **Speaker / narration and close:** SM
- **Guitarist / the user journey:** Aditya: plays the intentional stumble and correction, approves the drill through the verified control, gives one authentic guitarist line, and owns hardware questions
- **Gesture explanation:** Joey
- **Audio engine explanation:** Angelo
- **Rig operator:** assign before rehearsal; this person watches the dashboard, starts/clears takes if Aditya cannot do so hands-free, and cues the labeled backup

1. **First timed run:** use the final dashboard and a real guitar/webcam. Confirm camera framing on both hands, whether the finger diagnosis is true, the approved control, coach latency, and whether the retake comparison arrives by 1:40. Ask Aditya, John and Angelo to replace their proposed lines with words they would actually say.
2. **Second timed run:** perform the chosen script without stopping. If it exceeds 1:50, remove John/Angelo's lines; keep the practice loop and Aditya's perspective. Do not compress the guitar takes into inaudible fragments.
3. **One failure drill:** if the coach or camera does not produce valid evidence, use the timing-only line or the labeled recorded/simulated backup. Say which one it is. Keep the instrument path separate from the AI claim.
4. **Before judging:** guitar tuned; chosen dashboard, camera and audio ready; old loop cleared; backup cued; assigned operator knows the controls. Run `python -m tools.tablecheck` (Windows: `.\scripts\windows\tablecheck.ps1`) if using the local rig.

## Assets (owners on issue #1)
- Labeled **coach-session backup video** ≤2 min (simulated guitar + scripted coach, visibly labeled) for the table and the Devpost fallback.
- **Devpost gallery:** a dashboard mid-session, the hand view, the evidence timeline, an architecture diagram. Simulated captures labeled as such.
- **Real-rig video** recorded after hardware bring-up. Preferred over the backup for Devpost if it works.
- **One screenshot** on the laptop as the last-resort fallback.

## Final lock before recording or judging

The spoken words and timing above are ready for rehearsal, not proof that a real-camera diagnosis has worked. Replace only the two evidence branches with the result actually observed; get Aditya's approval for his own lines; confirm the website/local control path and John/Angelo's proof lines. A real-rig run that names the wrong finger means use the timing-only line or a clearly labeled backup—not the synthetic ring-finger cue. Then time one uninterrupted run and freeze the script.

For the recording, capture guitar audio, speech and a readable dashboard separately where possible. Use a wide shot to establish Aditya really playing, and only use hand/pedal inserts that depict the action actually performed. Keep private raw takes, passcodes and hardware identifiers out of public assets.
