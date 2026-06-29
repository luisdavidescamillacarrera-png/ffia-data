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
