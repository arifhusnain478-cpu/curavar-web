"""
LLM client with two modes:

  * live   -- calls the Anthropic API (needs ANTHROPIC_API_KEY). Every response
              is saved to a cassette keyed by a stable hash of the request, so a
              live run automatically records fixtures for later replay.
  * replay -- loads the recorded cassette for a request. No network, fully
              deterministic. This is what the offline demo uses.

This "record/replay" pattern is standard for testing LLM pipelines: it lets the
same agent code produce identical, inspectable results without hitting the
network, while still supporting genuine live reasoning when a key is present.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from typing import Optional

DEFAULT_MODEL = "claude-opus-4-8"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


def _request_key(model: str, system: str, user: str) -> str:
    basis = json.dumps({"model": model, "system": system, "user": user},
                       sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


class LLMClient:
    def __init__(
        self,
        mode: str = "replay",
        model: str = DEFAULT_MODEL,
        cassettes: Optional[dict] = None,
        max_tokens: int = 1500,
    ):
        assert mode in ("live", "replay")
        self.mode = mode
        self.model = model
        self.max_tokens = max_tokens
        self.cassettes: dict[str, str] = dict(cassettes or {})
        self._recorded: dict[str, str] = {}

    def complete(self, system: str, user: str) -> str:
        key = _request_key(self.model, system, user)
        if self.mode == "replay":
            if key not in self.cassettes:
                raise KeyError(
                    f"No cassette for request {key}. Run in --live mode with an "
                    f"API key to record it, or check the bundled case file."
                )
            return self.cassettes[key]

        # live
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set; cannot run live mode.")
        body = json.dumps({
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }).encode("utf-8")
        req = urllib.request.Request(
            ANTHROPIC_URL, data=body, method="POST",
            headers={
                "content-type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": ANTHROPIC_VERSION,
            },
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = "".join(
            block.get("text", "") for block in data.get("content", [])
            if block.get("type") == "text"
        )
        self._recorded[key] = text     # auto-record fixture for replay
        return text

    @property
    def recorded_cassettes(self) -> dict[str, str]:
        return dict(self._recorded)


def parse_json_block(text: str):
    """Agents are prompted to return strict JSON. Strip any accidental fences
    and parse. Raises with the offending text on failure so it is debuggable."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip("`").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Agent did not return valid JSON: {exc}\n---\n{text[:500]}")
