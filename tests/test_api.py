"""Functional and invalid-input tests for the REST API (TC-01 ... TC-22)."""
import json
import sqlite3

GREAT_WALL = "The Great Wall of China is visible from space with the naked eye."


def post(client, text):
    return client.post("/api/claims", json={"claim_text": text})


# ---------------------------------------------------------------- creating claims
def test_tc01_valid_claim_returns_201_and_refuted(client):
    r = post(client, GREAT_WALL)
    body = r.get_json()
    assert r.status_code == 201
    assert body["id"] >= 1 and body["verdict"] == "Refuted"
    assert len(body["evidence"]) == 4 and body["confidence"] >= 0.75


def test_tc02_missing_claim_text_field(client):
    r = client.post("/api/claims", json={"other": "x"})
    assert r.status_code == 400 and "enter a claim" in r.get_json()["error"].lower()


def test_tc03_spaces_only_rejected(client):
    r = post(client, "            ")
    assert r.status_code == 400


def test_tc04_too_short_rejected(client):
    r = post(client, "Short")
    assert r.status_code == 400 and "too short" in r.get_json()["error"]


def test_tc05_too_long_rejected_and_nothing_saved(client):
    r = post(client, "word " * 120)
    assert r.status_code == 400 and "too long" in r.get_json()["error"]
    assert client.get("/api/claims").get_json()["total"] == 0


def test_tc06_wrong_type_rejected(client):
    r = client.post("/api/claims", json={"claim_text": 12345678901})
    assert r.status_code == 400 and "string" in r.get_json()["error"]


def test_tc07_invalid_json_body_rejected(client):
    r = client.post("/api/claims", data="not json", content_type="application/json")
    assert r.status_code == 400


def test_tc08_numbers_only_rejected(client):
    r = post(client, "1234567890 987654")
    assert r.status_code == 400 and "two words" in r.get_json()["error"]


# --------------------------------------------------------------- verdict behaviour
def test_tc09_supported_claim(client):
    body = post(client, "The Earth is round.").get_json()
    assert body["verdict"] == "Supported"


def test_tc10_mixed_claim(client):
    body = post(client, "Mount Everest is the tallest mountain in the world.").get_json()
    assert body["verdict"] == "Mixed" and body["confidence"] is None
    stances = sorted(e["stance"] for e in body["evidence"])
    assert stances == ["REFUTES", "REFUTES", "SUPPORTS", "SUPPORTS"]


def test_tc11_unverifiable_when_no_evidence(client):
    body = post(client, "My neighbour's cat can speak fluent Spanish.").get_json()
    assert body["verdict"] == "Unverifiable" and body["evidence"] == []


def test_tc12_negated_claim_flips_stance(client):
    refuted = post(client, "The Earth is flat.").get_json()
    supported = post(client, "The Earth is not flat.").get_json()
    assert refuted["verdict"] == "Refuted" and supported["verdict"] == "Supported"


def test_tc13_credibility_tiers_attached(client):
    body = post(client, "The Earth is flat.").get_json()
    tiers = {e["domain"]: e["credibility_tier"] for e in body["evidence"]}
    assert tiers["science.feedback.org"] == 1 and tiers["askanexpert.asu.edu"] == 2
    assert tiers["mentalfloss.com"] == 3


# -------------------------------------------------------------- reading claims back
def test_tc14_get_claim_by_id(client):
    cid = post(client, GREAT_WALL).get_json()["id"]
    r = client.get(f"/api/claims/{cid}")
    assert r.status_code == 200 and r.get_json()["claim_text"] == GREAT_WALL


def test_tc15_unknown_id_returns_404(client):
    r = client.get("/api/claims/999999")
    assert r.status_code == 404 and r.get_json()["error"] == "Claim not found."


def test_tc16_history_filter_search_and_paging(client):
    for t in [GREAT_WALL, "The Earth is flat.", "The Earth is round.", "My neighbour's cat can speak fluent Spanish."]:
        post(client, t)
    assert client.get("/api/claims").get_json()["total"] == 4
    assert client.get("/api/claims?verdict=Refuted").get_json()["total"] == 2
    assert client.get("/api/claims?q=earth").get_json()["total"] == 2
    page = client.get("/api/claims?per_page=3&page=2").get_json()
    assert len(page["items"]) == 1 and page["page"] == 2
    assert client.get("/api/claims?verdict=Bogus").status_code == 400
    assert client.get("/api/claims?page=abc").status_code == 400


def test_tc17_sources_endpoint(client):
    items = client.get("/api/sources").get_json()["items"]
    assert len(items) >= 25 and {i["tier"] for i in items} == {1, 2, 3}


# ----------------------------------------------------------------------- feedback
def test_tc18_feedback_saved_and_validated(client):
    cid = post(client, GREAT_WALL).get_json()["id"]
    ok = client.post(f"/api/claims/{cid}/feedback", json={"helpful": True, "comment": "clear"})
    assert ok.status_code == 201
    assert client.post(f"/api/claims/{cid}/feedback", json={"helpful": "yes"}).status_code == 400
    assert client.post("/api/claims/999/feedback", json={"helpful": True}).status_code == 404


# --------------------------------------------------------- persistence and safety
def test_tc19_data_survives_restart(make_app):
    first = make_app().test_client()
    cid = post(first, GREAT_WALL).get_json()["id"]
    second = make_app().test_client()            # a brand-new app instance = backend restart
    again = second.get(f"/api/claims/{cid}").get_json()
    assert again["verdict"] == "Refuted" and len(again["evidence"]) == 4


def test_tc20_sql_injection_text_is_stored_as_plain_text(client, tmp_path):
    nasty = "Robert'); DROP TABLE claims;-- is a valid claim text"
    r = post(client, nasty)
    assert r.status_code == 201
    assert client.get("/api/claims").get_json()["total"] == 1            # table still exists
    assert client.get("/api/claims?q=" + "'; DROP TABLE claims;--").status_code == 200


def test_tc21_html_in_claim_is_returned_as_data_not_executed(client):
    r = post(client, "<script>alert(1)</script> is not a real claim")
    assert r.status_code == 201
    assert r.get_json()["claim_text"].startswith("<script>")            # frontend uses textContent


def test_tc22_health_and_unknown_routes_are_json(client):
    assert client.get("/api/health").get_json()["status"] == "ok"
    r = client.get("/api/nothing")
    assert r.status_code == 404 and r.get_json()["error"] == "Not found."
    assert client.put("/api/claims").status_code == 405


def test_tc23_json_list_body_is_rejected_not_crashed(client):
    r = client.post("/api/claims", json=[1, 2, 3])
    assert r.status_code == 400 and "JSON" in r.get_json()["error"]
