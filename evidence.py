"""Evidence retrieval.

Two providers, both free and key-less:

* bundled pack  - data/evidence_pack.json, hand-labelled evidence for a few well-known claims.
                  Works offline and makes demos repeatable.
* live search   - Wikipedia's public search API. Stance is decided by the rules in analysis.py.

Policy (RC_MODE): "offline" = pack only, "live" = Wikipedia only,
"auto" (default) = pack first; Wikipedia only when the pack has no match.
The language model never supplies sources: every URL comes from one of the two providers.
"""
import json
import os
from pathlib import Path

import requests

from analysis import domain_of, has_negation, tokens

PACK_PATH = Path(__file__).resolve().parent / "data" / "evidence_pack.json"
WIKI_API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "RealityCheckAI/1.0 (student project; CSL120)"
MATCH_THRESHOLD = 0.5


def load_pack():
    with open(PACK_PATH, encoding="utf-8") as fh:
        return json.load(fh)["propositions"]


def _jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def pack_lookup(claim):
    """Return (proposition_id, items) for the best-matching bundled proposition, or (None, [])."""
    claim_tokens = tokens(claim)
    best, best_score = None, 0.0
    for prop in load_pack():
        score = _jaccard(claim_tokens, tokens(prop["text"]))
        if score > best_score:
            best, best_score = prop, score
    if best is None or best_score < MATCH_THRESHOLD:
        return None, []

    # If the user's claim is the negation of the stored proposition, the stored stances flip.
    flip = has_negation(claim) != has_negation(best["text"])
    items = []
    for it in best["items"]:
        stance = it["stance"]
        if flip and stance != "NEUTRAL":
            stance = "SUPPORTS" if stance == "REFUTES" else "REFUTES"
        note = "Curated label from the bundled evidence pack"
        note += " (reversed because the claim is worded as a negation)." if flip else "."
        items.append({
            "source_name": it["source_name"], "url": it["url"], "domain": domain_of(it["url"]),
            "snippet": it["snippet"], "stance": stance, "reason": note, "published_date": it.get("published_date"),
        })
    return best["id"], items


def parse_wikipedia(payload):
    """Turn a MediaWiki generator=search response into evidence dicts (stance still unknown)."""
    pages = (payload or {}).get("query", {}).get("pages", {})
    out = []
    for page in sorted(pages.values(), key=lambda p: p.get("index", 99)):
        extract = (page.get("extract") or "").strip()
        url = page.get("fullurl")
        if not extract or not url:
            continue
        out.append({
            "source_name": f"Wikipedia: {page.get('title', 'article')}",
            "url": url, "domain": domain_of(url), "snippet": extract[:600],
            "stance": None, "reason": None,
            "published_date": (page.get("touched") or "")[:10] or None,
        })
    return out


def wikipedia_search(claim, timeout=6):
    params = {
        "action": "query", "format": "json", "generator": "search", "gsrsearch": claim,
        "gsrlimit": 5, "prop": "extracts|info", "exintro": 1, "explaintext": 1,
        "exsentences": 3, "exlimit": "max", "inprop": "url",
    }
    resp = requests.get(WIKI_API, params=params, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    return parse_wikipedia(resp.json())


def gather(claim, mode=None):
    """Return (items, info). info says which providers were used and any live-search error."""
    mode = (mode or os.environ.get("RC_MODE", "auto")).lower()
    info = {"mode": mode, "pack_match": None, "live_used": False, "live_error": None}
    items = []
    if mode in ("auto", "offline"):
        prop_id, items = pack_lookup(claim)
        info["pack_match"] = prop_id
    if mode == "live" or (mode == "auto" and not items):
        try:
            items = wikipedia_search(claim)
            info["live_used"] = True
        except Exception as exc:  # network down, timeout, bad JSON: degrade gracefully
            info["live_error"] = f"{type(exc).__name__}: {exc}"[:200]
    return items, info
