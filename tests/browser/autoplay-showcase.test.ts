import { afterEach, describe, expect, it, vi } from 'vitest';
import { AutoplayShowcase } from '../../dashboard/browser/coach/autoplay-showcase';

function setup() {
  let onState: (frame: any) => void = () => {};
  let onConnection: (info: any) => void = () => {};
  let onModeChange: (info: any) => void = () => {};
  const manager: any = {
    activeMode: 'simulator',
    onState: vi.fn(cb => { onState = cb; }),
    onConnection: vi.fn(cb => { onConnection = cb; }),
    onModeChange: vi.fn(cb => { onModeChange = cb; }),
    sendControl: vi.fn(() => true),
  };
  const showcase = new AutoplayShowcase(manager);
  const messages: any[] = [];
  const socket = showcase.socketFactory() as any;
  socket.onmessage = (event: { data: string }) => messages.push(JSON.parse(event.data));
  vi.advanceTimersByTime(0);
  return {
    manager, showcase, messages,
    setLoop: (state: string) => onState({ loop: { state } }),
    disconnect: () => onConnection({ status: 'stopped' }),
    switchMode: (mode: string) => { manager.activeMode = mode; onModeChange({ mode }); },
  };
}

describe('AutoplayShowcase', () => {
  afterEach(() => { vi.useRealTimers(); });

  it('runs two actual browser loop takes and publishes explicitly scripted, read-only coach frames', () => {
    vi.useFakeTimers();
    const { manager, showcase, messages, setLoop } = setup();
    showcase.start();
    expect(messages.at(-1).scripted).toBe(true);
    expect(messages.at(-1).session_id).toMatch(/^showcase-/);
    vi.advanceTimersByTime(7000);
    expect(manager.sendControl).toHaveBeenCalledWith('loop');
    setLoop('recording');
    vi.advanceTimersByTime(7500);
    expect(manager.sendControl).toHaveBeenCalledTimes(2);
    setLoop('playing');
    vi.advanceTimersByTime(15500);
    expect(messages.at(-1).awaiting_approval).toBeTruthy();
    vi.advanceTimersByTime(6000);
    expect(manager.sendControl).toHaveBeenCalledWith('bypass');
    expect(messages.at(-1).awaiting_approval).toBeNull();
    vi.advanceTimersByTime(4500);
    expect(manager.sendControl).toHaveBeenCalledTimes(4); // first start/finish, then clear
    setLoop('idle');
    vi.advanceTimersByTime(2000);
    expect(manager.sendControl).toHaveBeenCalledTimes(5); // second start
    setLoop('recording');
    vi.advanceTimersByTime(7500);
    expect(manager.sendControl).toHaveBeenCalledTimes(6); // second finish
    setLoop('playing');
    vi.advanceTimersByTime(6500);
    expect(messages.at(-1).before_after.worst_gap_ms).toEqual([118, 31]);
    expect(messages.every(m => m.scripted === true)).toBe(true);
    const firstSession = messages[0].session_id;
    vi.advanceTimersByTime(19500);
    expect(messages.at(-1).session_id).not.toBe(firstSession); // unattended repeat
    expect(messages.at(-1).before_after).toBeNull();
  });

  it('stops all scheduled controls on disconnect or source change', () => {
    vi.useFakeTimers();
    const { manager, showcase, disconnect, switchMode } = setup();
    showcase.start();
    disconnect();
    vi.advanceTimersByTime(80000);
    expect(manager.sendControl).not.toHaveBeenCalled();
    showcase.start();
    switchMode('live');
    vi.advanceTimersByTime(80000);
    expect(manager.sendControl).not.toHaveBeenCalled();
  });
});
