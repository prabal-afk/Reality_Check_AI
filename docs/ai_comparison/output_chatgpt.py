@app.route('/api/claims', methods=['POST'])
def create_claim():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"message": "Invalid JSON data"}), 400

    claim_text = data.get('claim_text')

    if not isinstance(claim_text, str):
        return jsonify({"message": "claim_text must be a string"}), 400

    claim_text = claim_text.strip()

    if not 10 <= len(claim_text) <= 500:
        return jsonify({"message": "Claim must be between 10 and 500 characters"}), 400

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO claims (claim_text, verdict) VALUES (?, ?)",
        (claim_text, 'Pending')
    )

    claim_id = cursor.lastrowid
    conn.commit()

    return jsonify({"id": int(claim_id)}), 201
