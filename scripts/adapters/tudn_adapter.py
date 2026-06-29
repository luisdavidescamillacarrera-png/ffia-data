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
