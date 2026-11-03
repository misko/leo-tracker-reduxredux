"""Compare intermediate RF decisions as well as final positions in paired replays."""

import argparse
import json
import math
from pathlib import Path

IGNORED = {'seconds', 'protocol_sha256'}


def compare(left, right):
    left, right = Path(left), Path(right)
    a = {str(p.relative_to(left)): p for p in (left/'SCAN').rglob('*.json')}
    b = {str(p.relative_to(right)): p for p in (right/'SCAN').rglob('*.json')}
    differences, floating = [], []
    exact_leaves = 0

    def visit(x, y, path):
        nonlocal exact_leaves
        if isinstance(x, str) and isinstance(y, str):
            x, y = x.replace(str(left), '<OUTPUT>'), y.replace(str(right), '<OUTPUT>')
        if isinstance(x, dict) and isinstance(y, dict):
            if set(x) != set(y):
                differences.append(dict(path=path, reason='keys'))
                return
            for key in x:
                if key not in IGNORED:
                    visit(x[key], y[key], path+'/'+key)
        elif isinstance(x, list) and isinstance(y, list):
            if len(x) != len(y):
                differences.append(dict(path=path, reason='length'))
                return
            for i, (v, w) in enumerate(zip(x, y, strict=True)):
                visit(v, w, path+'/'+str(i))
        elif type(x) is type(y) and x == y:
            exact_leaves += 1
        elif (isinstance(x, (float, int)) and isinstance(y, (float, int))
              and not isinstance(x, bool) and not isinstance(y, bool)
              and (isinstance(x, float) or isinstance(y, float))):
            tolerance = 1e-8
            if any(s in path for s in ('/objective', 'negative_twice_elbo')):
                tolerance = 1e-4
            elif any(s in path for s in ('/reference/', '/phase_reference/')):
                tolerance = 1e-6
            elif any(s in path for s in ('/x/', '/endpoint_east_north_km/')):
                tolerance = 1e-5
            delta = abs(x-y)
            row = dict(path=path, baseline=x, candidate=y, abs_difference=delta, atol=tolerance)
            floating.append(row)
            if not math.isfinite(delta) or delta > tolerance:
                differences.append(row)
        else:
            differences.append(dict(path=path, baseline=x, candidate=y, reason='value'))

    if set(a) != set(b):
        differences.append(dict(reason='file_inventory', baseline_only=sorted(set(a)-set(b)),
                                candidate_only=sorted(set(b)-set(a))))
    for name in sorted(set(a) & set(b)):
        visit(json.loads(a[name].read_text()), json.loads(b[name].read_text()), name)
    return dict(passed=not differences and bool(a), files=len(a), exact_leaves=exact_leaves,
                differing_floats=len(floating), differences=differences,
                largest_float_differences=sorted(floating, key=lambda r: -r['abs_difference'])[:30],
                ignored_fields=sorted(IGNORED), output_paths_normalized=True,
                includes_intermediate_screens_and_optimizer_histories=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.baseline, args.candidate)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in result.items()
                      if k not in {'differences', 'largest_float_differences'}}))
    if not result['passed']:
        raise SystemExit(1)
