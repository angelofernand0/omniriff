/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Default hosted coach address for this build, e.g. wss://omniriff-coach.fly.dev/coach (set in Vercel). */
  readonly VITE_COACH_SERVER?: string;
}
