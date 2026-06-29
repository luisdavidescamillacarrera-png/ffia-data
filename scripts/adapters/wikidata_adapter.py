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
