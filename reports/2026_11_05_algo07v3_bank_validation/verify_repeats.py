"""Require both repeated baselines and repeated candidates to remain exact."""

import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from compare_algo07v3_runs import compare


def main(pair, reverse):
    results = {}
    for side in ('baseline', 'candidate'):
        results[side] = compare(SimpleNamespace(
            baseline_request=pair / f'{side}-request.json',
            candidate_request=reverse / f'{side}-request.json',
            baseline_timing=pair / side / 'attempt/supervisor.json',
            candidate_timing=reverse / side / 'attempt/supervisor.json',
            changed_module=[], added_module=[]))
    results['verifier_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with (reverse / 'cross-pair.json').open('x') as stream:
        json.dump(results, stream, indent=2)
        stream.write('\n')
    print('Repeated baseline and candidate science/eight PNGs exact')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pair', type=Path, required=True)
    parser.add_argument('--reverse', type=Path, required=True)
    main(**vars(parser.parse_args()))
