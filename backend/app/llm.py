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


def repair_json(t: str) -> str:
    """Fix the JSON mistakes models make most often: unescaped " inside strings, raw line breaks
    inside strings, and trailing commas. A quote counts as closing a string only when the next
    non-space character is , } ] or : (otherwise it's treated as part of the text and escaped)."""
    out, in_str, esc, n = [], False, False, len(t)
    for i, ch in enumerate(t):
        if not in_str:
            in_str = ch == '"'
            out.append(ch)
            continue
        if esc:
            esc = False
            out.append(ch)
        elif ch == "\\":
            esc = True
            out.append(ch)
        elif ch == '"':
            j = i + 1
            while j < n and t[j] in " \t\r\n":
                j += 1
            if j >= n or t[j] in ",}]:":
                in_str = False
                out.append(ch)
            else:
                out.append('\\"')
        elif ch in "\r\n":
            out.append("\\n" if ch == "\n" else "")
        else:
            out.append(ch)
    return re.sub(r",\s*([}\]])", r"\1", "".join(out))


def parse_json_reply(text: str) -> dict:
    """Parse a model reply that should be JSON, tolerating ```json fences, leading prose and common typos."""
    t = _FENCE.sub("", text.strip())
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end <= start:
        raise LLMError("Model did not return JSON")
    candidate = t[start : end + 1]
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as e:
        try:
            data = json.loads(repair_json(candidate))
        except json.JSONDecodeError:
            raise LLMError(f"Model returned invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise LLMError("Model JSON is not an object")
    return data


# Errors where another model may succeed: busy/rate-limited (429), model or route unavailable (404),
# model-specific request problems (400/422) and provider outages (5xx, timeouts). Auth/billing errors
# (401/402/403) would fail for every model, so they stop immediately.
_TRY_NEXT = re.compile(r"HTTP (400|404|408|409|422|429|5\d\d)\b|request failed|Empty reply|Unexpected LLM response")


class OpenAICompatibleLLM:
    """Chat-completions client with JSON mode and automatic fallback across models.

    `fallback_models` are tried in order when a model is rate-limited or unavailable, which matters
    for free model tiers that are often busy.
    """

    def __init__(self, api_key: str, base_url: str, model: str, timeout_s: float = 60.0,
                 fallback_models: list[str] | tuple[str, ...] = ()):
        self.api_key, self.base_url, self.name, self.timeout_s = api_key, base_url.rstrip("/"), model, timeout_s
        self.models = [model] + [m for m in fallback_models if m and m != model]
        self.last_model = model
        self._json_mode: dict[str, bool] = {}

    def _post(self, payload: dict) -> dict:
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                # Cloudflare (in front of OpenRouter and others) often blocks the default "Python-urllib" agent.
                "User-Agent": "rental-redflag-checker/1.0",
                "X-Title": "Rental Agreement Red-Flag Checker",  # optional OpenRouter attribution
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            raise LLMError(f"HTTP {e.code}: {e.read()[:300].decode(errors='replace')}") from e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            raise LLMError(f"LLM request failed: {e}") from e

    def _complete(self, model: str, messages: list[dict]) -> str:
        payload = {"model": model, "messages": messages, "temperature": 0, "max_tokens": 8192}
        if "openrouter.ai" in self.base_url:
            # Reasoning models can spend the whole budget "thinking" and return no answer; keep it short.
            payload["reasoning"] = {"effort": "low"}
        json_mode = self._json_mode.get(model, True)
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            data = self._post(payload)
        except LLMError as e:
            # Some models reject response_format (OpenRouter answers 404 "No endpoints found that can
            # handle the requested parameters"); retry this model once without it and remember that.
            if json_mode and re.search(r"HTTP (400|404|422)\b", str(e)):
                self._json_mode[model] = False
                payload.pop("response_format", None)
                data = self._post(payload)
            else:
                raise
        if isinstance(data, dict) and data.get("error"):
            # Some gateways report provider failures inside a 200 response.
            code = data["error"].get("code", 502) if isinstance(data["error"], dict) else 502
            raise LLMError(f"HTTP {code}: {json.dumps(data['error'])[:300]}")
        try:
            choice = data["choices"][0]
            msg = choice["message"]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError("Unexpected LLM response shape") from e
        content = (msg.get("content") or "").strip()
        if not content and msg.get("reasoning"):
            content = str(msg["reasoning"])  # some reasoning models put the final JSON only in their reasoning
        if not content:
            raise LLMError(f"Empty reply (finish_reason={choice.get('finish_reason')})")
        return content

    def complete_json(self, messages: list[dict]) -> dict:
        errors = []
        for model in self.models:
            try:
                content = self._complete(model, messages)
            except LLMError as e:
                errors.append(f"{model}: {e}")
                if not _TRY_NEXT.search(str(e)):
                    raise
                continue
            try:
                parsed = parse_json_reply(content)
            except LLMError as e:
                # Empty or non-JSON answer from this model: note what came back and try the next one.
                errors.append(f"{model}: {e} (reply started: {content.strip()[:160]!r})")
                continue
            self.last_model = model
            return parsed
        # Every model failed. Keep each model's reason so the server log shows what happened.
        raise LLMError(" | ".join(errors))
