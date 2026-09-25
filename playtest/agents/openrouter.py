"""OpenRouter chat client.

OpenRouter proxies every provider it supports (Gemini, Claude, GPT, Llama, ...)
behind one OpenAI-compatible ``/chat/completions`` endpoint, so the model is a
setting rather than a dependency: see ``OPENROUTER_MODEL``.
"""

import logging
import os

import requests

logger = logging.getLogger(__name__)

API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Default model, as an OpenRouter model id (any model listed on
# https://openrouter.ai/models works). Override it with OPENROUTER_MODEL, or
# per seat when setting up a match.
DEFAULT_MODEL = "google/gemini-2.5-flash"

# A match runs in a background thread: a provider that never answers must not
# keep that thread (and the match's "running" status) hanging forever.
REQUEST_TIMEOUT = 60

# Optional attribution headers, used by OpenRouter to credit the calling app.
APP_URL = "https://github.com/gab-25/mtg_deck_tester"
APP_TITLE = "mtg_deck_tester"


class ChatError(Exception):
    """The model could not be reached or gave no usable answer."""


def api_key() -> str | None:
    return os.environ.get("OPENROUTER_API_KEY") or None


def default_model() -> str:
    return os.environ.get("OPENROUTER_MODEL") or DEFAULT_MODEL


def chat(messages: list[dict], model: str | None = None, key: str | None = None) -> str:
    """Sends ``messages`` to ``model`` and returns the completion text.

    Raises :class:`ChatError` on a missing key, a network or HTTP failure, or an
    empty or malformed response.
    """
    key = key or api_key()
    if not key:
        raise ChatError("no OpenRouter API key configured (set OPENROUTER_API_KEY)")
    model = model or default_model()

    try:
        response = requests.post(
            API_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "HTTP-Referer": APP_URL,
                "X-Title": APP_TITLE,
            },
            json={"model": model, "messages": messages},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise ChatError(f"OpenRouter request failed: {exc}") from exc

    if response.status_code != 200:
        raise ChatError(f"OpenRouter returned HTTP {response.status_code}: {response.text[:300]}")

    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (ValueError, LookupError, TypeError) as exc:
        raise ChatError(f"unexpected OpenRouter response ({exc})") from exc

    if not content or not content.strip():
        raise ChatError("OpenRouter returned an empty completion")
    return content
