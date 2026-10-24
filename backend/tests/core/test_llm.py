import json
from types import SimpleNamespace
from typing import Literal

import httpx
import pytest
from pydantic import BaseModel

import bidwit.core.llm as llm
from bidwit.core.llm import LLMClient, LLMUnavailable, parse_chain, strict_schema


class Item(BaseModel):
    i: int
    label: Literal["a", "b"]


class Out(BaseModel):
    items: list[Item]


GOOD = {"items": [{"i": 1, "label": "a"}]}


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)


def groq_server(responses, seen):
    """Fake Groq: returns the queued responses in order and records each request."""
    queue = list(responses)

    def handler(req: httpx.Request):
        seen.append({"auth": req.headers.get("authorization"), "body": json.loads(req.content)})
        r = queue.pop(0) if queue else ("ok", GOOD)
        kind, payload = r
        if kind == "ok":
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(payload)}}]})
        if kind == "raw":
            return httpx.Response(200, json={"choices": [{"message": {"content": payload}}]})
        status, headers, text = payload
        return httpx.Response(status, headers=headers, text=text)
    return httpx.MockTransport(handler)


def client(chain, transport=None, gemini_factory=None, tmp_path=None, max_calls=20):
    return LLMClient(parse_chain(chain, transport, gemini_factory), cache_dir=tmp_path, max_calls=max_calls)


def test_strict_schema_closes_every_object_and_requires_every_field():
    s = strict_schema(Out)
    item = s["$defs"]["Item"]
    assert s["additionalProperties"] is False and s["required"] == ["items"]
    assert item["additionalProperties"] is False and set(item["required"]) == {"i", "label"}
    assert "title" not in json.dumps(s)


def test_groq_answer_is_validated_and_key_sent_only_in_header():
    seen = []
    out, info = client("groq:openai/gpt-oss-120b", groq_server([("ok", GOOD)], seen)).ask("t", "sys", "user", Out)
    assert out == Out(**GOOD) and info.provider == "groq:openai/gpt-oss-120b" and not info.cached
    body = seen[0]["body"]
    assert seen[0]["auth"] == "Bearer test-groq-key" and "test-groq-key" not in json.dumps(body)
    assert body["response_format"]["json_schema"]["strict"] is True and body["reasoning_effort"] == "low"


def test_bad_answer_is_retried_then_next_provider():
    seen = []
    bad = [("raw", "not json"), ("ok", {"items": [{"i": 1, "label": "zzz"}]}), ("raw", "{}")]
    c = client("groq:m1,groq:m2", groq_server(bad + [("ok", GOOD)], seen))
    out, info = c.ask("t", "s", "u", Out)
    assert info.provider == "groq:m2" and "failed 3 times" in c.skipped["groq:m1"]


def test_short_rate_limit_waits_long_one_moves_on():
    seen = []
    c = client("groq:m1,groq:m2", groq_server([("err", (429, {"retry-after": "3"}, "slow down")), ("ok", GOOD)], seen))
    assert c.ask("t", "s", "u", Out)[1].provider == "groq:m1"
    seen2 = []
    c2 = client("groq:m1,groq:m2", groq_server([("err", (429, {"retry-after": "3600"}, "daily limit")), ("ok", GOOD)], seen2))
    assert c2.ask("t", "s", "u", Out)[1].provider == "groq:m2" and "rate limited" in c2.skipped["groq:m1"]


@pytest.mark.parametrize("status", [401, 403, 404])
def test_unusable_provider_is_skipped_for_the_rest_of_the_run(status):
    seen = []
    c = client("groq:m1,groq:m2", groq_server([("err", (status, {}, "nope")), ("ok", GOOD), ("ok", GOOD)], seen))
    c.ask("t", "s", "u1", Out)
    c.ask("t", "s", "u2", Out)
    assert [s["body"]["model"] for s in seen] == ["m1", "m2", "m2"]


def test_reasoning_setting_dropped_if_rejected():
    seen = []
    c = client("groq:openai/gpt-oss-120b", groq_server([("err", (400, {}, "reasoning_effort not supported")), ("ok", GOOD)], seen))
    c.ask("t", "s", "u", Out)
    assert "reasoning_effort" in seen[0]["body"] and "reasoning_effort" not in seen[1]["body"]


