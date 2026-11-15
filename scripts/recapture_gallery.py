"""Recapture gallery-01-coach.png and gallery-02-hand.png per docs/media/GALLERY.md."""
import asyncio
import base64
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request
import websockets
from PIL import Image
import io

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / 'docs/media'
CHROME_BIN = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

UDP_PORT = 59210
WS_PORT = 59211
HAND_PORT = 59212
COACH_PORT = 59213
HTTP_PORT = 18985
CDP_PORT = 9222


async def get_cdp_page(ws_url):
    return await websockets.connect(ws_url, max_size=20 * 1024 * 1024)


async def evaluate(ws, expr):
    msg_id = int(time.time() * 1000) % 1000000 + 100
    await ws.send(json.dumps({
        'id': msg_id,
        'method': 'Runtime.evaluate',
        'params': {'expression': expr, 'returnByValue': True}
    }))
    while True:
        raw = await ws.recv()
        data = json.loads(raw)
        if data.get('id') == msg_id:
            return data.get('result', {}).get('result', {}).get('value')


async def capture_screenshot(ws, output_path):
    msg_id = int(time.time() * 1000) % 1000000 + 200
    await ws.send(json.dumps({
        'id': msg_id,
        'method': 'Page.captureScreenshot',
        'params': {'format': 'png'}
    }))
    while True:
        raw = await ws.recv()
        data = json.loads(raw)
        if data.get('id') == msg_id:
            png_bytes = base64.b64decode(data['result']['data'])
            # Ensure it is RGB PNG at 1920x1080
            im = Image.open(io.BytesIO(png_bytes)).convert('RGB')
            if im.size != (1920, 1080):
                im = im.resize((1920, 1080), Image.Resampling.LANCZOS)
            im.save(output_path, 'PNG')
            print(f'Saved verified RGB PNG {im.size} ({os.path.getsize(output_path)} bytes): {output_path}')
            return png_bytes


