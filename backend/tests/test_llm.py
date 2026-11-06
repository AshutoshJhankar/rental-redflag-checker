"""LLM client: JSON-mode fallback and multi-model fallback (no network)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.llm import LLMError, OpenAICompatibleLLM  # noqa: E402

OK = {"choices": [{"message": {"content": '{"ok": true}'}}]}


class Fake(OpenAICompatibleLLM):
    def __init__(self, script, **kw):
        super().__init__("k", "https://x/v1", "primary", fallback_models=kw.get("fallbacks", ()))
        self.script, self.calls = script, []

    def _post(self, payload):
        self.calls.append((payload["model"], "response_format" in payload))
        r = self.script(payload)
        if isinstance(r, Exception):
            raise r
        return r


def test_falls_back_to_next_model_when_rate_limited():
    llm = Fake(lambda p: LLMError("HTTP 429: rate-limited upstream") if p["model"] == "primary" else OK,
               fallbacks=["backup"])
    assert llm.complete_json([]) == {"ok": True}
    assert llm.last_model == "backup" and [m for m, _ in llm.calls] == ["primary", "backup"]


def test_json_mode_retry_without_response_format_on_404():
    llm = Fake(lambda p: LLMError("HTTP 404: No endpoints found that can handle the requested parameters")
               if "response_format" in p else OK)
    assert llm.complete_json([]) == {"ok": True}
    assert llm.calls == [("primary", True), ("primary", False)]
    llm.complete_json([])
    assert llm.calls[-1] == ("primary", False)  # remembered per model


def test_auth_error_stops_immediately():
    llm = Fake(lambda p: LLMError("HTTP 401: bad key"), fallbacks=["backup"])
    with pytest.raises(LLMError, match="401"):
        llm.complete_json([])
    assert [m for m, _ in llm.calls] == ["primary"]


def test_all_models_busy_reports_429():
    llm = Fake(lambda p: LLMError("HTTP 429: busy"), fallbacks=["b1", "b2"])
    with pytest.raises(LLMError) as e:
        llm.complete_json([])
    assert "HTTP 429" in str(e.value) and "b2" in str(e.value)


def test_error_inside_200_body_triggers_fallback():
    llm = Fake(lambda p: {"error": {"code": 503, "message": "provider down"}} if p["model"] == "primary" else OK,
               fallbacks=["backup"])
    assert llm.complete_json([]) == {"ok": True} and llm.last_model == "backup"


def test_user_agent_header_is_set():
    llm = OpenAICompatibleLLM("k", "https://x/v1", "m")
    import urllib.request
    seen = {}

    def fake_urlopen(req, timeout):
        seen.update(req.headers)
        raise LLMError("stop")

    orig = urllib.request.urlopen
    urllib.request.urlopen = fake_urlopen
    try:
        with pytest.raises(LLMError):
            llm._post({"model": "m"})
    finally:
        urllib.request.urlopen = orig
    assert "python-urllib" not in seen.get("User-agent", "").lower() and seen.get("User-agent")


def test_non_json_reply_moves_to_next_model():
    llm = Fake(lambda p: {"choices": [{"message": {"content": ""}}]} if p["model"] == "primary" else OK,
               fallbacks=["backup"])
    assert llm.complete_json([]) == {"ok": True} and llm.last_model == "backup"


def test_openrouter_requests_short_reasoning():
    llm = Fake(lambda p: OK)
    llm.base_url = "https://openrouter.ai/api/v1"
    seen = []
    llm.script = lambda p: (seen.append(p), OK)[1]
    llm.complete_json([])
    assert seen[0]["reasoning"] == {"effort": "low"}


def test_repairs_common_json_mistakes():
    from app.llm import parse_json_reply
    bad = '{"quote": "the "OWNER" may enter", "items": [1, 2,], "note": "line one\nline two"}'.replace("\\n", "\n")
    assert parse_json_reply(bad) == {"quote": 'the "OWNER" may enter', "items": [1, 2], "note": "line one\nline two"}
    assert parse_json_reply('Sure! ```json\n{"a": {"b": "x"},}\n```') == {"a": {"b": "x"}}
    with pytest.raises(LLMError):
        parse_json_reply('{"a": ')


def test_empty_content_uses_reasoning_or_falls_back():
    reasoning_only = {"choices": [{"message": {"content": None, "reasoning": 'thinking... {"ok": true}'}}]}
    assert Fake(lambda p: reasoning_only).complete_json([]) == {"ok": True}
    empty = {"choices": [{"message": {"content": ""}, "finish_reason": "length"}]}
    llm = Fake(lambda p: empty if p["model"] == "primary" else OK, fallbacks=["backup"])
    assert llm.complete_json([]) == {"ok": True}
