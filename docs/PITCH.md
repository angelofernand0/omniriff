# Pitch plan — OmniRiff

This is the spoken in-person cut, the LangChain-judge swap, and the recording plan. The beat-by-beat/failure runbook is [DEMO.md §3–4](DEMO.md). Only quote facts and numbers from an observed run, [DEVPOST.md](DEVPOST.md), or [QA.md](QA.md); bracketed cues below are **not** spoken aloud.

## The identity line (memorize it)
> **OmniRiff is a guitar teacher that lives in your signal chain: it hears and sees you play, finds why you stumbled, and sets up the drill, without you ever putting the guitar down.**

Short form for the end: **"Never put the guitar down."**

## The two-minute in-person pitch (rehearsal cut)

SM tells the product/AI story; Aditya plays and supplies the guitarist's point of view; John and Angelo get one proof line each. **Aim to finish by 1:50**, leaving ten seconds for a slow screen or handoff. The [official rules](https://hackprinceton-fall-26.devpost.com/rules) cap the in-person presentation at two minutes. Do not add a separate technology introduction before this script.

The demo story: **Aditya can't get his timing right.** Riff remembers him, listens to one take, and names the cause: **on the third phrase he plays straight with uneven attacks, so swing it and hit every strum the same.** It sets up the drill, he approves with a thumbs-up, plays it again, and Riff shows the improvement and remembers it. The session runs on the website's **demo coach** (below): the coaching lines and numbers are scripted for this story and react to what Aditya actually does on stage.

| Clock | Speaker and live action | Say |
| --- | --- | --- |
| 0:00–0:08 | **SM.** Aditya, guitar and camera in view; omniriff.vercel.app with the demo coach on the big screen, already started. | “OmniRiff is a guitar teacher that lives in your signal chain: it hears and sees you play, finds why you slipped, and sets up the fix.” |
| 0:08–0:16 | **Aditya** plays the riff freely. Riff greets him from memory: *“Welcome back, last time leading with your ring finger fixed those changes. What are we working on today?”* | **SM:** “Riff already knows him. Last session it fixed his chord changes.” |
| 0:16–0:22 | **Aditya** holds TALK (V) and says it to Riff. Riff: *“Timing, got it… Tap the pedal, play the riff, then tap again.”* | **Aditya:** “Riff, I can't get my timing right.” |
| 0:22–0:34 | **Aditya** taps Record loop, plays the riff about 10 s, taps again. | **SM:** “He just plays. No menus, no metronome app.” |
| 0:34–0:42 | Riff: *“Okay, let me listen back to that.”* Its plan streams in: Ears, Eyes, find the phrase, pick a drill. | **SM:** “Riff is a LangChain Deep Agent. Ears reads the timing, Eyes watches both hands, and it picks one fix, not a score.” |
| 0:42–0:47 | **Angelo.** Guitar still sounding. | “The guitar never stops while Riff thinks, and Riff can't touch the sound without asking.” |
| 0:47–0:57 | Riff marks **3RD PHRASE** on the loop: *“It's the third phrase. You're playing it straight and your attacks jump around, so swing it, long-short, and hit every strum the same.”* | **Aditya:** “That's it. I rush that phrase and dig in on the off-beats.” |
| 0:57–1:05 | Riff: *“I'll take the effects off so you can hear your attacks. Thumbs-up or hold the pedal if that's okay.”* **Aditya** holds a thumbs-up; FX goes OFF. | **John:** “The camera reads his thumbs-up. His hands never leave the guitar.” |
| 1:05–1:22 | **Aditya** clears the loop, records the third phrase with swing and even attacks, taps again. | *(Let the guitar speak.)* |
| 1:22–1:32 | Riff: *“Nice, that's the swing. Your attacks are way more even, and the third phrase sits in the pocket now.”* Before/after on screen. | **SM:** “Timing drift on that phrase: 118 down to 31 milliseconds.” |
| 1:32–1:42 | Riff: *“Effects are back on, pinch the reverb in and make it yours. I'll remember the third phrase for next time.”* **Aditya** pinches the reverb up; the **SAVED TO MEMORY** card files into Riff. | **SM:** “And next time, it starts right here.” |
| 1:42–1:50 | **SM.** | “OmniRiff. Never put the guitar down.” |

If time runs short, drop Angelo's line first, then John's. Keep the take, the diagnosis, the thumbs-up, the second take, and the memory card.

### LangChain judge swap (same two minutes, not a second pitch)

Keep the same guitarist, mistake, drill and retake. Replace SM's 0:34–0:42 line with: “Riff is built with LangChain Deep Agents. Its plan reads the timing and hand reports together, opens a drill skill, and a memory-keeper subagent saves what matters for next time. Before a rig change, it waits for Aditya's approval.” Point to the live trace and approval state. This is the technical answer **inside** the product story; don't append another 20-second opener on top. Plain report reads are parallel tools on the lead agent; Ears/Eyes subagents are reserved for a confusing report, not invoked for every take. The full proof/limits are in [PITCH-LANGCHAIN.md](PITCH-LANGCHAIN.md). If a trace element is absent, name only what is visible and show the deeper architecture in Q&A.

### Recording cut

Use the same words and speaker assignments for the optional product video. Film a wide shot of Aditya and the rig, a readable screen capture of Riff's actual cue, and short camera/hand/pedal inserts under John and Angelo's lines. Editing may remove waiting time, but caption a stitched run **edited real session** and keep the before/after from that same session. If the take or coach is simulated, keep **SIMULATED** on screen and say it in voiceover. No fabricated reaction, evidence or live-performance claim.

## Demo coach (the scripted session on the website)

**Load:** on omniriff.vercel.app, settings → **Riff, the AI coach** → **Start demo session** (or `?coach=demo`). Press Start. Add `&source=live` to use Aditya's real guitar input and webcam (choose the instrument channel in the settings); without it the simulated guitar plays. Add `&fresh=1` for a first visit with no memory.

**What reacts to the room:** the goal Aditya says or types to Riff (any words), each finished loop recording (Record loop / L, real guitar or simulator), and the approval (a held thumbs-up on camera, or Y). Riff's voice is pre-rendered in its ElevenLabs voice (`tools/showcase/demo_voice.py`).

**What is scripted:** every line Riff says, the plan steps, the third-phrase marker (the third quarter of whatever loop he records), the drill, and the numbers (timing drift 118 → 31 ms, stability 0.78 → 0.95). The script is in `dashboard/browser/coach/demo-script.ts` and `demo-coach.ts`. The real coach (settings → Riff, the AI coach, with the passcode) measures the take instead; use it for Q&A or a second run.

**Memory:** the first visit opens with a remembered session (the ring-finger fix). Finishing the demo saves the third phrase, so a reload opens with *“Welcome back, last time swinging the third phrase evened out your timing.”* Use `&fresh=1` to reset before the real pitch.

**Operator checklist (SM):**
1. Before judges arrive: open omniriff.vercel.app, choose Source **Live audio + camera**, and in **Riff, the AI coach** press **Start demo session**, then Start (this grants mic and camera). Before each run press **Reset for the pitch** (settings → Riff), so Riff opens with the remembered ring-finger session. **Leave demo** returns to the normal site. The same as URL flags: `?coach=demo&source=live`; `&fresh=1` = a first visit with no memory.
2. If speech-to-text mishears Aditya, type “I can't get my timing right” in the TALK box. Any words move the script on.
3. If the thumbs-up doesn't register within two seconds, press **Y**.
4. Second take: tap once to clear the old loop, then record. Riff answers when the recording finishes.
5. Click the page once before starting so the browser allows Riff's voice. **M** mutes Riff.

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
