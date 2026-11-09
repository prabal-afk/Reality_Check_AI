"""RealityCheck AI - Flask backend (JSON API + static frontend)."""
import os
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

import analysis
import db
import evidence
import llm

STATIC_DIR = Path(__file__).resolve().parent / "static"
VERDICTS = ("Supported", "Refuted", "Mixed", "Unverifiable")


def create_app():
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024  # reject very large request bodies
    db.init_db()
    app.teardown_appcontext(db.close_db)

    # ---------------------------------------------------------------- helpers
    def error(message, status):
        return jsonify({"error": message}), status

    def evidence_rows(claim_id):
        rows = db.get_db().execute(
            "SELECT source_name, url, domain, snippet, stance, reason, credibility_tier, published_date "
            "FROM evidence WHERE claim_id = ? ORDER BY credibility_tier ASC, id ASC", (claim_id,)).fetchall()
        return [dict(r) for r in rows]

    def full_claim(row):
        ev = evidence_rows(row["id"])
        result = analysis.aggregate(ev, row["claim_text"]) if ev else analysis.aggregate([], row["claim_text"])
        return {
            "id": row["id"], "claim_text": row["claim_text"], "verdict": row["verdict"],
            "confidence": row["confidence"], "confidence_label": analysis.confidence_label(row["confidence"]),
            "explanation": row["explanation"], "retrieval_mode": row["retrieval_mode"],
            "created_at": row["created_at"], "evidence": ev, "breakdown": result["breakdown"],
        }

    # ------------------------------------------------------------------ pages
    @app.get("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.get("/static/<path:name>")
    def static_files(name):
        return send_from_directory(STATIC_DIR, name)

    # -------------------------------------------------------------------- API
    @app.get("/api/health")
    def health():
        n = db.get_db().execute("SELECT COUNT(*) AS n FROM claims").fetchone()["n"]
        return jsonify({"status": "ok", "claims_stored": n, "mode": os.environ.get("RC_MODE", "auto")})

    @app.post("/api/claims")
    def create_claim():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return error("Request body must be JSON with a claim_text field.", 400)
        clean, problem = analysis.validate_claim(data.get("claim_text"))
        if problem:
            return error(problem, 400)

        conn = db.get_db()
        source_rows = conn.execute("SELECT domain, tier FROM sources").fetchall()
        items, info = evidence.gather(clean)

        for it in items:
            it["credibility_tier"] = analysis.tier_for_domain(it["domain"], source_rows)
        unlabelled = [it for it in items if not it.get("stance")]
        if unlabelled:                         # AI labels live snippets when a key is set, else rules
            ai = llm.label_snippets(clean, [it["snippet"] for it in unlabelled])
            for i, it in enumerate(unlabelled):
                if ai:
                    it["stance"], it["reason"] = ai[i]
                else:
                    it["stance"], it["reason"] = analysis.classify_stance(clean, it["snippet"])

        result = analysis.aggregate(items, clean)
        if info["pack_match"]:
            retrieval = "bundled evidence pack"
        elif info["live_used"]:
            retrieval = "live Wikipedia search"
        elif info["live_error"]:
            retrieval = "no evidence found (live search unavailable)"
        else:
            retrieval = "no evidence found"

        cur = conn.execute(
            "INSERT INTO claims(claim_text, normalized_text, verdict, confidence, explanation, retrieval_mode) "
            "VALUES (?,?,?,?,?,?)",
            (clean, analysis.normalize_claim(clean), result["verdict"], result["confidence"],
             result["explanation"], retrieval))
        claim_id = cur.lastrowid
        for it in items:
            conn.execute(
                "INSERT INTO evidence(claim_id, source_name, url, domain, snippet, stance, reason, "
                "credibility_tier, published_date) VALUES (?,?,?,?,?,?,?,?,?)",
                (claim_id, it["source_name"], it["url"], it["domain"], it["snippet"], it["stance"],
                 it["reason"], it["credibility_tier"], it.get("published_date")))
        conn.commit()

        row = conn.execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()
        body = full_claim(row)
        body["live_error"] = info["live_error"]
        return jsonify(body), 201

    @app.get("/api/claims/<int:claim_id>")
    def get_claim(claim_id):
        row = db.get_db().execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()
        if row is None:
            return error("Claim not found.", 404)
        return jsonify(full_claim(row))

    @app.get("/api/claims")
    def list_claims():
        q = (request.args.get("q") or "").strip()[:100]
        verdict = (request.args.get("verdict") or "").strip()
        try:
            page = max(1, int(request.args.get("page", 1)))
            per_page = min(50, max(1, int(request.args.get("per_page", 10))))
        except ValueError:
            return error("page and per_page must be integers.", 400)
        if verdict and verdict not in VERDICTS:
            return error("verdict must be one of: " + ", ".join(VERDICTS), 400)

        where, params = [], []
        if q:
            where.append("claim_text LIKE ?")
            params.append(f"%{q}%")
        if verdict:
            where.append("verdict = ?")
            params.append(verdict)
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        conn = db.get_db()
        total = conn.execute(f"SELECT COUNT(*) AS n FROM claims {clause}", params).fetchone()["n"]
        rows = conn.execute(
            f"SELECT id, claim_text, verdict, confidence, created_at FROM claims {clause} "
            "ORDER BY id DESC LIMIT ? OFFSET ?", params + [per_page, (page - 1) * per_page]).fetchall()
        return jsonify({"items": [dict(r) for r in rows], "page": page, "per_page": per_page, "total": total})

    @app.get("/api/sources")
    def list_sources():
        rows = db.get_db().execute(
            "SELECT domain, name, tier, notes FROM sources ORDER BY tier, name").fetchall()
        return jsonify({"items": [dict(r) for r in rows]})

    @app.post("/api/claims/<int:claim_id>/feedback")
    def add_feedback(claim_id):
        conn = db.get_db()
        if conn.execute("SELECT 1 FROM claims WHERE id = ?", (claim_id,)).fetchone() is None:
            return error("Claim not found.", 404)
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not isinstance(data.get("helpful"), bool):
            return error("helpful must be true or false.", 400)
        comment = data.get("comment") or ""
        if not isinstance(comment, str) or len(comment) > 300:
            return error("comment must be text of at most 300 characters.", 400)
        cur = conn.execute("INSERT INTO feedback(claim_id, helpful, comment) VALUES (?,?,?)",
                           (claim_id, int(data["helpful"]), comment.strip()))
        conn.commit()
        return jsonify({"id": cur.lastrowid, "claim_id": claim_id}), 201

    # ---------------------------------------------------------- error handlers
    @app.errorhandler(404)
    def not_found(_e):
        return error("Not found.", 404)

    @app.errorhandler(405)
    def bad_method(_e):
        return error("Method not allowed.", 405)

    @app.errorhandler(413)
    def too_big(_e):
        return error("Request body too large.", 413)

    @app.errorhandler(500)
    def server_error(_e):
        return error("Internal server error.", 500)

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="127.0.0.1", port=port, debug=False)
