#!/usr/bin/env bash
set -e
mkdir -p .github/workflows scripts scripts/adapters data logs

cat > .github/workflows/update.yml <<'EOF'
name: Update FFIA data

on:
  schedule:
    - cron: '*/5 * * * *'  # cada 5 minutos
  workflow_dispatch:

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          persist-credentials: true

      - name: Setup Python 3.11
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run updater
        run: |
          python scripts/update_results.py

      - name: Run validator
        run: |
          python scripts/validator.py

      - name: Commit changes if any
        env:
          GIT_AUTHOR_NAME: "github-actions[bot]"
          GIT_AUTHOR_EMAIL: "github-actions[bot]@users.noreply.github.com"
        run: |
          git config user.name "$GIT_AUTHOR_NAME"
          git config user.email "$GIT_AUTHOR_EMAIL"
          git add data logs || true
          if git diff --cached --quiet; then
            echo "No changes to commit"
          else
            git commit -m "automated: update FFIA data $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
            git push
          fi

      - name: Deploy JSON to GitHub Pages (gh-pages)
        uses: peaceiris/actions-gh-pages@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./data
EOF

cat > scripts/__init__.py <<'EOF'
# Package init for scripts
EOF

cat > scripts/normalize.py <<'EOF'
"""
Módulo de normalización de nombres de selecciones.
Responsabilidad única: mapear sinónimos a nombres oficiales FFIA.
"""

_normalization_map = {
    "USA": "Estados Unidos",
    "U.S.A.": "Estados Unidos",
    "United States": "Estados Unidos",
    "Korea Republic": "Corea del Sur",
    "Republic of Korea": "Corea del Sur",
    "Korea, South": "Corea del Sur",
    "Czech Republic": "República Checa",
    "IR Iran": "Irán",
    "UAE": "Emiratos Árabes Unidos",
}

def normalize_team(name: str) -> str:
    if not name:
        return name
    key = name.strip()
    if key in _normalization_map:
        return _normalization_map[key]
    low = key.lower()
    for k, v in _normalization_map.items():
        if k.lower() == low:
            return v
    return key
EOF

cat > scripts/validator.py <<'EOF'
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
EOF

cat > scripts/update_results.py <<'EOF'
"""
Orquestador actualizado para soportar múltiples adaptadores.
Detecta adaptadores en scripts/adapters/* y carga solo los que estén habilitados por ENV.
"""

import json
import time
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict

from scripts.normalize import normalize_team

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
LOGS_DIR = ROOT / "logs"
LOG_FILE = LOGS_DIR / "sync.log"

ALLOW_REMOTE_FETCH = os.getenv("ALLOW_REMOTE_FETCH", "false").lower() in ("1","true","yes")

class DataSourceAdapter:
    def fetch_matches(self, last_update_iso: str = None) -> List[Dict]:
        raise NotImplementedError

def load_json(p: Path):
    if not p.exists():
        return None
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def log(entry: str):
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    line = f"{ts} - {entry}\n"
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line)

def discover_adapters():
    adapters = []
    try:
        from scripts.adapters.wikidata_adapter import WikidataAdapter
        adapters.append(WikidataAdapter())
    except Exception as e:
        print(f"Wikidata adapter not loaded: {e}")
    try:
        from scripts.adapters.openfootball_adapter import OpenFootballAdapter
        adapters.append(OpenFootballAdapter())
    except Exception as e:
        print(f"OpenFootball adapter not loaded: {e}")
    return adapters

def main():
    start = time.time()
    try:
        results = load_json(DATA_DIR / "results.json") or {"lastUpdate": "", "matches": []}
        teams = load_json(DATA_DIR / "teams.json") or {"teams": []}
        groups = load_json(DATA_DIR / "groups.json") or {"groups": []}

        last_update = results.get("lastUpdate") or None

        adapters = discover_adapters()
        if not adapters:
            msg = "No adapters enabled or available."
            print(msg)
            log(msg)
            return

        if not ALLOW_REMOTE_FETCH:
            msg = "Remote fetch disabled globally (ALLOW_REMOTE_FETCH not set). Enable to fetch remote sources."
            print(msg)
            log(msg)
            return

        all_remote_matches = []
        for adapter in adapters:
            try:
                remote_matches = adapter.fetch_matches(last_update)
                for m in remote_matches:
                    if m.get("team1"):
                        m["team1"] = normalize_team(m["team1"])
                    if m.get("team2"):
                        m["team2"] = normalize_team(m["team2"])
                all_remote_matches.extend(remote_matches)
            except PermissionError as pe:
                print(f"Adapter skipped (permission): {pe}")
                log(f"Adapter skipped (permission): {pe}")
            except Exception as e:
                print(f"Adapter error: {e}")
                log(f"Adapter error: {e}")

        if not all_remote_matches:
            duration = time.time() - start
            log(f"No remote matches fetched. duration_s={duration:.2f}")
            print("No remote matches fetched.")
            return

        existing = {m["id"]: m for m in results.get("matches", [])}
        changed = False
        for m in all_remote_matches:
            mid = m["id"]
            if mid not in existing:
                existing[mid] = m
                changed = True
            else:
                if existing[mid] != m:
                    existing[mid] = m
                    changed = True

        new_matches = list(existing.values())
        new_matches.sort(key=lambda x: x.get("date") or "")

        if changed:
            results["matches"] = new_matches
            results["lastUpdate"] = datetime.now(timezone.utc).isoformat()
            save_json(DATA_DIR / "results.json", results)
            duration = time.time() - start
            log(f"Updated results.json: matches={len(new_matches)} teams={len(teams.get('teams',[]))} duration_s={duration:.2f}")
            print("Updated results.json")
        else:
            duration = time.time() - start
            log(f"No changes detected. matches={len(new_matches)} duration_s={duration:.2f}")
            print("No changes detected.")

    except Exception as e:
        duration = time.time() - start
        log(f"ERROR: {e} duration_s={duration:.2f}")
        raise

