from pathlib import Path
import json
import sys

from game.catalog import COUNTRY_DATA, load_catalog
from game.engine import soldier_value


def test_worldometer_snapshot_has_195_countries():
    assert len(COUNTRY_DATA) == 195
    assert COUNTRY_DATA['South Africa']['population'] == 65_453_084
    assert COUNTRY_DATA['South Africa']['starting_soldiers'] == 5
    assert COUNTRY_DATA['Holy See (Vatican City)']['starting_soldiers'] == 1
    assert len(set(COUNTRY_DATA.keys())) == 195
    assert all(row['starting_soldiers'] == soldier_value(row['population'])
               for row in COUNTRY_DATA.values())


def test_catalog_rejects_duplicates(tmp_path):
    p = tmp_path / 'bad.json'
    p.write_text(json.dumps({'countries':[{'name':'X','population':4}]*10}),encoding='utf-8')
    try:
        load_catalog(p)
        raise AssertionError('Expected duplicate name to be rejected')
    except ValueError:
        pass


def test_population_import_parser_accepts_195_country_rows():
    from scripts.update_populations import parse_table
    fake = '<table><thead><tr><th>#</th><th>Country</th><th>Population 2026</th></tr></thead><tbody>'
    fake += ''.join(f'<tr><td>{i}</td><td>Nation {i}</td><td>1,000,000</td></tr>' for i in range(195))
    fake += '</tbody></table>'
    records = parse_table(fake)
    assert len(records) == 195
    assert records[-1]['population'] == 1_000_000
