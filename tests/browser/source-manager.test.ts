import { describe, it, expect, vi } from 'vitest';
vi.mock('../../dashboard/browser/adapters/browser-live', () => ({ BrowserLiveAdapter: class {} }));
vi.mock('../../dashboard/browser/adapters/browser-simulator', () => ({ BrowserSimulatorAdapter: class {} }));
vi.mock('../../dashboard/browser/adapters/python-bridge', () => ({ PythonBridgeAdapter: class {} }));
import { SourceManager } from '../../dashboard/browser/source-manager';

function fake(label: string) {
  let state = (_: any) => {}, hand = (_: any) => {}, connection = (_: any) => {};
  return { modeLabel: label, start: vi.fn(async () => { connection({ status: 'connected' }); }),
    stop: vi.fn(async () => { connection({ status: 'stopped' }); }),
    onState: (cb: any) => { state = cb; }, onHand: (cb: any) => { hand = cb; },
    onConnection: (cb: any) => { connection = cb; },
    emitState: (frame: any) => state(frame), emitHand: (frame: any) => hand(frame),
    emitConnection: (info: any) => connection(info), sendControl: vi.fn(() => true), clearLoop: vi.fn() };
}
function fixture() {
  const simulator = fake('SIMULATED'), live = fake('LIVE'), python = fake('PYTHON');
  const manager = new SourceManager({ simulator, live, python } as any);
  return { manager, simulator, live, python };
}
const flush = async () => { for (let i = 0; i < 6; i++) await Promise.resolve(); };

describe('SourceManager lifecycle', () => {
  it('serializes transitions, skips superseded requests and drops inactive callbacks', async () => {
    const { manager, live, simulator, python } = fixture();
    let finish!: () => void;
    live.start.mockImplementation(() => new Promise<void>(resolve => { finish = resolve; }));
    const states: any[] = [], hands: any[] = [], connections: any[] = [];
    manager.onState(frame => states.push(frame)); manager.onHand(frame => hands.push(frame));
    manager.onConnection(info => connections.push(info));
    const first = manager.setMode('live'); await flush();
    live.emitState({ version: 1 }); expect(states).toHaveLength(0);
    const second = manager.setMode('simulator'); const last = manager.setMode('python');
    finish(); await Promise.all([first, second, last]);
    expect(live.stop).toHaveBeenCalledOnce(); expect(simulator.start).not.toHaveBeenCalled();
    expect(python.start).toHaveBeenCalledOnce(); expect(manager.activeMode).toBe('python');
    live.emitState({ old: true }); live.emitHand({ old: true }); live.emitConnection({ status: 'error' });
    python.emitState({ current: true });
    expect(states).toEqual([{ current: true }]); expect(hands.some(f => f.old)).toBe(false);
    expect(connections.at(-1)).toMatchObject({ mode: 'python', status: 'connected' });
  });
  it('cleans failed starts and permits retry of the same mode', async () => {
    const { manager, simulator } = fixture(); const connections: any[] = [];
    manager.onConnection(info => connections.push(info));
    simulator.start.mockRejectedValueOnce(new Error('worklet unavailable'));
    await expect(manager.setMode('simulator')).rejects.toThrow('worklet unavailable');
    expect(simulator.stop).toHaveBeenCalledOnce(); expect(manager.currentAdapter).toBeNull();
    expect(manager.sendControl('loop')).toBe(false);
    expect(connections.at(-1)).toMatchObject({ mode: 'simulator', status: 'error' });
    await manager.setMode('simulator'); expect(manager.sendControl('loop')).toBe(true);
  });
  it('stop invalidates an outstanding start and prevents late mode/frame notifications', async () => {
    const { manager, live, simulator } = fixture(); let finish!: () => void;
    live.start.mockImplementation(() => new Promise<void>(resolve => { finish = resolve; }));
    const states = vi.fn(), mode = vi.fn(); manager.onState(states); manager.onModeChange(mode);
    const pending = manager.setMode('live'); await flush(); await manager.stop();
    live.emitState({ late: true });
    expect(states).not.toHaveBeenCalled(); expect(mode).not.toHaveBeenCalled();
    expect(manager.currentAdapter).toBeNull(); expect(manager.activeMode).toBeNull();
    await manager.setMode('simulator'); // old permission acquisition is still unresolved
    expect(simulator.start).toHaveBeenCalledOnce();
    finish(); await pending; expect(manager.activeMode).toBe('simulator');
    expect(simulator.stop).not.toHaveBeenCalled();
  });
});
