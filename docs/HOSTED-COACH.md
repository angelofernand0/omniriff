# Hosted coach: the real Riff from the website

The website (omniriff.vercel.app) is the instrument: your guitar through the browser's effects and
looper, your webcam for the hand. Riff, the AI coach, runs on a small server (`coach/server.py`)
that holds the API keys. Anyone on the team can do a **real test** from any computer with a browser:
no Python, no keys, no `.env`.

```
browser (Vercel)                                   coach server (any container host)
 guitar -> effects + looper -- finished loop -->    Ears + Eyes + the same CoachRunner/agent
 webcam -> hand tracking ----- wrist track ---->    per-player memory ("Last time...")
 coach column <------------- coach.frame/audio --   ElevenLabs voice
 effects <------------------ approved rig change -  (only after you approve with Y / the pedal)
```

## Test it from the website
1. Open the site, open **Riff, the AI coach** in the settings, paste the server address
   (`wss://.../coach`) and the team passcode, **Connect Riff**. (Or open
   `https://omniriff.vercel.app/?coachserver=wss://.../coach&coachkey=PASSCODE` once; the browser remembers.)
2. Pick **Live audio + camera** (your guitar; choose the interface's instrument channel) or
   **Browser simulator**, press Start.
3. Type or say what you're working on (hold V), or press **Y**. Record a loop (Record loop / L),
   play 10+ seconds, Finish. Riff listens, thinks (plan on screen) and answers. Y approves a drill.

Each take costs a few cents (7 takes in the first real run: about $0.38, upper-bound estimate).
The server refuses new model runs near `OMNIRIFF_COACH_LIMIT_USD` (default $8, across everyone).

## Run the server
On your own machine (keys from `.env` / `~/.config/omniriff/.env`):

```sh
python -m coach.server --no-passcode               # ws://127.0.0.1:8787/coach, loopback only
npm run build && npm run preview                   # http://127.0.0.1:4173/?coachserver=ws://127.0.0.1:8787/coach
python -m tools.showcase.realrun --out runs/showcase/check   # or drive a whole session from a script
```

**Live now (Railway, SM's account):** `wss://coach-production-73284aee.up.railway.app/coach`
(`/healthz` answers `ok`). The passcode is shared privately by SM, never on the board.
It was deployed from this branch with the Railway CLI (not git-connected), so a coach change needs
a redeploy from a checkout of the merged code:

```sh
npx @railway/cli@latest login            # once
npx @railway/cli@latest link             # pick project omniriff-coach, service coach
npx @railway/cli@latest up --service coach --ci
```

The service builds `coach/Dockerfile` (service variable `RAILWAY_DOCKERFILE_PATH=coach/Dockerfile`;
Railway ignored `railway.json` and tried to build the website without it), has a volume at `/data`,
and variables `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`, `OMNIRIFF_COACH_PASSCODE`,
`OMNIRIFF_COACH_LIMIT_USD=8`, `OMNIRIFF_COACH_MAX_SESSIONS=3`. Logs: `npx @railway/cli@latest logs --service coach`.

Other hosts (any Docker host; Fly.io shown). One machine, a volume for memory, secrets for keys:

```sh
fly launch --dockerfile coach/Dockerfile --name omniriff-coach --no-deploy --internal-port 8787
fly volumes create coach_data --size 1        # then add to fly.toml: [mounts] source="coach_data" destination="/data"
fly secrets set ANTHROPIC_API_KEY=... ELEVENLABS_API_KEY=... OMNIRIFF_COACH_PASSCODE=...
fly deploy
curl https://omniriff-coach.fly.dev/healthz    # ok
```

Then in Vercel set `VITE_COACH_SERVER=wss://omniriff-coach.fly.dev/coach` so the site connects by
default (players still need the passcode). Settings: `OMNIRIFF_COACH_ORIGINS` adds allowed page
origins (preview URLs); `OMNIRIFF_COACH_MAX_SESSIONS` (default 3) limits concurrent players.

## Limits
- One looper take at a time, up to 30 s; the take is the dry input (before effects), resampled to 16 kHz.
- The browser sends only the wrist point per hand frame (same as vision's hand log), so Eyes can say
  *that* the hand stopped, not what the fingers did. See "What's next" in the PR.
- Hosted memory is per browser (a random player id in local storage), kept on the server's volume.
- Nothing here is verified on Windows browsers or a real Scarlett through the browser yet.
