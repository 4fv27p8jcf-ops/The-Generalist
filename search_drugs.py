"""
Drug Database v1 - Search / Autocomplete (SQLite-backed)
Implements the GET /search-drugs?q=<text> logic against the locked API contract.
Queries brands.db on disk instead of loading all brands into memory.
"""
import json
import sqlite3

DB_PATH = "brands.db"

try:
    with open("food_interactions.json") as f:
        FOOD_INTERACTIONS = json.load(f)
except FileNotFoundError:
    FOOD_INTERACTIONS = {}


def _get_conn():
    return sqlite3.connect(DB_PATH)


def food_tags_for_salts(salts):
    tags = set()
    for salt in salts:
        for entry in FOOD_INTERACTIONS.get(salt, []):
            tags.add(entry["food"])
    return sorted(tags)


def search_drugs(query, limit=10):
    q = query.strip().lower()
    if not q or len(q) < 2:
        return {"results": []}

    conn = _get_conn()
    cur = conn.cursor()

    rows = []
    seen_ids = set()

    cur.execute(
        "SELECT id, name, salts, route FROM brands WHERE discontinued=0 AND name_lower LIKE ? LIMIT ?",
        (q + "%", limit)
    )
    for r in cur.fetchall():
        if r[0] not in seen_ids:
            rows.append(r)
            seen_ids.add(r[0])

    if len(rows) < limit:
        cur.execute(
            "SELECT id, name, salts, route FROM brands WHERE discontinued=0 AND name_lower LIKE ? LIMIT ?",
            ("%" + q + "%", limit * 3)
        )
        for r in cur.fetchall():
            if r[0] not in seen_ids:
                rows.append(r)
                seen_ids.add(r[0])
                if len(rows) >= limit:
                    break

    if len(rows) < limit:
        cur.execute(
            "SELECT DISTINCT brand_id FROM brand_salts WHERE salt LIKE ? LIMIT ?",
            ("%" + q + "%", limit * 3)
        )
        candidate_ids = [r[0] for r in cur.fetchall() if r[0] not in seen_ids]
        if candidate_ids:
            placeholders = ",".join("?" * len(candidate_ids))
            cur.execute(
                f"SELECT id, name, salts, route FROM brands WHERE discontinued=0 AND id IN ({placeholders})",
                candidate_ids
            )
            for r in cur.fetchall():
                if r[0] not in seen_ids:
                    rows.append(r)
                    seen_ids.add(r[0])
                    if len(rows) >= limit:
                        break

    conn.close()

    out = []
    for bid, name, salts_json, route in rows[:limit]:
        salts = json.loads(salts_json)
        out.append({
            "id": bid,
            "name": name,
            "salts": salts,
            "route": route,
            "food_tags": food_tags_for_salts(salts) if route in ("oral", "unknown") else [],
        })

    return {"results": out}


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "para"
    print(json.dumps(search_drugs(q), indent=2))
