# Browser instrument

Players open the hosted URL and tap **Start simulator**. No terminal, Python installation, account or model key is required for browser simulation. Record/Finish/Clear are visible touch buttons; advanced sound/hand controls live behind a collapsed settings section. The responsive browser layout stacks on phone/tablet screens.

The browser build shares the existing dashboard renderer. It adds an explicit Start button and three sources. The original Python-served dashboard continues to use its existing WebSockets and coach.

- **Browser simulator:** synthetic guitar and generated hand movement through an AudioWorklet filter, reverb and single-track looper. The SIMULATED label remains visible. No microphone, camera, model key or coach calls.
- **Live audio + camera:** microphone/interface input through browser effects, plus MediaPipe hand tracking after Start requests permission. Choose channel 2 for an interface whose instrument input is on that channel. Camera denial leaves the instrument and manual controls available. Missing input never substitutes a simulated guitar.
- **Python bridge:** connect to a running local Python engine and coach. Python remains authoritative for audio. Disconnecting this page leaves that instrument running. Use the local dashboard when browser security prevents a hosted HTTPS page connecting to local WebSockets.

Browser simulator and live input are instruments, not AI coaching sessions. Choose Python bridge for the coach. Browser telemetry does not measure native engine performance or physical round-trip latency.

## Develop and build

Requires Node 22.12 or later. From the repository root:

```sh
npm ci --ignore-scripts
npm run typecheck
npm test
npm run build
npm run preview
```

Open the preview URL printed by Vite. `dist/` is the static website artifact. `vercel.json` builds this artifact from the **repository root**. An existing Vercel project configured with Root Directory `dashboard` must change that setting to the repository root; otherwise it will continue publishing the old static offline dashboard. Keep Vercel on Node22 or later. Deployment quota is a hosting constraint, separate from local browser functionality. `npm run dev` serves the development build on loopback. The build injects the browser entry without changing the HTML served by Python, and includes the existing brand assets and classic dashboard layers.

Press **Start simulator** to enable browser audio. Open **Sound and source settings** to stop/mute the instrument, change tempo, pluck a note, select filter/reverb/scene hand control, or change source. The RIG drawer retains loop, bypass, manual effect sliders and hand view. L loops and B bypasses. Manual effect changes pause the automatic hand demo so it does not fight your slider.

Live tracking downloads the versioned MediaPipe runtime and hand model when selected. The instrument audio runs in an AudioWorklet; hand inference runs outside the audio processor. Webcam/microphone permissions, actual guitar/interface channel routing, browser support and audible behavior still need testing on the intended hardware.

## Verification boundaries

Automated tests cover DSP helpers, actual deployed worklet execution, source transitions and adapter cleanup. Browser simulator UI checks use generated audio and hand positions. They do not validate live camera accuracy, a real Scarlett/guitar sweep, pedal hardware, live coach responses, or measured latency. The pending audible Mac guitar/Scarlett validation remains documented on PR #13.
