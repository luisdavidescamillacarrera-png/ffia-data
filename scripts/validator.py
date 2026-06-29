"""
Validación de los JSON antes de guardar:
- JSON válido contra un JSON Schema mínimo
- IDs únicos
- Sin duplicados
- Fechas válidas (ISO 8601)
- Equipos existentes
- Grupos válidos
- Marcadores consistentes (enteros, score1 >=0, score2 >=0)
"""

import json
import sys
from pathlib import Path
from dateutil import parser as dateparser
from jsonschema import validate, ValidationError

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

SCHEMA_MATCH = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "date": {"type": "string", "format": "date-time"},
        "team1": {"type": "string"},
        "team2": {"type": "string"},
        "score1": {"type": ["integer", "null"]},
        "score2": {"type": ["integer", "null"]},
        "group": {"type": ["string", "null"]},
    },
    "required": ["id", "date", "team1", "team2"],
}

SCHEMA_RESULTS = {
    "type": "object",
    "properties": {
        "lastUpdate": {"type": "string"},
        "matches": {"type": "array", "items": SCHEMA_MATCH},
    },
    "required": ["lastUpdate", "matches"],
}

def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def validate_matches_structure(matches):
    for m in matches:
        try:
            validate(instance=m, schema=SCHEMA_MATCH)
        except ValidationError as e:
            raise ValueError(f"Schema error in match {m.get('id')}: {e.message}")

def validate_business_rules(matches, teams, groups):
    ids = set()
    for m in matches:
        mid = m["id"]
        if mid in ids:
            raise ValueError(f"Duplicate match id: {mid}")
        ids.add(mid)

        try:
            dateparser.parse(m["date"])
        except Exception as e:
            raise ValueError(f"Invalid date in match {mid}: {m['date']} -> {e}")

        if m["team1"] not in teams:
            raise ValueError(f"Unknown team: {m['team1']} in match {mid}")
        if m["team2"] not in teams:
            raise ValueError(f"Unknown team: {m['team2']} in match {mid}")

        if m.get("group") and m["group"] not in groups:
            raise ValueError(f"Unknown group: {m['group']} in match {mid}")

        s1 = m.get("score1")
        s2 = m.get("score2")
        if s1 is not None and (not isinstance(s1, int) or s1 < 0):
            raise ValueError(f"Invalid score1 for {mid}: {s1}")
        if s2 is not None and (not isinstance(s2, int) or s2 < 0):
            raise ValueError(f"Invalid score2 for {mid}: {s2}")

def main():
    try:
        results = load_json(DATA_DIR / "results.json")
        validate(instance=results, schema=SCHEMA_RESULTS)
        matches = results["matches"]
        teams_file = load_json(DATA_DIR / "teams.json")
        groups_file = load_json(DATA_DIR / "groups.json")
        teams = [t.get("name") if isinstance(t, dict) else t for t in teams_file.get("teams", [])]
        groups = [g.get("id") if isinstance(g, dict) else g for g in groups_file.get("groups", [])]
        validate_matches_structure(matches)
        validate_business_rules(matches, teams, groups)
        print("OK: validation passed")
        return 0
    except Exception as e:
        err_line = f"Validation error: {e}"
        print(err_line, file=sys.stderr)
        return 2

if __name__ == "__main__":
    sys.exit(main())
