"""Unit tests for the rule-based parts: stance, tiers, verdict rule, live-search parsing (U01 ... U12)."""
import analysis
import evidence


def ev(stance, tier=2, date=None):
    return {"stance": stance, "credibility_tier": tier, "published_date": date}


def test_u01_stance_refutes_with_cue():
    stance, why = analysis.classify_stance(
        "The Great Wall of China is visible from space with the naked eye.",
        "The Great Wall is generally not visible to the unaided eye from low Earth orbit.")
    assert stance == "REFUTES" and "cue" in why


def test_u02_stance_supports_without_cue():
    stance, _ = analysis.classify_stance(
        "Mount Everest is the highest mountain above sea level.",
        "Mount Everest is Earth's highest mountain above sea level, at 8,848.86 metres.")
    assert stance == "SUPPORTS"


def test_u03_irrelevant_snippet_is_neutral():
    stance, why = analysis.classify_stance(
        "The Great Wall of China is visible from space.",
        "Paris is the capital and most populous city of France.")
    assert stance == "NEUTRAL" and "relevance" in why.lower() or "mention" in why.lower()


def test_u04_named_subject_must_appear():
    stance, why = analysis.classify_stance(
        "Sydney is the capital of Australia.",
        "Canberra is the capital of Australia and the seat of government.")
    assert stance == "NEUTRAL" and "named subject" in why


def test_u05_negated_claim_reverses_stance():
    stance, why = analysis.classify_stance(
        "The Earth is not flat.", "Claims that the Earth is flat are false.")
    assert stance == "SUPPORTS" and "reversed" in why


def test_u06_tier_lookup_and_fallbacks():
    rows = [{"domain": "wikipedia.org", "tier": 2}, {"domain": "nasa.gov", "tier": 1}]
    assert analysis.tier_for_domain("en.wikipedia.org", rows) == 2
    assert analysis.tier_for_domain("www.nasa.gov".replace("www.", ""), rows) == 1
    assert analysis.tier_for_domain("nca.gov.au", rows) == 1      # government TLD rule
    assert analysis.tier_for_domain("cs.example.edu", rows) == 2
    assert analysis.tier_for_domain("randomblog.xyz", rows) == 3


def test_u07_verdict_refuted_supported_mixed_unverifiable():
    assert analysis.aggregate([ev("REFUTES"), ev("REFUTES"), ev("REFUTES")], "x claim")["verdict"] == "Refuted"
    assert analysis.aggregate([ev("SUPPORTS"), ev("SUPPORTS"), ev("NEUTRAL")], "x claim")["verdict"] == "Supported"
    assert analysis.aggregate([ev("SUPPORTS"), ev("REFUTES")], "x claim")["verdict"] == "Mixed"
    assert analysis.aggregate([ev("SUPPORTS"), ev("NEUTRAL")], "x claim")["verdict"] == "Unverifiable"
    assert analysis.aggregate([], "x claim")["verdict"] == "Unverifiable"


def test_u08_tier_weights_let_one_strong_source_outweigh_weak_ones():
    out = analysis.aggregate([ev("REFUTES", 1), ev("REFUTES", 1), ev("SUPPORTS", 3)], "x claim")
    assert out["breakdown"]["refutes_weight"] == 6 and out["verdict"] == "Refuted"


def test_u09_recency_weighting_only_for_time_sensitive_claims():
    old = [ev("SUPPORTS", 2, "2015-01-01"), ev("SUPPORTS", 2, "2015-01-01")]
    assert analysis.aggregate(old, "He is the current president")["breakdown"]["supports_weight"] == 2.0
    assert analysis.aggregate(old, "Water boils at 100 degrees")["breakdown"]["supports_weight"] == 4.0


def test_u10_validate_claim_rules():
    assert analysis.validate_claim("  The Earth   is round.  ") == ("The Earth is round.", None)
    assert analysis.validate_claim("Hi")[1] is not None
    assert analysis.validate_claim(None)[1] == "Please enter a claim."
    assert analysis.validate_claim(42)[1] == "claim_text must be a string."


def test_u11_parse_wikipedia_payload_without_network():
    payload = {"query": {"pages": {
        "1": {"index": 2, "title": "B", "extract": "Text B", "fullurl": "https://en.wikipedia.org/wiki/B", "touched": "2026-10-01T10:00:00Z"},
        "2": {"index": 1, "title": "A", "extract": "Text A", "fullurl": "https://en.wikipedia.org/wiki/A"},
        "3": {"index": 3, "title": "C", "extract": "", "fullurl": "https://en.wikipedia.org/wiki/C"}}}}
    items = evidence.parse_wikipedia(payload)
    assert [i["source_name"] for i in items] == ["Wikipedia: A", "Wikipedia: B"]      # ordered, empty extract dropped
    assert items[1]["published_date"] == "2026-10-01" and items[0]["domain"] == "en.wikipedia.org"


def test_u12_live_failure_degrades_gracefully(monkeypatch):
    def boom(_claim, timeout=6):
        raise ConnectionError("network down")
    monkeypatch.setattr(evidence, "wikipedia_search", boom)
    items, info = evidence.gather("A completely unknown claim about nothing", mode="auto")
    assert items == [] and "ConnectionError" in info["live_error"]
