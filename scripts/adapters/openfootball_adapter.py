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
