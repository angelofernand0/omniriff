# Hosted coach: the real Riff from the website

The website (omniriff.vercel.app) is the instrument: your guitar through the browser's effects and
looper, your webcam for the hand. Riff, the AI coach, runs on a small server (`coach/server.py`)
that holds the Gemini API key. With the server configured and quota available,
anyone on the team can do a **real test** from a computer with a browser:
no Python or model key on the player's computer. The team passcode is still required.

```
browser (Vercel)                                   coach server (any container host)
 guitar -> effects + looper -- finished loop -->    Ears + Eyes + the same CoachRunner/agent
 webcam -> hand tracking ----- wrist track ---->    per-player memory ("Last time...")
 coach column <------------- coach.frame --------   Gemini coaching cue
 local browser voice / captions <---------------   the same cue text
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

The current coach uses `gemini-2.5-flash-lite` through the Gemini Developer API,
with thinking disabled and no automatic paid-provider fallback. To avoid model
charges, the operator must use a free-tier Gemini API project **without billing
enabled**. An API key cannot prove its project's billing tier. Check
[Google's current pricing and limits](https://ai.google.dev/gemini-api/docs/pricing).
Quota exhaustion fails the request rather than selecting a paid model or Vertex AI.
Riff uses a local browser voice when available, with captions otherwise; it does
not make ElevenLabs requests or play prerecorded ElevenLabs cues.

The server also refuses new model runs near `OMNIRIFF_COACH_LIMIT_USD` (default
$8, across everyone). This is conservative local usage accounting, not a
provider-enforced billing cap or Gemini price quote. Hosting costs are separate.

## Run the server
On your own machine (keys from `.env` / `~/.config/omniriff/.env`):

```sh
python -m coach.server --no-passcode               # ws://127.0.0.1:8787/coach, loopback only
npm run build && npm run preview                   # http://127.0.0.1:4173/?coachserver=ws://127.0.0.1:8787/coach
python -m tools.showcase.realrun --out runs/showcase/check   # or drive a whole session from a script
```

**Existing Railway endpoint (SM's account):** `wss://coach-production-73284aee.up.railway.app/coach`.
The passcode is shared privately by SM, never on the board. A health response
does not establish which model is deployed. The original service was deployed
with the Railway CLI rather than a Git connection, so the provider migration
requires a redeploy from the reviewed, merged code and a Gemini key on the service:

```sh
npx @railway/cli@latest login            # once
npx @railway/cli@latest link             # pick project omniriff-coach, service coach
npx @railway/cli@latest up --service coach --ci
```

The service builds `coach/Dockerfile` (service variable `RAILWAY_DOCKERFILE_PATH=coach/Dockerfile`;
Railway ignored `railway.json` and tried to build the website without it), has a volume at `/data`,
and variables `GOOGLE_API_KEY` (or `GEMINI_API_KEY`), `OMNIRIFF_COACH_PASSCODE`,
`OMNIRIFF_COACH_LIMIT_USD=8`, `OMNIRIFF_COACH_MAX_SESSIONS=3`. Logs: `npx @railway/cli@latest logs --service coach`.

Other hosts (any Docker host; Fly.io shown). One machine, a volume for memory, secrets for keys:

```sh
fly launch --dockerfile coach/Dockerfile --name omniriff-coach --no-deploy --internal-port 8787
fly volumes create coach_data --size 1        # then add to fly.toml: [mounts] source="coach_data" destination="/data"
fly secrets set GOOGLE_API_KEY=... OMNIRIFF_COACH_PASSCODE=...
fly deploy
curl https://omniriff-coach.fly.dev/healthz    # ok
```

Then in Vercel set `VITE_COACH_SERVER=wss://omniriff-coach.fly.dev/coach` so the site connects by
default (players still need the passcode). Settings: `OMNIRIFF_COACH_ORIGINS` adds allowed page
origins (preview URLs); `OMNIRIFF_COACH_MAX_SESSIONS` (default 3) limits concurrent players.
Do not retain Anthropic or ElevenLabs keys for this coach; they are no longer
needed. Keep the Gemini key on the server, never in Vercel's public `VITE_*` variables.

## Limits
- One looper take at a time, up to 30 s; the take is the dry input (before effects), resampled to 16 kHz.
- The browser sends only the wrist point per hand frame (same as vision's hand log), so Eyes can say
  *that* the hand stopped, not what the fingers did. See "What's next" in the PR.
- Hosted memory is per browser (a random player id in local storage), kept on the server's volume.
- Nothing here is verified on Windows browsers or a real Scarlett through the browser yet.