if __name__ == "__main__":
    main()
EOF

cat > scripts/adapters/__init__.py <<'EOF'
# Package init for adapters - no-op
EOF

cat > scripts/adapters/wikidata_adapter.py <<'EOF'
"""
Adapter para Wikidata Query Service (SPARQL).
"""

import os
import time
import requests
from typing import List, Dict
from scripts.update_results import DataSourceAdapter

WIKIDATA_ENDPOINT_DEFAULT = "https://query.wikidata.org/sparql"
USER_AGENT = "ffia-data-bot/1.0 (https://github.com/luisdavidescamillacarrera-png/ffia-data) contact:you@example.com"

class WikidataAdapter(DataSourceAdapter):
    def __init__(self):
        self.enabled = os.getenv("ENABLE_WIKIDATA", "false").lower() in ("1","true","yes")
        self.endpoint = os.getenv("WIKIDATA_ENDPOINT", WIKIDATA_ENDPOINT_DEFAULT)
        self.tournament_qid = os.getenv("WIKIDATA_TOURNAMENT_QID")
        if self.enabled and not self.tournament_qid:
            raise ValueError("WIKIDATA_TOURNAMENT_QID is required when ENABLE_WIKIDATA is set")

    def _build_query(self, tournament_qid: str, last_update_iso: str = None) -> str:
        q = f"""
        SELECT ?match ?matchLabel ?date ?team1 ?team1Label ?team2 ?team2Label ?score1 ?score2 ?groupLabel WHERE {{
          ?match wdt:P31/wdt:P279* wd:Q4026292;
                 wdt:P3450 wd:{tournament_qid} .
          OPTIONAL {{ ?match wdt:P585 ?date. }}
          OPTIONAL {{ ?match wdt:P710 ?team1. }}
          OPTIONAL {{ ?match wdt:P710 ?team2. }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "es,en". }}
        }}
        """
        return q

    def fetch_matches(self, last_update_iso: str = None) -> List[Dict]:
        if not self.enabled:
            raise PermissionError("Wikidata adapter disabled. Set ENABLE_WIKIDATA=1 to enable.")
        query = self._build_query(self.tournament_qid, last_update_iso)
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/sparql-results+json"
        }
        resp = requests.get(self.endpoint, params={"query": query}, headers=headers, timeout=30)
        if resp.status_code != 200:
            raise ConnectionError(f"Wikidata SPARQL error: {resp.status_code} - {resp.text[:200]}")
        data = resp.json()
        matches = []
        for row in data.get("results", {}).get("bindings", []):
            mid = row.get("match", {}).get("value", "")
            date = row.get("date", {}).get("value")
            team1 = (row.get("team1Label") or row.get("team1") or {}).get("value")
            team2 = (row.get("team2Label") or row.get("team2") or {}).get("value")
            match = {
                "id": mid,
                "date": date,
                "team1": team1,
                "team2": team2,
                "score1": None,
                "score2": None,
                "group": None
            }
            matches.append(match)
        time.sleep(1.0)
        return matches
EOF

cat > scripts/adapters/openfootball_adapter.py <<'EOF'
"""
Adapter para datasets públicos tipo OpenFootball (GitHub raw JSON).
"""

import os
import requests
from typing import List, Dict
from scripts.update_results import DataSourceAdapter

USER_AGENT = "ffia-data-bot/1.0 (https://github.com/luisdavidescamillacarrera-png/ffia-data) contact:you@example.com"

