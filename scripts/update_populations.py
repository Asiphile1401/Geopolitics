"""Updating data/countries.json from the Worldometer 195-country population table.

Run manually with internet access: python scripts/update_populations.py
The web page is the population reference specified in the UCT exam brief.
No API key is required. Always inspect updates before committing the snapshot.
"""
import json
from pathlib import Path
import sys
from datetime import date

import requests
from bs4 import BeautifulSoup

SOURCE = 'https://www.worldometers.info/geography/how-many-countries-are-there-in-the-world/'
TARGET = Path(__file__).resolve().parents[1] / 'data' / 'countries.json'


def parse_table(html):
    soup = BeautifulSoup(html, 'html.parser')
    # Worldometer geography page: rank, country, 2026 population, ...
    tables = soup.select('table')
    for table in tables:
        header = table.find('thead')
        headers = header.get_text(' ', strip=True).lower() if header else ''
        if 'population' not in headers or 'country' not in headers:
            continue
        records = []
        for tr in table.select('tbody tr'):
            cells = tr.find_all('td', recursive=False)
            if len(cells) < 3:
                continue
            name = cells[1].get_text(' ', strip=True)
            raw = cells[2].get_text(' ', strip=True).replace(',', '').replace(' ', '')
            if raw.isdigit() and name:
                records.append({'name': name, 'population': int(raw)})
        if len(records) == 195:
            return records
    raise ValueError('Could not locate a compatible Worldometer population table')


def main():
    response = requests.get(SOURCE, timeout=20, headers={'User-Agent': 'INF4001 educational project country update'})
    response.raise_for_status()
    records = parse_table(response.text)
    snapshot = {'source': SOURCE, 'year': date.today().year, 'updated': date.today().isoformat(),
                'notes': 'Worldometer population table snapshot; check source notes.', 'countries': records}
    tmp = TARGET.with_suffix('.tmp')
    tmp.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    tmp.replace(TARGET)
    print(f'Updated {len(records)} countries in {TARGET}')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        sys.exit(f'Population import failed without overwriting existing data: {exc}')
