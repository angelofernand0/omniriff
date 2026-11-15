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
  // replies when you talk to Riff after the script (demo-coach.ts replyFor), recorded too so Riff never falls back to a robot voice
  replySpeed: { text: "Got it, shifting focus to speed and tempo. Keep your fretting hand relaxed and let's push the pace on your next take.", ms: 8150 },
  replyTiming: { text: 'Understood, locked in on timing and rhythm. Focus on tight, even attacks right on the beat.', ms: 6200 },
  replyChords: { text: 'Heard loud and clear. Focus on clean finger placement and smooth transitions between chords.', ms: 6010 },
  replyStrum: { text: 'Got it. Keep your wrist loose and aim for consistent attack and dynamic control on every stroke.', ms: 6290 },
  replyTone: { text: 'Dialing in your tone. Keep your notes articulate and focus on muting any unplayed strings.', ms: 6340 },
  replyPhrasing: { text: 'Nice, working on phrasing and melodic flow. Keep your notes deliberate and expressive.', ms: 5920 },
  replyOther: { text: "Got it, I've updated your goal. Show me what you've got on your next take.", ms: 4990 },
} as const;

export type LineId = keyof typeof LINES;
