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
