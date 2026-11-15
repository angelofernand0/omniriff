# Play this: a real test of Riff's coaching

For Aditya (or anyone with a guitar). About 10 minutes. The goal is to check that Riff, using the
camera, names the **actual cause** of a late chord change (which finger, when the hand moves)
instead of "keep strumming through it".

## 1. Frame the camera first (this matters most)
- **Both hands in the picture:** the fretting hand on the neck *and* the strumming hand.
- Camera about 1 m away at chest height, a little to the side of the fretboard so the fingertips on the
  neck aren't hidden behind the hand. Neck roughly horizontal in the image.
- Light from the front (a window or lamp behind the camera). No strong light behind you.
- Check: the hand panel (RIG → hand view) shows a skeleton on each hand while you hold a chord.

If only one hand is in view, Riff will say so and teach from timing only. That's correct behaviour, not a bug.

## 2. The riff
`Em → Cmaj7 → G → Dsus2`, then repeat. Four strums per chord: **down, up, down, up**, at a steady medium
tempo (about 2 strums a second). Record a loop of **10–15 seconds** (two times through).

| Chord | Fingers (string: low E = 6 ... high e = 1) |
|---|---|
| Em | middle 5th string fret 2, ring 4th string fret 2 |
| Cmaj7 | ring 5th string fret 3, middle 4th string fret 2 (x32000) |
| G | middle 6th string fret 3, index 5th string fret 2, ring 1st string fret 3 |
| Dsus2 | index 3rd string fret 2, ring 2nd string fret 3 (xx0230) |

## 3. Three takes, three habits (do them on purpose)
Start a session first: type or say "My chord changes feel clunky" (or press Y), then record.

| Take | What to do | What Riff should say (roughly) |
|---|---|---|
| **A. Late finger** | At every change, put your **ring finger down last**, about a quarter second after the others. Keep strumming steadily; let the strum after the change wait for the ring finger. | "Your ring finger lands last in all three changes, about a quarter second behind… put that one down first." Drill: *lead with the last finger*. |
| **B. Late start** | Keep the fretting hand **completely still until after the last up-strum** of each chord, then change quickly. | "Your fretting hand waits for the last strum before it moves… start the change on the last up-strum." Drill: *move on the "and"*. |
| **C. Clean** | Change early (on the last up-strum), all fingers together. | Praise with numbers: the gap and the late finger both smaller. No invented problem. |

After Riff's drill card, **hold a thumbs-up for half a second** (website) or hold the pedal / press Y to
approve. Play the drill take; Riff compares before/after.

## 4. What to report on the board
For each take: what you did, what Riff said, whether that was **true and useful**, and a screenshot of
the coach column. Especially: did it name the right finger? Did it ever claim something it can't see
(which fret, finger height, pick angle)? Did the thumbs-up trigger by accident while playing?

## Reference run (synthetic hands, real coach)
The same three habits are generated in `tools/showcase/hands.py` (`Faults(late_finger="ring", lag_s=0.28)`,
`Faults(start_delay_s=0.25)`, `Faults()`), and `python -m tools.showcase.realrun --scenario late-finger`
drives a whole session through the coach server. That proves the pipeline. Only a real player on a real
camera proves the coaching.
