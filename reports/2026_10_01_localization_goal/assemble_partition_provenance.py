"""Assemble four bounded read-only exports in frozen selection order."""
import json
from pathlib import Path

from regression_batch import digest

HERE = Path(__file__).resolve().parent


def main():
    selection = HERE/'student-scale-expansion-v1-freeze.json'
    assert digest(selection) == selection.with_suffix('.sha256').read_text().strip()
    units = json.loads(selection.read_text())['ordered_units']
    parts = [Path('/tmp')/f'leo-partition-provenance-12-v1-{suffix}.json' for suffix in 'abcd']
    documents = [json.loads(p.read_text()) for p in parts]
    first = documents[0]
    for doc in documents:
        assert doc['selection_sha256'] == digest(selection)
        assert doc['source_sha256'] == first['source_sha256']
        assert all(r['status'] == 'bound' and r['qualified'] for r in doc['rows'])
    rows = [r for d in documents for r in d['rows']]
    assert [r['unit'] for r in rows] == units
    result = dict(first, rows=rows, part_sha256={str(p): digest(p) for p in parts},
                  assembler_sha256=digest(__file__))
    output = HERE/'partition-provenance-12-v1.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(dict(bound=len(rows), sha256=digest(output))))


if __name__ == '__main__':
    main()