class OpenFootballAdapter(DataSourceAdapter):
    def __init__(self):
        self.enabled = os.getenv("ENABLE_OPENFOOTBALL", "false").lower() in ("1","true","yes")
        self.url = os.getenv("OPENFOOTBALL_URL", "").strip()
        if self.enabled and not self.url:
            raise ValueError("OPENFOOTBALL_URL is required when ENABLE_OPENFOOTBALL is set")

    def fetch_matches(self, last_update_iso: str = None) -> List[Dict]:
        if not self.enabled:
            raise PermissionError("OpenFootball adapter disabled. Set ENABLE_OPENFOOTBALL=1 to enable.")
        headers = {"User-Agent": USER_AGENT}
        resp = requests.get(self.url, headers=headers, timeout=30)
        if resp.status_code != 200:
            raise ConnectionError(f"OpenFootball raw JSON fetch failed: {resp.status_code}")
        payload = resp.json()
        matches = []
        if isinstance(payload, dict):
            rounds = payload.get("rounds") or payload.get("matches") or []
            if isinstance(rounds, list) and rounds and isinstance(rounds[0], dict) and "matches" in rounds[0]:
                for r in rounds:
                    for m in r.get("matches", []):
                        mid = m.get("id") or f"{r.get('name')}-{m.get('date')}-{m.get('team1')}-{m.get('team2')}"
                        match = {
                            "id": mid,
                            "date": m.get("date"),
                            "team1": m.get("team1"),
                            "team2": m.get("team2"),
                            "score1": m.get("score1"),
                            "score2": m.get("score2"),
                            "group": r.get("name")
                        }
                        matches.append(match)
            else:
                for m in rounds:
                    mid = m.get("id") or f"{m.get('date')}-{m.get('team1')}-{m.get('team2')}"
                    match = {
                        "id": mid,
                        "date": m.get("date"),
                        "team1": m.get("team1"),
                        "team2": m.get("team2"),
                        "score1": m.get("score1"),
                        "score2": m.get("score2"),
                        "group": m.get("group")
                    }
                    matches.append(match)
        else:
            raise ValueError("Unexpected OpenFootball payload structure")
        return matches
EOF

cat > scripts/adapters/espn_adapter.py <<'EOF'
"""
Plantilla deshabilitada para ESPN. No ejecutar sin permiso escrito.
"""

import os
from typing import List, Dict
from scripts.update_results import DataSourceAdapter

class ESPNAdapter(DataSourceAdapter):
    def __init__(self):
        self.enabled = os.getenv("ENABLE_ESPN", "false").lower() in ("1","true","yes")
        if not self.enabled:
            raise PermissionError("ESPN adapter disabled: requires explicit permission and ENABLE_ESPN=1")

    def fetch_matches(self, last_update_iso: str = None) -> List[Dict]:
        raise NotImplementedError("ESPN adapter is a template and must not be implemented/executed without authorization.")
EOF

cat > scripts/adapters/tudn_adapter.py <<'EOF'
"""
Plantilla deshabilitada para TUDN. No ejecutar sin permiso escrito.
"""

import os
from typing import List, Dict
from scripts.update_results import DataSourceAdapter

class TUDNAdapter(DataSourceAdapter):
    def __init__(self):
        self.enabled = os.getenv("ENABLE_TUDN", "false").lower() in ("1","true","yes")
        if not self.enabled:
            raise PermissionError("TUDN adapter disabled: requires explicit permission and ENABLE_TUDN=1")

    def fetch_matches(self, last_update_iso: str = None) -> List[Dict]:
        raise NotImplementedError("TUDN adapter is a template and must not be implemented/executed without authorization.")
EOF

cat > scripts/adapters/fifa_social_adapter.py <<'EOF'
"""
Plantilla deshabilitada para extracción desde redes sociales de FIFA. No ejecutar sin permiso escrito.
"""

import os
from typing import List, Dict
from scripts.update_results import DataSourceAdapter

class FIFA_SocialAdapter(DataSourceAdapter):
    def __init__(self):
        self.enabled = os.getenv("ENABLE_FIFA_SOCIAL", "false").lower() in ("1","true","yes")
        if not self.enabled:
            raise PermissionError("FIFA Social adapter disabled: requires explicit permission and ENABLE_FIFA_SOCIAL=1")

    def fetch_matches(self, last_update_iso: str = None) -> List[Dict]:
        raise NotImplementedError("FIFA Social adapter is a template and must not be implemented/executed without authorization.")
EOF

cat > data/results.json <<'EOF'
{
  "lastUpdate": "",
  "matches": []
}
EOF

cat > data/teams.json <<'EOF'
{
  "teams": []
}
EOF

cat > data/groups.json <<'EOF'
{
  "groups": []
}
EOF

cat > data/standings.json <<'EOF'
{
  "standings": []
}
EOF

cat > data/rankings.json <<'EOF'
{
  "rankings": []
}
EOF

cat > logs/sync.log <<'EOF'
# sync log - append-only
EOF

cat > README.md <<'EOF'
# ffia-data

Proveedor de datos automático para FFIA v8.0 — resultados oficiales del Mundial FIFA 2026.

(README abreviado; revisa el repo para la versión completa)
EOF

cat > requirements.txt <<'EOF'
requests>=2.31.0
python-dateutil>=2.8.2
jsonschema>=4.17.3
PyYAML>=6.0
# SPARQLWrapper opcional
EOF

cat > LICENSE <<'EOF'
MIT License

Copyright (c) 2026 Luis David Escamilla Carrera
EOF

echo "Archivos creados correctamente."
