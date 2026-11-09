"""Claim validation, text normalisation, stance rules, credibility tiers and the verdict rule.

Everything here is plain Python with no external services, so each function can be
explained and unit-tested on its own.
"""
import re
from datetime import date, datetime

MIN_LEN, MAX_LEN = 10, 500

STOPWORDS = set("""
a an the is are was were be been being of in on at to for with from by that this these those it its as and or
but if then than so very can could would should will do does did has have had which who whom into over under
there their they them he she his her we you i my our your about also just only really actually
""".split())

NEGATIONS = {"not", "no", "never", "cannot", "isnt", "arent", "wasnt", "werent", "doesnt", "dont",
             "didnt", "cant", "wont", "without", "neither", "nor"}

# very small synonym table so that "tallest" and "highest", "faked" and "hoax" can match
SYNONYMS = {
    "tallest": "high", "highest": "high", "tall": "high", "taller": "high", "higher": "high",
    "faked": "fake", "faking": "fake", "hoax": "fake", "staged": "fake", "fabricated": "fake",
    "used": "use", "uses": "use", "using": "use",
    "spherical": "round", "sphere": "round",
    "unaided": "naked", "eye": "eye", "eyes": "eye",
    "humans": "human", "people": "human", "person": "human",
}

REFUTE_CUES = [
    "myth", "misconception", "debunk", "hoax", "false", "untrue", "incorrect", "disproved",
    "no evidence", "no scientific", "not supported", "not true", "contrary to", "conspiracy theor",
    "cannot be", "could not", "did not", "does not", "is not", "are not", "was not", "were not",
    "never", "no credible", "not visible", "refuted", "rejected",
]


def _stem(word):
    if word in SYNONYMS:
        return SYNONYMS[word]
    if len(word) > 5 and word.endswith("ing"):
        word = word[:-3]
    elif len(word) > 4 and word.endswith("ed"):
        word = word[:-2]
    elif len(word) > 4 and word.endswith("es"):
        word = word[:-2]
    elif len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        word = word[:-1]
    return SYNONYMS.get(word, word)


def _words(text):
    text = text.lower().replace("%", " percent ").replace("’", "'")
    text = re.sub(r"\bten percent\b", "10 percent", text)
    text = text.replace("'", "")          # isn't -> isnt
    return re.findall(r"[a-z0-9]+", text)


def tokens(text):
    """Content tokens: lower-case, no stop words, no negations, lightly stemmed."""
    return {_stem(w) for w in _words(text) if w not in STOPWORDS and w not in NEGATIONS}


def has_negation(text):
    """True when the text contains an odd number of negation words."""
    count = sum(1 for w in _words(text) if w in NEGATIONS)
    return count % 2 == 1


def normalize_claim(text):
    return re.sub(r"\s+", " ", text.strip().lower())


def validate_claim(raw):
    """Return (clean_text, error_message). Exactly one of them is None."""
    if raw is None:
        return None, "Please enter a claim."
    if not isinstance(raw, str):
        return None, "claim_text must be a string."
    clean = re.sub(r"\s+", " ", raw.strip())
    if not clean:
        return None, "Please enter a claim."
    if len(clean) < MIN_LEN:
        return None, f"The claim is too short; write at least {MIN_LEN} characters."
    if len(clean) > MAX_LEN:
        return None, f"The claim is too long; the limit is {MAX_LEN} characters."
    if len(re.findall(r"[A-Za-z]{2,}", clean)) < 2:
        return None, "The claim must contain at least two words."
    return clean, None


# ---------------------------------------------------------------- credibility
def domain_of(url):
    m = re.match(r"^(?:https?://)?([^/:?#]+)", url.strip().lower())
    host = m.group(1) if m else ""
    return host[4:] if host.startswith("www.") else host


def tier_for_domain(domain, source_rows):
    """Look up a domain (or its parent domain) in the sources table; fall back to TLD rules."""
    known = {r["domain"]: r["tier"] for r in source_rows}
    parts = domain.split(".")
    for i in range(len(parts) - 1):
        candidate = ".".join(parts[i:])
        if candidate in known:
            return known[candidate]
    if domain.endswith(".gov") or ".gov." in domain or domain.endswith(".int"):
        return 1
    if domain.endswith(".edu") or ".ac." in domain or ".edu." in domain:
        return 2
    return 3


