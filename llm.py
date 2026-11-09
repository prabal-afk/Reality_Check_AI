"""Optional AI stance labelling (Google Gemini free tier, or any key you set).

Used ONLY to label snippets that retrieval already found (prompt v2 from the report):
the model never supplies sources or links. If no key is set, or the call/parse fails,
the app silently falls back to the rule-based labeller in analysis.py.

Setup (free key from Google AI Studio):
    set GEMINI_API_KEY=your_key          (PowerShell: $env:GEMINI_API_KEY="your_key")
    optional: GEMINI_MODEL (default gemini-2.0-flash)
"""
import json
import os
import re

import requests

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
VALID = {"SUPPORTS", "REFUTES", "NEUTRAL"}

PROMPT = (
    "Using only the evidence snippets below, label each as SUPPORTS, REFUTES or NEUTRAL for the claim. "
    'Return JSON only: [{{"id":1,"label":"...","reason":"max 15 words"}}]. '
    "If a snippet does not mention the claim, label NEUTRAL. Do not add sources or facts not in the snippets.\n\n"
    'Claim: "{claim}"\nSnippets:\n{snippets}'
)


def enabled():
    return bool(os.environ.get("GEMINI_API_KEY"))


def build_prompt(claim, snippets):
    lines = "\n".join(f'{i}. "{s}"' for i, s in enumerate(snippets, 1))
    return PROMPT.format(claim=claim, snippets=lines)


def parse_labels(text, n):
    """Parse the model's JSON reply into [(stance, reason)] of length n, or None if invalid."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if not isinstance(data, list):
        return None
    out = {}
    for row in data:
        if not isinstance(row, dict):
            return None
        label = str(row.get("label", "")).upper()
        if row.get("id") not in range(1, n + 1) or label not in VALID:
            return None
        out[row["id"]] = (label, str(row.get("reason", ""))[:120])
    if len(out) != n:
        return None
    return [out[i] for i in range(1, n + 1)]


def label_snippets(claim, snippets, timeout=12):
    """Return [(stance, reason)] from the model, or None to signal 'use the rules instead'."""
    if not enabled() or not snippets:
        return None
    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    try:
        resp = requests.post(
            ENDPOINT.format(model=model),
            headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"], "Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": build_prompt(claim, snippets)}]}],
                  "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}},
            timeout=timeout)
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        return None
    labels = parse_labels(text, len(snippets))
    return [(s, "AI label (Gemini): " + r) for s, r in labels] if labels else None
