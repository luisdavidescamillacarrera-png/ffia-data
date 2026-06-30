import os
import requests
import time
from datetime import datetime, timezone
from scripts.normalize import normalize_team

OPENFOOTBALL_URL = "https://githubusercontent.com"

class OpenFootballAdapter:
    def fetch_matches(self, last_update_iso: str = None):
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
