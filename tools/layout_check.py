"""Measured dashboard layout check (SM, 2026-11-14): never ship UI on eyeballed screenshots.
Loads the dashboard in headless Chrome at 1288x734 (a laptop window), 1280x720, 1440x900 and 1920x1080 and, every STEP s through a session, reports text that overflows its box, readouts that escape their panel, overlapping coach-column parts and page scroll. Needs Google Chrome (macOS path below) and websockets.
  python -m tools.sim run --demo --coach-sim --no-voice --http-port 19001 ...   then
  python tools/layout_check.py "http://127.0.0.1:19001/?ws=...&coachws=..." 34 1.5      # expect TOTAL 0
"""
import asyncio, json, subprocess, sys, time, urllib.request
from websockets.asyncio.client import connect

URL, SECS, STEP = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
SIZES = [(1288, 734), (1280, 720), (1440, 900), (1920, 1080)]
CH = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

PROBE = r"""
(() => {
  const out = [];
  const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity > 0.05; };
  const name = (e) => (e.id ? '#' + e.id : e.className && typeof e.className === 'string' ? '.' + e.className.split(' ')[0] : e.tagName);
  // 1. text that spills out of its own box
  for (const e of document.querySelectorAll('.app *')) {
    if (!vis(e) || e.closest('.drawer') || e.tagName === 'CANVAS' || e.closest('.riff')) continue;
    const s = getComputedStyle(e);
    if (s.overflow === 'visible' && (e.scrollWidth > e.clientWidth + 2 || e.scrollHeight > e.clientHeight + 6) && e.clientWidth > 0 && e.children.length < 6 && e.textContent.trim())
      out.push('OVERFLOW ' + name(e) + ' ' + JSON.stringify(e.textContent.trim().slice(0, 40)));
  }
  // 2. text boxes that leave their panel
  for (const e of document.querySelectorAll('.pct, .spot-cue, .p-read b, .p-drill, .spot-ask, .practice, .booth, .plan, .spot-ba, .loop-word, .fx-power b')) {
    if (!vis(e)) continue;
    const p = e.closest('.card, .coach-col, .loop-state, .fx-power, .practice') ;
    if (!p || p === e) continue;
    const a = e.getBoundingClientRect(), b = p.getBoundingClientRect();
    if (a.left < b.left - 1 || a.right > b.right + 1 || a.top < b.top - 1 || a.bottom > b.bottom + 1)
      out.push('ESCAPES ' + name(e) + ' from ' + name(p));
  }
  // 3. siblings in the coach column that overlap each other
  const col = [...document.querySelectorAll('.coach-col > *')].filter(vis);
  for (let i = 0; i < col.length; i++) for (let j = i + 1; j < col.length; j++) {
    const a = col[i].getBoundingClientRect(), b = col[j].getBoundingClientRect();
    if (a.bottom > b.top + 1 && b.bottom > a.top + 1 && a.right > b.left && b.right > a.left)
      out.push('OVERLAP ' + name(col[i]) + ' / ' + name(col[j]));
  }
  const cue = document.querySelector('.spot-cue');
  if (cue && vis(cue) && cue.scrollHeight > cue.getBoundingClientRect().height + 2) out.push('CLIPPED cue');
  if (document.documentElement.scrollHeight > innerHeight + 1) out.push('PAGE SCROLLS');
  return out;
})()
"""

async def run(w, h, port):
    p = subprocess.Popen([CH, '--headless=new', f'--remote-debugging-port={port}', f'--window-size={w},{h}',
                          f'--user-data-dir=/tmp/omniriff-cdp-{port}', 'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    seen = {}
    try:
        for _ in range(50):
            try:
                tabs = json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/json')); break
            except Exception:
                await asyncio.sleep(0.2)
        pg = next(t for t in tabs if t['type'] == 'page')
        async with connect(pg['webSocketDebuggerUrl'], max_size=2**24) as ws:
            n = 0
            async def call(m, **kw):
                nonlocal n
                n += 1; i = n
                await ws.send(json.dumps({'id': i, 'method': m, 'params': kw}))
                while True:
                    r = json.loads(await ws.recv())
                    if r.get('id') == i:
                        return r.get('result', {})
            await call('Emulation.setDeviceMetricsOverride', width=w, height=h, deviceScaleFactor=1, mobile=False)
            await call('Page.navigate', url=URL)
            t0 = time.time()
            while time.time() - t0 < SECS:
                await asyncio.sleep(STEP)
                r = await call('Runtime.evaluate', expression=PROBE, returnByValue=True)
                st = await call('Runtime.evaluate', returnByValue=True, expression="(window.OmniRiff&&OmniRiff.coach.get().state)||''")
                for issue in r.get('result', {}).get('value') or []:
                    seen.setdefault(issue, st['result'].get('value'))
    finally:
        p.terminate()
    return seen

async def main():
    total = 0
    for k, (w, h) in enumerate(SIZES):
        seen = await run(w, h, 19240 + k)
        total += len(seen)
        print(f'{w}x{h}: {"OK" if not seen else str(len(seen)) + " issues"}')
        for issue, state in seen.items():
            print(f'   [{state}] {issue}')
    print('TOTAL', total)

asyncio.run(main())
