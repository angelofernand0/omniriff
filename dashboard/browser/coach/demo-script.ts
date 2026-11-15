/**
 * Riff's lines for the demo coach (docs/PITCH.md, "Demo coach"). Two sentences each, Riff's voice
 * (BRAND_SPEC.md §7). `ms` is the spoken length of the pre-rendered clip
 * (tools/showcase/demo_voice.py writes it), used to wait for Riff to finish before the next beat.
 */
export const SEED_MEMORY = 'Your chord changes were dragging; leading with the ring finger fixed them.';
export const DEMO_MEMORY = 'Phrase 3 was straight with uneven attacks; swinging it evened your timing.';

export const LINES = {
  freePlay: { text: "Free play, I'm just listening. Press Y or hold the pedal when you want to practice with me.", ms: 5550 },
  welcomeBack: { text: 'Welcome back, last time leading with your ring finger fixed those changes. What are we working on today?', ms: 6760 },
  welcomeBackSwing: { text: 'Welcome back, last time swinging the third phrase evened out your timing. Want to warm up there?', ms: 6060 },
  whatGoal: { text: "What are you working on? Hold TALK or type it, then play.", ms: 3880 },
  goalTiming: { text: "Timing, got it, and your changes are clean now, so let's find where the beat slips. Tap the pedal, play the riff, then tap again.", ms: 9080 },
  listenBack: { text: 'Okay, let me listen back to that.', ms: 2720 },
  diagnosis: { text: "It's the third phrase. You're playing it straight and your attacks jump around, so swing it, long-short, and hit every strum the same.", ms: 8100 },
  askEffectsOff: { text: "I'll take the effects off so you can hear your attacks. Thumbs-up or hold the pedal if that's okay.", ms: 5600 },
  effectsOff: { text: "Effects off. Loop the third phrase with that swing, and tap the pedal when you're ready.", ms: 5970 },
  keepSound: { text: "No problem, we'll keep your sound. Loop the third phrase with that swing, and tap when you're ready.", ms: 6290 },
  result: { text: "Nice, that's the swing. Your attacks are way more even, and the third phrase sits in the pocket now.", ms: 6760 },
  handBack: { text: "Effects are back on, pinch the reverb in and make it yours. I'll remember the third phrase for next time.", ms: 6660 },
} as const;

export type LineId = keyof typeof LINES;
