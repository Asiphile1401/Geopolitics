"""Offline country snapshot, replaceable with the exam's Worldometer population data."""
from __future__ import annotations

import json
from pathlib import Path
from .engine import soldier_value

CATALOG_FILE = Path(__file__).resolve().parent.parent / 'data' / 'countries.json'


def load_catalog(path: Path = CATALOG_FILE) -> dict:
    snapshot = json.loads(Path(path).read_text(encoding='utf-8'))
    result = {}
    for item in snapshot['countries']:
        name, population = item['name'], item['population']
        if not isinstance(name, str) or not name or not isinstance(population, int) or population < 0:
            raise ValueError('Invalid country snapshot row')
        if name in result:
            raise ValueError(f'Duplicate country: {name}')
        result[name] = {'name': name, 'population': population, 'starting_soldiers': soldier_value(population)}
    if len(result) < 10:
        raise ValueError('The catalog must contain at least ten countries')
    return result


COUNTRY_DATA = load_catalog()