# --------------------------------------------------------------------- stance
def classify_stance(claim, snippet):
    """Rule-based stance of one snippet towards a claim -> (stance, reason).

    1. relevance = share of the claim's content words that appear in the snippet;
    2. named things in the claim (capitalised words) must also appear in the snippet;
    3. a refutation cue in a relevant snippet means REFUTES, otherwise SUPPORTS;
    4. if the claim itself is negated ("... is not ..."), SUPPORTS and REFUTES swap.
    """
    claim_tokens = tokens(claim)
    if not claim_tokens:
        return "NEUTRAL", "Claim has no content words to compare."
    snippet_tokens = tokens(snippet)
    relevance = len(claim_tokens & snippet_tokens) / len(claim_tokens)

    # capitalised words are treated as named things; sentence-opening stop words ("The") are ignored
    entities = {_stem(w.lower()) for w in re.findall(r"\b[A-Z][a-z]{2,}", claim) if w.lower() not in STOPWORDS}
    if entities:
        entity_share = len(entities & snippet_tokens) / len(entities)
        if entity_share < 0.6:
            return "NEUTRAL", f"Snippet does not mention the claim's named subject ({entity_share:.0%})."
    if relevance < 0.55:
        return "NEUTRAL", f"Low relevance: only {relevance:.0%} of the claim's key words appear."

    lowered = snippet.lower()
    cue = next((c for c in REFUTE_CUES if c in lowered), None)
    stance = "REFUTES" if cue else "SUPPORTS"
    note = f"Relevance {relevance:.0%}; " + (f"refutation cue '{cue}' found." if cue else "no refutation cue found.")
    if has_negation(claim):
        stance = "SUPPORTS" if stance == "REFUTES" else "REFUTES"
        note += " The claim itself is negated, so the stance is reversed."
    return stance, note


# -------------------------------------------------------------------- verdict
TIER_WEIGHT = {1: 3, 2: 2, 3: 1}
TIME_WORDS = {"current", "currently", "now", "today", "latest", "recent", "recently", "newest",
              "president", "population", "record", "richest", "largest", "biggest"}


def is_time_sensitive(claim):
    return bool(set(_words(claim)) & TIME_WORDS)


def _age_years(published):
    if not published:
        return None
    try:
        d = datetime.fromisoformat(published[:10]).date()
    except ValueError:
        return None
    return (date.today() - d).days / 365.25


def evidence_weight(item, time_sensitive):
    w = TIER_WEIGHT.get(item["credibility_tier"], 1)
    if time_sensitive:
        age = _age_years(item.get("published_date"))
        if age is not None and age > 2:
            w *= 0.5
    return w


def aggregate(evidence, claim_text):
    """Combine labelled evidence into a verdict. Returns a dict with a full breakdown."""
    ts = is_time_sensitive(claim_text)
    s_w = r_w = 0.0
    s_n = r_n = n_n = 0
    for item in evidence:
        w = evidence_weight(item, ts)
        if item["stance"] == "SUPPORTS":
            s_w += w
            s_n += 1
        elif item["stance"] == "REFUTES":
            r_w += w
            r_n += 1
        else:
            n_n += 1
    usable = s_n + r_n
    total = s_w + r_w
    share_s = s_w / total if total else 0.0
    share_r = r_w / total if total else 0.0

    if usable < 2:
        verdict, confidence = "Unverifiable", None
        explanation = ("Fewer than two relevant sources were found, so no reliable verdict can be given. "
                       "This does not mean the claim is true or false; try rewording it or check other sources.")
    elif share_s >= 0.7 or share_r >= 0.7:
        verdict = "Supported" if share_s >= 0.7 else "Refuted"
        top = max(share_s, share_r)
        confidence = round(min(0.95, top * min(1.0, usable / 3)), 2)
        side = "support" if verdict == "Supported" else "contradict"
        explanation = (f"{max(s_n, r_n)} of {usable} relevant sources {side} the claim, carrying "
                       f"{top:.0%} of the credibility-weighted evidence. "
                       f"Higher-tier sources count more, so one strong source can outweigh several weak ones.")
    else:
        verdict, confidence = "Mixed", None
        explanation = (f"The evidence is split: {s_n} source(s) support and {r_n} contradict the claim "
                       f"({share_s:.0%} versus {share_r:.0%} of the weighted evidence). "
                       "The claim may depend on how a term is defined; read both sides.")
    return {
        "verdict": verdict,
        "confidence": confidence,
        "confidence_label": confidence_label(confidence),
        "explanation": explanation,
        "breakdown": {
            "supports_count": s_n, "refutes_count": r_n, "neutral_count": n_n,
            "supports_weight": round(s_w, 2), "refutes_weight": round(r_w, 2),
            "share_support": round(share_s, 2), "share_refute": round(share_r, 2),
            "time_sensitive": ts,
        },
    }


def confidence_label(confidence):
    if confidence is None:
        return None
    return "High" if confidence >= 0.75 else "Medium" if confidence >= 0.5 else "Low"
