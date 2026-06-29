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
