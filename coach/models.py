"""One Gemini Developer API path for every coach model call.

Free-tier eligibility belongs to the Google project, not to an API-key string.
Use a free-tier project without billing; quota failures never switch providers.
"""
from __future__ import annotations

import os


MODEL = "gemini-3.5-flash-lite"
KEY_NAMES = ("GOOGLE_API_KEY", "GEMINI_API_KEY")


def api_key() -> str:
    """Read only Gemini credentials; an old Anthropic key cannot start Riff."""
    for name in KEY_NAMES:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    raise RuntimeError(
        "GOOGLE_API_KEY or GEMINI_API_KEY is required. Use a Gemini free-tier "
        "project without billing; do not put the key in the browser or Git."
    )


def make_model(*, max_tokens: int = 4096, offline: bool = False):
    """Construct without invoking; offline is only for harness inspection.

    Explicit Developer API selection prevents Vertex/GCP environment variables
    from silently choosing a different billing path. No provider/model fallback
    or retry is configured, and no built-in paid search tools are enabled.
    """
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=MODEL,
        api_key="offline-harness-only-not-a-real-key" if offline else api_key(),
        vertexai=False,
        max_output_tokens=max_tokens,
        thinking_level="minimal",
        max_retries=0,
        timeout=40,
    )
