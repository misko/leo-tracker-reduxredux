"""Compare all scientific values with an earlier qualified owned implementation.

Source changes are reported explicitly; this is not a timing comparison.
"""

import argparse
import hashlib
import json
from pathlib import Path

from check_algo07v3_publication import evidence_snapshot
from compare_algo07v3_runs import matched_requests, scientific_values

from leo.storage.localization_v3 import LocalizationV3Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--earlier', type=Path, required=True)
    parser.add_argument('--current', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    requests = [json.loads(p.read_bytes()) for p in (args.earlier, args.current)]
    matched_requests(*requests)
    saved = [LocalizationV3Store(r['output_root']).load(r['identity']['run_id']) for r in requests]
    a, b = [r['evidence'] for r in saved]
    failures = []
    try:
        scientific_values(a, b)
    except ValueError as error:
        failures.append(str(error))
    if evidence_snapshot(a, saved[0]['pngs']) != evidence_snapshot(b, saved[1]['pngs']):
        failures.append('Complete scientific/presentation snapshot differs')
    if saved[0]['pngs'] != saved[1]['pngs']:
        failures.append('PNG bytes differ')
    old, new = a['provenance']['modules'], b['provenance']['modules']
    changes = {k: dict(earlier=old.get(k), current=new.get(k))
               for k in sorted(old.keys() | new.keys())
               if old.get(k) != new.get(k)}
    output = dict(exact=not failures, failures=failures, timing_comparison=False,
                  changed_modules=changes, scientific_receipts=[r['sha256'] for r in saved],
                  bindings={str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in (args.earlier, args.current, Path(__file__))})
    with args.output.open('x') as stream:
        json.dump(output, stream, indent=2)
        stream.write('\n')
    print(json.dumps(dict(exact=not failures, failures=failures,
                          changed_modules=list(changes))))
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
