import { describe, it, expect, vi, beforeEach } from 'vitest';
import { DemoCoach, generateCoachReply } from '../../dashboard/browser/coach/demo-coach';

describe('generateCoachReply', () => {
  it('generates contextual AI replies for various guitar practice topics', () => {
    expect(generateCoachReply('I want to work on my speed')).toContain('speed and tempo');
    expect(generateCoachReply('Help with timing and rhythm')).toContain('timing and rhythm');
    expect(generateCoachReply('Chord transitions are clunky')).toContain('finger placement and smooth transitions between chords');
    expect(generateCoachReply('Strumming attack is uneven')).toContain('wrist loose and aim for consistent attack');
    expect(generateCoachReply('Clean tone without string buzz')).toContain('Dialing in your tone');
    expect(generateCoachReply('Work on solo and lead phrasing')).toContain('phrasing and melodic flow');
    expect(generateCoachReply('practice song 2')).toContain('updated your goal');
  });
});

describe('DemoCoach conversational goal updates', () => {
  let mockManager: any;

  beforeEach(() => {
    mockManager = {
      onState: vi.fn(),
      live: {
        tracker: {
          onAllHands: null,
        },
      },
      simulator: {
        choreography: { enabled: true },
        hand: { present: true },
      },
      sendControl: vi.fn(),
    };
  });

  it('sets initial goal and transitions to take1 on first voice input', async () => {
    const coach = new DemoCoach(mockManager, true);
    const delivered: any[] = [];
    const socket = coach.socketFactory() as any;
    socket.onmessage = (ev: { data: string }) => {
      delivered.push(JSON.parse(ev.data));
    };
    await new Promise(resolve => setTimeout(resolve, 10));

    coach.fromPlayer({ type: 'coach.say', text: 'Master the opening lick' });

    const frames = delivered.filter(m => m.type === 'coach.frame');
    expect(frames.length).toBeGreaterThan(0);
    const lastFrame = frames[frames.length - 1];
    expect(lastFrame.session?.goal).toBe('Master the opening lick');
    expect(lastFrame.cue).toContain("Tap the pedal");
  });

  it('updates goal and replies conversationally when player talks with V again', async () => {
    const coach = new DemoCoach(mockManager, true);
    const delivered: any[] = [];
    const socket = coach.socketFactory() as any;
    socket.onmessage = (ev: { data: string }) => {
      delivered.push(JSON.parse(ev.data));
    };
    await new Promise(resolve => setTimeout(resolve, 10));

    // First voice input
    coach.fromPlayer({ type: 'coach.say', text: 'Get my timing right' });
    expect(delivered.some(m => m.cue?.includes("Tap the pedal"))).toBe(true);

    // Second voice input (updating goal after the first time)
    coach.fromPlayer({ type: 'coach.say', text: 'Actually I need to practice chord transitions' });

    const frames = delivered.filter(m => m.type === 'coach.frame');
    const latestFrame = frames[frames.length - 1];
    expect(latestFrame.session?.goal).toBe('Actually I need to practice chord transitions');
    expect(latestFrame.cue).toContain('finger placement and smooth transitions between chords');
    expect(latestFrame.state).toBe('speaking');
    expect(latestFrame.mood).toBe('encouraging');
    expect(latestFrame.activity.some((a: any) => a.what === 'write /journal/goal.md')).toBe(true);
  });
});
