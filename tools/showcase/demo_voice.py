"""Retired provider-audio generator; Riff now uses local browser speech.

Kept as a harmless entry point for old runbooks. It never reads a key, calls a
provider, changes cue timings, or creates audio files.
"""


def main() -> int:
    print("Demo voice generation is retired. Riff uses browser-local speech or captions; no API key is needed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
