"""Compare native support with independent projected support, using fixed tolerances."""
import argparse
import math
from pathlib import Path

from leo.native_pipeline.location_input import graph_authority
from leo.native_pipeline.membership import read_observations
from leo.native_pipeline.runner import digest, finite_json, write_json


def compare(actual, expected):
    def parse(text):
        lines = text.splitlines()
        if len(lines) < 2:
            raise ValueError('missing support graph header')
        header = 'candidate_id\tstart_utc_ns\tcenter_utc_ns\tend_utc_ns\tm0\tm1\tm2\tm3'
        if lines[1] != header:
            raise ValueError('invalid support graph header')
        rows = {}
        for line in lines[2:]:
            fields = line.split('\t')
            if len(fields) != 8 or fields[0] in rows:
                raise ValueError('invalid or duplicate support row')
            times = tuple(map(int, fields[1:4]))
            moments = tuple(map(float, fields[4:]))
            if not all(math.isfinite(v) for v in moments):
                raise ValueError('nonfinite support moment')
            rows[fields[0]] = times, moments
        return lines[0], rows
    a_meta, a = parse(actual)
    b_meta, b = parse(expected)
    tolerances = (0., 0., 1e-18, 1e-20)
    errors = [0.]*4
    changed = []
    for key in sorted(a.keys() & b.keys()):
        delta = [abs(x-y) for x,y in zip(a[key][1], b[key][1])]
        errors = [max(x,y) for x,y in zip(errors,delta)]
        if a[key][0] != b[key][0] or any(x>tol for x,tol in zip(delta,tolerances)):
            changed.append(key)
    return {'passed': a_meta == b_meta and a.keys() == b.keys() and not changed,
            'metadata_exact': a_meta == b_meta, 'actual_count': len(a), 'expected_count': len(b),
            'missing': sorted(b.keys()-a.keys()), 'additional': sorted(a.keys()-b.keys()),
            'changed': changed, 'maximum_moment_errors': errors,
            'absolute_moment_tolerances': tolerances}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('graph','projection','authority','output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    receipt = finite_json(args.projection/'receipt.json')
    for name,key in [('observations.tsv','observation_sha256'),('support.json','support_sha256')]:
        if digest(args.projection/name) != receipt[key]:
            raise ValueError('reference projection changed')
    expected = graph_authority(read_observations(args.projection/'observations.tsv'),
        finite_json(args.projection/'support.json'), receipt, finite_json(args.authority))
    result = compare(args.graph.read_text(),expected)
    result['graph_sha256'] = digest(args.graph)
    result['projection_receipt_sha256'] = digest(args.projection/'receipt.json')
    result['authority_sha256'] = digest(args.authority)
    write_json(args.output,result)
    print(result)
    if not result['passed']:
        raise ValueError('native support differs from independent projection')


if __name__ == '__main__':
    main()
