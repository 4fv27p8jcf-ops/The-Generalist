"""
Drug Database v1 - Deployable Flask API

Exposes the locked contract as real HTTP endpoints:
  GET  /search-drugs?q=<text>
  POST /check-interactions
  GET  /health   (simple check that the service is up)

Run locally with: python app.py
Deployed on Render with: gunicorn app:app
"""
from flask import Flask, request, jsonify
import os
import glob

DB_PATH = "brands.db"

def _reassemble_db_if_needed():
    """If brands.db isn't present but split binary parts are (brands_db_part_*.bin),
    reassemble them into brands.db. Used to work around GitHub's 25MB web-upload limit."""
    if os.path.exists(DB_PATH):
        return
    parts = sorted(glob.glob("brands_db_part_*.bin"))
    if not parts:
        raise FileNotFoundError("Neither brands.db nor brands_db_part_*.bin found")
    with open(DB_PATH, "wb") as out:
        for part in parts:
            with open(part, "rb") as f:
                out.write(f.read())

_reassemble_db_if_needed()

import sqlite3
try:
    _conn = sqlite3.connect(DB_PATH)
    _count = _conn.execute("SELECT COUNT(*) FROM brands").fetchone()[0]
    print(f"[startup] brands.db loaded OK - {_count} brands found", flush=True)
    _conn.close()
except Exception as e:
    print(f"[startup] ERROR loading brands.db: {e}", flush=True)

from search_drugs import search_drugs
from check_interactions import check_interactions

app = Flask(__name__)


@app.after_request
def add_cors_headers(response):
    # Reflect the actual request origin (works whether or not the frontend
    # uses credentials mode - a hardcoded "*" is rejected by browsers when
    # credentials are involved, which can silently cause "Failed to fetch")
    origin = request.headers.get("Origin", "*")
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Credentials"] = "true"
    return response


@app.route("/search-drugs", methods=["GET", "OPTIONS"])
def search_drugs_endpoint():
    if request.method == "OPTIONS":
        return "", 204
    q = request.args.get("q", "")
    limit = request.args.get("limit", 10, type=int)
    try:
        result = search_drugs(q, limit=limit)
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/check-interactions", methods=["POST", "OPTIONS"])
def check_interactions_endpoint():
    if request.method == "OPTIONS":
        return "", 204
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"status": "error", "message": "Request body must be valid JSON"}), 400
    try:
        result = check_interactions(payload)
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
