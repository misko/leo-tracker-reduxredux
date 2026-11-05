"""External exhaustive scientific audit of archived cavity nominations and selection."""
import argparse
import hashlib
import json
from pathlib import Path

from compare_algo07v3_history import compare_persisted


def compare(nominations, position, candidate):
    if nominations['status'] != 'complete' or position['status'] != 'complete':
        raise ValueError('Archived cavity policy is incomplete')
    for archived, key, excluded in (
        (nominations, 'cavity_nominations', {'seconds'}),
        (position, 'cavity_policy', {'seconds', 'nomination_sha256'}),
    ):
        compare_persisted({k:v for k,v in archived.items() if k not in excluded},
                          candidate[key], key)
    return dict(exact=True, scope='All cavity nomination and selection scientific fields; '
                                 'not subsequent ALGO03–07 recovery or final publication',
        excluded_nomination_fields=['seconds'],
        excluded_position_fields=['nomination_sha256', 'seconds'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nominations', type=Path, required=True)
    parser.add_argument('--position', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    paths = {k:getattr(args, k) for k in ('nominations', 'position', 'candidate')}
    values = {k:p.read_bytes() for k,p in paths.items()}
    result = compare(*(json.loads(values[k]) for k in paths))
    result['inputs'] = {k:dict(path=str(paths[k]), sha256=hashlib.sha256(v).hexdigest())
                        for k,v in values.items()}
    with args.output.open('x') as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps(result, sort_keys=True))
