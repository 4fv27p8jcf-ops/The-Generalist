"""
Drug Database v1 - Core Checking Method (SQLite-backed)
Implements the POST /check-interactions logic against the locked API contract.
"""
import json
import sqlite3

DB_PATH = "brands.db"

with open("interactions.json") as f:
    INTERACTIONS = json.load(f)
try:
    with open("food_interactions.json") as f:
        FOOD_INTERACTIONS = json.load(f)
except FileNotFoundError:
    FOOD_INTERACTIONS = {}

ORAL_ROUTES = {"oral"}


def is_oral(route):
    return route in ORAL_ROUTES or route == "unknown"


def _get_conn():
    return sqlite3.connect(DB_PATH)


def lookup_brand(conn, drug_id):
    """Return (name, salts_list, route) for a brand id, or None if unknown."""
    cur = conn.cursor()
    cur.execute("SELECT name, salts, route FROM brands WHERE id=?", (drug_id,))
    row = cur.fetchone()
    if row is None:
        return None
    name, salts_json, route = row
    return name, json.loads(salts_json), route


def check_interactions(payload):
    all_drug_ids = payload.get("ongoing_medications", []) + payload.get("new_prescriptions", [])
    route_overrides = payload.get("route_overrides", {})

    conn = _get_conn()

    unknown_drugs = []
    salt_sources = {}
    food_eligible_salt_sources = {}

    for drug_id in all_drug_ids:
        result = lookup_brand(conn, drug_id)
        if result is None:
            unknown_drugs.append(drug_id)
            continue
        brand_name, salts, brand_route = result
        route = route_overrides.get(drug_id, brand_route)
        for salt in salts:
            salt_sources.setdefault(salt, []).append({"drug_id": drug_id, "drug_name": brand_name})
            if is_oral(route):
                food_eligible_salt_sources.setdefault(salt, []).append({"drug_id": drug_id, "drug_name": brand_name})

    conn.close()

    # ---- duplication check ----
    duplicates = []
    for salt, sources in salt_sources.items():
        distinct_brands = {s["drug_id"] for s in sources}
        if len(distinct_brands) > 1:
            duplicates.append({
                "salt": salt,
                "found_in": sources,
                "message": f"'{salt}' appears in more than one of your medicines."
            })

    # ---- drug-drug interaction check ----
    salts_present = list(salt_sources.keys())
    drug_drug_interactions = []
    seen_pairs = set()

    for i in range(len(salts_present)):
        for j in range(i + 1, len(salts_present)):
            a, b = salts_present[i], salts_present[j]
            pair_key = tuple(sorted([a, b]))
            if pair_key in seen_pairs:
                continue
            severity = INTERACTIONS.get(a, {}).get(b)
            if severity:
                seen_pairs.add(pair_key)
                drug_names_a = [s["drug_name"] for s in salt_sources[a]]
                drug_names_b = [s["drug_name"] for s in salt_sources[b]]
                drug_drug_interactions.append({
                    "drugs": [a, b],
                    "brands_involved": {a: drug_names_a, b: drug_names_b},
                    "severity": severity,
                    "message": f"Possible {severity} interaction between {a} and {b}."
                })

    # ---- drug-food interaction check ----
    diet = set(f.strip().lower() for f in payload.get("diet", []))
    drug_food_interactions = []
    if diet:
        for salt, sources in food_eligible_salt_sources.items():
            for entry in FOOD_INTERACTIONS.get(salt, []):
                if entry["food"] in diet:
                    drug_food_interactions.append({
                        "salt": salt,
                        "food": entry["food"],
                        "brands_involved": [s["drug_name"] for s in sources],
                        "severity": entry["severity"],
                        "message": entry["message"],
                    })

    issues_found = bool(duplicates or drug_drug_interactions or drug_food_interactions or unknown_drugs)

    if drug_drug_interactions or duplicates or drug_food_interactions:
        summary = "We found possible issues with your medicine list. Please show this result to your doctor before making any changes."
    elif unknown_drugs:
        summary = "Some medicines could not be checked because they weren't found in our database. No issues were found among the ones we could check."
    else:
        summary = "No duplicate medicines or known interactions were found among the medicines checked."

    return {
        "status": "ok",
        "issues_found": issues_found,
        "duplicates": duplicates,
        "unknown_drugs": unknown_drugs,
        "drug_drug_interactions": drug_drug_interactions,
        "drug_food_interactions": drug_food_interactions,
        "patient_summary": summary,
        "disclaimer": "This is not medical advice. Always consult your doctor before changing any medication."
    }


if __name__ == "__main__":
    import sys
    sample = json.loads(sys.argv[1]) if len(sys.argv) > 1 else None
    if sample:
        print(json.dumps(check_interactions(sample), indent=2))
