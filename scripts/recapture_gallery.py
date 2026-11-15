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
            # Ensure it is RGB PNG at 1280x720
            im = Image.open(io.BytesIO(png_bytes)).convert('RGB')
            if im.size != (1280, 720):
                im = im.resize((1280, 720), Image.Resampling.LANCZOS)
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

    print('Starting Chrome headless...')
    chrome_proc = subprocess.Popen([
        CHROME_BIN,
        '--headless',
        f'--remote-debugging-port={CDP_PORT}',
        '--window-size=1280,720',
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
                    'width': 1280,
                    'height': 720,
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

            print('Monitoring coach state for Drill 2 / before-after (Pass cue)...')
            t0 = time.time()
            captured_01 = False
            while time.time() - t0 < 90.0:
                pill = await evaluate(ws, 'document.querySelector("#statusPill") ? document.querySelector("#statusPill").textContent : ""')
                coach_line = await evaluate(ws, 'document.querySelector("#coachLine") ? document.querySelector("#coachLine").textContent : ""')
                app_coach = await evaluate(ws, 'document.querySelector("#app") ? document.querySelector("#app").dataset.coach : ""')
                has_before_after = await evaluate(ws, 'Boolean(document.querySelector(".before-after") || document.body.innerText.includes("120 ms") || document.body.innerText.includes("430 ms"))')
                loop_word = await evaluate(ws, 'document.querySelector("#loopWord") ? document.querySelector("#loopWord").textContent : ""')

                print(f'[{time.time()-t0:.1f}s] pill="{pill}" coach="{app_coach}" loop="{loop_word}" b/a={has_before_after} line="{coach_line[:35]}..."')

                # We specifically want the Drill 2 moment where the before/after card is shown or pass cue
                if 'SIMULATED · SCRIPTED COACH' in pill and has_before_after and ('tenth' in coach_line.lower() or 'pattern' in coach_line.lower() or 'nice' in coach_line.lower() or 'drill' in coach_line.lower()):
                    print('Found Drill 2 with before-after card and pass cue!')
                    await asyncio.sleep(1.0)
                    await capture_screenshot(ws, MEDIA / 'gallery-01-coach.png')
                    captured_01 = True
                    break

                await asyncio.sleep(1.2)

            if not captured_01:
                print('Capturing latest coach state...')
                await capture_screenshot(ws, MEDIA / 'gallery-01-coach.png')

            # -------------------------------------------------------------
            # CAPTURE 2: Gesture Control View (gallery-02-hand.png)
            # -------------------------------------------------------------
            url2 = f'http://127.0.0.1:{HTTP_PORT}/?ws=ws://127.0.0.1:{WS_PORT}&hand=ws://127.0.0.1:{HAND_PORT}&coach=off&sim=input'
            print(f'Navigating to Gallery 2 URL:\n  {url2}')
            await ws.send(json.dumps({'id': 4, 'method': 'Page.navigate', 'params': {'url': url2}}))
            await asyncio.sleep(2.0)

            print('Monitoring demo for hand filter sweep...')
            t0 = time.time()
            captured_02 = False
            while time.time() - t0 < 45.0:
                pill = await evaluate(ws, 'document.querySelector("#statusPill") ? document.querySelector("#statusPill").textContent : ""')
                eng_name = await evaluate(ws, 'document.querySelector("#engName") ? document.querySelector("#engName").textContent : ""')
                eng_pct = await evaluate(ws, 'document.querySelector("#engPct") ? document.querySelector("#engPct").textContent : ""')
                hand_state = await evaluate(ws, 'document.querySelector("#handState") ? document.querySelector("#handState").textContent : ""')
                filter_pct = await evaluate(ws, 'document.querySelector("#pct-filter") ? document.querySelector("#pct-filter").textContent : ""')

                print(f'[{time.time()-t0:.1f}s] pill="{pill}" hand="{hand_state}" eng="{eng_name} {eng_pct}" filter="{filter_pct}"')

                # We want filter sweep: engName == 'FILTER' and hand engaged!
                if pill == 'SIMULATED' and eng_name == 'FILTER' and eng_pct != '0%':
                    print('Captured active filter sweep!')
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
