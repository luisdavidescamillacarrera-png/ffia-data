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
