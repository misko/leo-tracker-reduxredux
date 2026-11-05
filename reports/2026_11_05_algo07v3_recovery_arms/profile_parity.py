"""Check research instrumentation against an unchanged owned result."""

import argparse
import hashlib
import json
from pathlib import Path

from check_algo07v3_publication import evidence_snapshot
from compare_algo07v3_runs import matched_requests, scientific_values

from leo.storage.localization_v3 import LocalizationV3Store


def main(reference, profile, output):
    requests = [json.loads(p.read_bytes()) for p in (reference, profile)]
    matched_requests(*requests)
    saved = [LocalizationV3Store(r['output_root']).load(r['identity']['run_id']) for r in requests]
    a, b = [v['evidence'] for v in saved]
    scientific_values(a, b)
    assert evidence_snapshot(a, saved[0]['pngs']) == evidence_snapshot(b, saved[1]['pngs'])
    assert saved[0]['pngs'] == saved[1]['pngs']
    left, right = a['provenance']['modules'], b['provenance']['modules']
    # The tool imports the same CLI worker instead of executing it as -m.
    assert set(left) - set(right) == {'__main__', '__mp_main__'}
    assert set(right) - set(left) == {'leo.cli.algo07v3'}
    assert all(left[k] == right[k] for k in left.keys() & right.keys())
    assert left['__main__']['sha256'] == left['__mp_main__']['sha256'] == (
        right['leo.cli.algo07v3']['sha256'])
    result = dict(
        profile_science_and_eight_pngs_exact=True, shared_implementation_exact=True,
        entry_point_module_aliases=['__main__', '__mp_main__', 'leo.cli.algo07v3'],
        entry_point_bytes_identical=True, scientific_receipts=[v['sha256'] for v in saved],
        bindings={str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in (reference, profile, Path(__file__))}, timing_comparison=False,
    )
    with output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('reference', 'profile', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    main(args.reference, args.profile, args.output)
