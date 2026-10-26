"""Correct the archived nomination-status column; saved metadata only."""
import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = Path('/srv/bulk/leo/research/ds24-ambiguity-position-r01/inventory/inventory.json')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == '__main__':
    source = HERE / 'report/metadata_witnesses.csv'
    destination = HERE / 'report/metadata_witnesses02.csv'
    rows = list(csv.DictReader(source.open()))
    old = json.loads(PRIOR.read_text())
    lookup = {(q['case'], q['component']): q for q in old['sources']}
    for row in rows:
        row['archived_nominee_compatible'] = lookup[(row['case'], row['component'])]['archived_nomination_compatible']
    with destination.open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    receipt = dict(reporting_only=True, reason='Original reporter read absent compatible key; exact key is archived_nomination_compatible',
        primary_witness_table=destination.name, original_table_preserved=True, scientific_values_or_selection_changed=False,
        files={str(p): sha(p) for p in [source, destination, PRIOR, Path(__file__)]})
    (HERE / 'report/witness02_seal.json').write_text(json.dumps(receipt, indent=2) + '\n')