async def capture_gallery():
    print('Starting tools.sim run...')
    sim_proc = subprocess.Popen([
        'python3', '-m', 'tools.sim', 'run',
        '--demo', '--coach-sim', '--coach-round', '--no-voice',
        '--duration', '300',
        '--udp-port', str(UDP_PORT),
        '--ws-port', str(WS_PORT),
        '--hand-port', str(HAND_PORT),
        '--coach-port', str(COACH_PORT),
        '--http-port', str(HTTP_PORT),
    ], cwd=str(ROOT))

    print('Starting Chrome headless at 1920x1080...')
    chrome_proc = subprocess.Popen([
        CHROME_BIN,
        '--headless',
        f'--remote-debugging-port={CDP_PORT}',
        '--window-size=1920,1080',
        '--disable-gpu',
        '--hide-scrollbars',
        'about:blank'
    ])

    try:
        await asyncio.sleep(2.5)
        with urllib.request.urlopen(f'http://127.0.0.1:{CDP_PORT}/json/list') as resp:
            tabs = json.loads(resp.read().decode())
        ws_url = tabs[0]['webSocketDebuggerUrl']

        async with await get_cdp_page(ws_url) as ws:
            # Enable Page and Emulation
            await ws.send(json.dumps({'id': 1, 'method': 'Page.enable'}))
            await ws.send(json.dumps({
                'id': 2,
                'method': 'Emulation.setDeviceMetricsOverride',
                'params': {
                    'width': 1920,
                    'height': 1080,
                    'deviceScaleFactor': 1,
                    'mobile': False,
                }
            }))

            # -------------------------------------------------------------
            # CAPTURE 1: Practice Dashboard (gallery-01-coach.png)
            # -------------------------------------------------------------
            url1 = f'http://127.0.0.1:{HTTP_PORT}/?ws=ws://127.0.0.1:{WS_PORT}&hand=ws://127.0.0.1:{HAND_PORT}&coachws=ws://127.0.0.1:{COACH_PORT}&sim=input'
            print(f'Navigating to Gallery 1 URL:\n  {url1}')
            await ws.send(json.dumps({'id': 3, 'method': 'Page.navigate', 'params': {'url': url1}}))
            await asyncio.sleep(3.0)

            print('Monitoring coach state for mid-session drill card / full line...')
            t0 = time.time()
            captured_01 = False
            while time.time() - t0 < 90.0:
                pill = await evaluate(ws, 'document.querySelector("#statusPill") ? document.querySelector("#statusPill").textContent : ""')
                coach_line = await evaluate(ws, 'document.querySelector("#coachLine") ? document.querySelector("#coachLine").textContent : ""')
                has_drill_card = await evaluate(ws, 'Boolean(document.querySelector(".drill-card") || document.body.innerText.includes("Keep the hand moving"))')
                has_gap_mark = await evaluate(ws, 'Boolean(document.querySelector("#waveMark") && !document.querySelector("#waveMark").hidden)')
                todos_len = await evaluate(ws, 'document.querySelectorAll("#sessionList li").length')

                print(f'[{time.time()-t0:.1f}s] pill="{pill}" drill_card={has_drill_card} gap={has_gap_mark} todos={todos_len} line="{coach_line[:40]}..."')

                # We want mid-session with full line, drill card or gap bar visible, and todos
                if ('SIMULATED' in pill) and has_drill_card and len(coach_line) > 20 and not coach_line.startswith('…'):
                    print('Found mid-session Drill 1 with full coach line and drill card!')
                    await asyncio.sleep(1.0)
                    await capture_screenshot(ws, MEDIA / 'gallery-01-coach.png')
                    captured_01 = True
                    break

                await asyncio.sleep(1.0)

            if not captured_01:
                print('Capturing latest coach state...')
                await capture_screenshot(ws, MEDIA / 'gallery-01-coach.png')

            # -------------------------------------------------------------
            # CAPTURE 2: Gesture Control View (gallery-02-hand.png)
            # Run with coach connected so coach dock is populated (not empty)
            # -------------------------------------------------------------
            url2 = f'http://127.0.0.1:{HTTP_PORT}/?ws=ws://127.0.0.1:{WS_PORT}&hand=ws://127.0.0.1:{HAND_PORT}&coachws=ws://127.0.0.1:{COACH_PORT}&sim=input'
            print(f'Navigating to Gallery 2 URL (with coach populated):\n  {url2}')
            await ws.send(json.dumps({'id': 4, 'method': 'Page.navigate', 'params': {'url': url2}}))
            await asyncio.sleep(2.0)

            print('Monitoring demo for hand filter sweep with populated coach...')
            t0 = time.time()
            captured_02 = False
            while time.time() - t0 < 50.0:
                pill = await evaluate(ws, 'document.querySelector("#statusPill") ? document.querySelector("#statusPill").textContent : ""')
                eng_name = await evaluate(ws, 'document.querySelector("#engName") ? document.querySelector("#engName").textContent : ""')
                eng_pct = await evaluate(ws, 'document.querySelector("#engPct") ? document.querySelector("#engPct").textContent : ""')
                hand_state = await evaluate(ws, 'document.querySelector("#handState") ? document.querySelector("#handState").textContent : ""')
                filter_pct = await evaluate(ws, 'document.querySelector("#pct-filter") ? document.querySelector("#pct-filter").textContent : ""')

                print(f'[{time.time()-t0:.1f}s] pill="{pill}" hand="{hand_state}" eng="{eng_name} {eng_pct}" filter="{filter_pct}"')

                # We want filter sweep: engName == 'FILTER' and hand engaged!
                if 'SIMULATED' in pill and eng_name == 'FILTER' and eng_pct != '0%':
                    print('Captured active filter sweep with coach column active!')
                    await asyncio.sleep(0.4)
                    await capture_screenshot(ws, MEDIA / 'gallery-02-hand.png')
                    captured_02 = True
                    break

                await asyncio.sleep(0.3)

            if not captured_02:
                print('Capturing gesture view fallback...')
                await capture_screenshot(ws, MEDIA / 'gallery-02-hand.png')

    finally:
        chrome_proc.terminate()
        sim_proc.terminate()
        try:
            chrome_proc.wait(timeout=3)
            sim_proc.wait(timeout=3)
        except Exception:
            chrome_proc.kill()
            sim_proc.kill()


if __name__ == '__main__':
    asyncio.run(capture_gallery())
