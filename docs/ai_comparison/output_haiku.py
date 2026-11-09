@app.route("/api/claims", methods=["POST"])
def create_claim():
    data = request.get_json(silent=True) or {}
    claim_text = data.get("claim_text")

    if not isinstance(claim_text, str):
        return jsonify({"message": "claim_text must be a string"}), 400

    claim_text = claim_text.strip()
    if not 10 <= len(claim_text) <= 500:
        return jsonify({"message": "claim_text must be 10 to 500 characters after trimming"}), 400

    db = get_db()
    cursor = db.execute(
        "INSERT INTO claims (claim_text, verdict) VALUES (?, ?)",
        (claim_text, "Pending"),
    )
    db.commit()
    return jsonify(cursor.lastrowid), 201
