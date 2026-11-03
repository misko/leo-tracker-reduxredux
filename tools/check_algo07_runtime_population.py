"""Bounded incumbent reconstruction parity across frozen private ALGO07 snapshots."""

import argparse
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np


def compare_results(baseline, candidate):
    a, b = [json.loads((p/'summary.json').read_text()) for p in (baseline, candidate)]
    if a['result'] != b['result']:
        raise ValueError('Incumbent reconstruction differs')
    af, bf = [sorted(p.glob('call-*.json')) for p in (baseline, candidate)]
    if not af or [p.name for p in af] != [p.name for p in bf]:
        raise ValueError('Kernel call inventories differ or are empty')
    for pa, pb in zip(af, bf, strict=True):
        if json.loads(pa.read_text()) != json.loads(pb.read_text()):
            raise ValueError('Kernel outputs differ: '+pa.name)
        with np.load(pa.with_suffix('.npz'), allow_pickle=False) as xa, np.load(
                pb.with_suffix('.npz'), allow_pickle=False) as xb:
            if xa.files != xb.files:
                raise ValueError('Tensor inventories differ')
            for key in xa.files:
                np.testing.assert_array_equal(xa[key], xb[key])
    return dict(checked_calls=len(af), associated=b['result']['associated'],
                seconds=b['seconds'], input_tensors_and_output_values_exact=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=Path, required=True)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output-label', required=True)
    parser.add_argument('--reference-label', default='calibration-cache1')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, choices=(1, 2, 3, 4), default=2)
    args = parser.parse_args()
    for name in (args.output_label, args.reference_label):
        if not re.fullmatch('[a-zA-Z0-9_-]+', name):
            raise ValueError('A simple directory label is required')
    rows = json.loads(args.index.read_text())['results']
    if not rows or len({r['root'] for r in rows}) != len(rows):
        raise ValueError('Nonempty unique snapshots required')
    environment = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1',
                       MKL_NUM_THREADS='1', PYTHONDONTWRITEBYTECODE='1',
                       PYTHONPATH=f'{args.repo}/src:{args.repo}/tools')

    def one(row):
        root = Path(row['root']).resolve()
        if not root.is_relative_to('/srv/bulk/leo/research'):
            raise ValueError('Private research snapshots required')
        output = root/args.output_label
        try:
            with (root/(args.output_label+'.log')).open('x') as stream:
                subprocess.run([sys.executable, '-B',
                                str(args.repo/'tools/profile_algo07_numerics.py'),
                                'run', '--snapshot', str(root), '--output', str(output),
                                '--mode', 'capture', '--no-cprofile', '--timeout', '300'],
                               cwd=args.repo, env=environment, stdout=stream,
                               stderr=subprocess.STDOUT, timeout=400, check=True)
            checks = compare_results(root/args.reference_label/'results', output/'results')
            return dict(case=row['case'], passed=True, root=str(root), **checks)
        except Exception as error:
            return dict(case=row['case'], passed=False, root=str(root), error=repr(error))

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(one, row) for row in rows]):
            result = future.result()
            results.append(result)
            print(json.dumps(result), flush=True)
    report = dict(passed=all(r['passed'] for r in results), results=results,
                  workers=args.workers, scope='Exact paired incumbent reconstruction and '
                  'kernel tensors; not full association search or optimizer reruns')
    with args.output.open('x') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