def test_missing_key_skips_provider(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY")
    with pytest.raises(LLMUnavailable, match="GROQ_API_KEY is not set"):
        client("groq:m1", groq_server([], [])).ask("t", "s", "u", Out)


def test_cache_replays_without_calls_even_if_provider_changes(tmp_path):
    seen = []
    c = client("groq:m1", groq_server([("ok", GOOD)], seen), tmp_path=tmp_path)
    c.ask("t", "s", "u", Out)
    c2 = client("gemini:g1", gemini_factory=lambda: (_ for _ in ()).throw(AssertionError("should not call")), tmp_path=tmp_path)
    out, info = c2.ask("t", "s", "u", Out)
    assert info.cached and out == Out(**GOOD) and c2.calls == 0
    assert "test-groq-key" not in "".join(p.read_text() for p in tmp_path.iterdir())


def test_tampered_cache_is_ignored(tmp_path):
    seen = []
    c = client("groq:m1", groq_server([("ok", GOOD), ("ok", GOOD)], seen), tmp_path=tmp_path)
    c.ask("t", "s", "u", Out)
    for p in tmp_path.iterdir():
        p.write_text(json.dumps({"provider": "x", "output": {"items": [{"i": "bad", "label": "q"}]}}))
    c.ask("t", "s", "u", Out)
    assert len(seen) == 2


def test_budget_is_enforced():
    with pytest.raises(LLMUnavailable, match="budget"):
        client("groq:m1", groq_server([("raw", "x")] * 10, []), max_calls=2).ask("t", "s", "u", Out)


def test_gemini_fallback_and_quota_skip():
    class FakeModels:
        def __init__(self, behaviour):
            self.behaviour = behaviour

        def generate_content(self, model, contents, config):
            b = self.behaviour.pop(0)
            if isinstance(b, Exception):
                raise b
            return SimpleNamespace(parsed=Out(**GOOD), text=json.dumps(GOOD))

    behaviour = [RuntimeError("429 RESOURCE_EXHAUSTED quota"), "ok"]
    factory = lambda: SimpleNamespace(models=FakeModels(behaviour))
    seen = []
    c = client("gemini:g1,groq:m1", groq_server([("ok", GOOD)], seen), gemini_factory=factory)
    out, info = c.ask("t", "s", "u", Out)
    assert info.provider == "groq:m1" and "quota" in c.skipped["gemini:g1"]


def test_everything_down_raises_unavailable_with_reasons():
    seen = []
    c = client("groq:m1,groq:m2", groq_server([("err", (401, {}, "x")), ("err", (404, {}, "y"))], seen))
    with pytest.raises(LLMUnavailable) as e:
        c.ask("t", "s", "u", Out)
    assert "groq:m1" in str(e.value) and "groq:m2" in str(e.value)


def test_per_day_limit_moves_on_even_with_short_retry_after():
    seen = []
    c = client("groq:m1,groq:m2", groq_server([("err", (429, {"retry-after": "30"}, "Limit reached on tokens per day (TPD)")), ("ok", GOOD)], seen))
    c.ask("t", "s", "u", Out)
    assert "groq:m1" in c.skipped and seen[-1]["body"]["model"] == "m2"


def test_pacer_waits_for_the_minute_window_instead_of_a_429(monkeypatch):
    waited = []
    monkeypatch.setattr(llm.time, "sleep", lambda s: waited.append(s))
    p = llm._Pacer(1000)
    p.spend(600, p.wait(600))
    p.spend(300, p.wait(300))                      # 900 used: still fits
    assert waited == []
    p.wait(500)                                    # would be 1400: must wait for the window
    assert waited and 55 < waited[0] <= 60.2


def test_pacer_is_shared_safely_by_parallel_threads(monkeypatch):
    import threading
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    p = llm._Pacer(10_000)
    ts = [threading.Thread(target=lambda: p.spend(100, p.wait(100))) for _ in range(50)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert sum(u[1] for u in p.used) == 5000
