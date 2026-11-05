"""Minimal OpenAI-compatible client that returns parsed JSON (stdlib only)."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Protocol


class LLMError(RuntimeError):
    pass


class JSONModel(Protocol):
    name: str

    def complete_json(self, messages: list[dict]) -> dict: ...


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I)


def parse_json_reply(text: str) -> dict:
    """Parse a model reply that should be JSON, tolerating ```json fences or leading prose."""
    t = _FENCE.sub("", text.strip())
    try:
        data = json.loads(t)
    except json.JSONDecodeError:
        start, end = t.find("{"), t.rfind("}")
        if start == -1 or end <= start:
            raise LLMError("Model did not return JSON")
        try:
            data = json.loads(t[start : end + 1])
        except json.JSONDecodeError as e:
            raise LLMError(f"Model returned invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise LLMError("Model JSON is not an object")
    return data


class OpenAICompatibleLLM:
    def __init__(self, api_key: str, base_url: str, model: str, timeout_s: float = 60.0):
        self.api_key, self.base_url, self.name, self.timeout_s = api_key, base_url.rstrip("/"), model, timeout_s
        self._json_mode = True

    def _post(self, payload: dict) -> dict:
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            raise LLMError(f"HTTP {e.code}: {e.read()[:300].decode(errors='replace')}") from e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            raise LLMError(f"LLM request failed: {e}") from e

    def complete_json(self, messages: list[dict]) -> dict:
        payload = {"model": self.name, "messages": messages, "temperature": 0}
        if self._json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            data = self._post(payload)
        except LLMError as e:
            # Some providers/models reject response_format; retry once without it.
            if self._json_mode and "HTTP 400" in str(e):
                self._json_mode = False
                payload.pop("response_format", None)
                data = self._post(payload)
            else:
                raise
        try:
            content = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError("Unexpected LLM response shape") from e
        return parse_json_reply(content)
