"""AI labelling tests (L-01 ... L-05). The network is mocked; no key or internet is needed."""
import json

import llm
import evidence

CLAIM = "The Great Wall of China is visible from space with the naked eye."
WIKI_ITEMS = [
    {"source_name": "Wikipedia: Great Wall of China", "url": "https://en.wikipedia.org/wiki/Great_Wall_of_China",
     "domain": "en.wikipedia.org", "snippet": "A series of fortifications.", "stance": None, "reason": None, "published_date": None},
    {"source_name": "Wikipedia: Space", "url": "https://en.wikipedia.org/wiki/Outer_space",
     "domain": "en.wikipedia.org", "snippet": "It is not visible to the unaided eye.", "stance": None, "reason": None, "published_date": None}]


class FakeResp:
    def __init__(self, text):
        self._text = text
    def raise_for_status(self):
        pass
    def json(self):
        return {"candidates": [{"content": {"parts": [{"text": self._text}]}}]}


def test_l01_disabled_without_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert llm.label_snippets(CLAIM, ["x"]) is None


def test_l02_parse_valid_and_fenced_json():
    good = json.dumps([{"id": 1, "label": "neutral", "reason": "a"}, {"id": 2, "label": "REFUTES", "reason": "b"}])
    assert llm.parse_labels("```json\n" + good + "\n```", 2) == [("NEUTRAL", "a"), ("REFUTES", "b")]


def test_l03_parse_rejects_bad_output():
    assert llm.parse_labels("not json", 1) is None
    assert llm.parse_labels(json.dumps([{"id": 1, "label": "MAYBE"}]), 1) is None
    assert llm.parse_labels(json.dumps([{"id": 1, "label": "SUPPORTS"}]), 2) is None       # missing id 2


def test_l04_ai_labels_used_for_live_snippets(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    reply = json.dumps([{"id": 1, "label": "NEUTRAL", "reason": "Does not address visibility."},
                        {"id": 2, "label": "REFUTES", "reason": "Says not visible."}])
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: FakeResp(reply))
    monkeypatch.setattr(evidence, "pack_lookup", lambda c: (None, []))
    monkeypatch.setattr(evidence, "wikipedia_search", lambda c, timeout=6: [dict(i) for i in WIKI_ITEMS])
    monkeypatch.setenv("RC_MODE", "auto")
    body = client.post("/api/claims", json={"claim_text": CLAIM}).get_json()
    assert [e["stance"] for e in body["evidence"]] == ["NEUTRAL", "REFUTES"]
    assert all(e["reason"].startswith("AI label (Gemini)") for e in body["evidence"])


def test_l05_falls_back_to_rules_when_ai_fails(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    def boom(*a, **k):
        raise ConnectionError("down")
    monkeypatch.setattr(llm.requests, "post", boom)
    monkeypatch.setattr(evidence, "pack_lookup", lambda c: (None, []))
    monkeypatch.setattr(evidence, "wikipedia_search", lambda c, timeout=6: [dict(i) for i in WIKI_ITEMS])
    monkeypatch.setenv("RC_MODE", "auto")
    r = client.post("/api/claims", json={"claim_text": CLAIM})
    assert r.status_code == 201
    assert not any(e["reason"].startswith("AI label") for e in r.get_json()["evidence"])
