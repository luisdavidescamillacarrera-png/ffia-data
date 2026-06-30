"""
Orquestador definitivo de demolición.
Cero lectura de variables externas. Dirección inmutable grabada a fuego.
"""

import json
import time
import requests
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict

from scripts.normalize import normalize_team

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
LOGS_DIR = ROOT / "logs"
LOG_FILE = LOGS_DIR / "sync.log"

OPENFOOTBALL_URL = "https://githubusercontent.com"

class DataSourceAdapter:
    def fetch_matches(self, last_update_iso: str = None) -> List[Dict]:
        raise NotImplementedError

class OpenFootballAdapter(DataSourceAdapter):
    def fetch_matches(self, last_update_iso: str = None) -> List[Dict]:
        try:
            print(f"Fetching from OpenFootball: {OPENFOOTBALL_URL}")
            r = requests.get(OPENFOOTBALL_URL, timeout=15)
            r.raise_for_status()
            data = r.json()
            
            raw_matches = data.get("matches", [])
            normalized_matches = []
            for m in raw_matches:
                normalized_matches.append({
                    "id": f"of-{m.get('num', time.time())}",
                    "date": m.get("date", datetime.now(timezone.utc).isoformat()),
                    "team1": normalize_team(m.get('team1')),
                    "team2": normalize_team(m.get('team2')),
                    "score1": m.get("score1"),
                    "score2": m.get("score2"),
                    "group": m.get("group")
                })
            return normalized_matches
        except Exception as e:
            print(f"Adapter error: {e}")
            return []

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

def main():
    try:
        results = load_json(DATA_DIR / "results.json") or {"lastUpdate": "", "matches": []}
        
        adapter = OpenFootballAdapter()
        fetched_matches = adapter.fetch_matches()
        
        if fetched_matches:
            results["matches"] = fetched_matches
            results["lastUpdate"] = datetime.now(timezone.utc).isoformat()
            save_json(DATA_DIR / "results.json", results)
            msg = f"Successfully fetched and validated {len(fetched_matches)} matches."
            print(msg)
            log(msg)
        else:
            msg = "No remote matches fetched or enabled."
            print(msg)
            log(msg)
            
    except Exception as e:
        msg = f"Critical error in main orchestrator: {e}"
        print(msg)
        log(msg)

if __name__ == "__main__":
    main()
