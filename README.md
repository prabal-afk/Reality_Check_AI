# RealityCheck AI

A small full-stack web app that checks a factual claim: it collects evidence, labels each source as
supporting / conflicting, weights sources by credibility tier and gives a verdict
(Supported, Refuted, Mixed, Unverifiable) with a confidence level and a plain-language explanation.
Course project for CSL120 (Applied AI Tools and Prompt Engineering), The NorthCap University.

Stack: HTML/CSS/JavaScript frontend, Python Flask backend, SQLite database. No API keys needed.

## Run (Windows / macOS / Linux)
    pip install -r requirements.txt
    python app.py                # then open http://127.0.0.1:5000
    python -m pytest -v          # 39 tests

Optional: `RC_MODE=offline` uses only the bundled evidence pack, `RC_MODE=live` only Wikipedia,
`auto` (default) = bundled pack first, live Wikipedia when the pack has no match.
(PowerShell: `$env:RC_MODE="offline"; python app.py`)

## Files
    app.py        routes (POST/GET /api/claims, /api/sources, feedback, health)
    db.py         schema + seed of trusted sources (SQLite, parameterized SQL)
    analysis.py   validation, credibility tiers, rule-based stance, verdict rule
    evidence.py   bundled evidence pack + live Wikipedia search
    static/       index.html, style.css, app.js
    data/         evidence_pack.json (hand-labelled evidence with real links)
    tests/        pytest: 22 API tests + 12 unit tests
    docs/         screenshots, test output, AI comparison evidence

## Optional AI labelling (Gemini, free tier)
    set GEMINI_API_KEY=your_free_key        (PowerShell: $env:GEMINI_API_KEY="your_free_key")
When a key is set, snippets found by live search are labelled SUPPORTS / REFUTES / NEUTRAL by the model
(prompt v2, see llm.py); the model never supplies links. Without a key, or if the call fails, the
rule-based labeller in analysis.py is used. The bundled evidence pack is always hand-labelled.
