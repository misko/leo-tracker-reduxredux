"""Check the final one-position cache against iteration 003 tensor captures."""

import concurrent.futures
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
POPULATION = Path('/srv/bulk/leo/research/algo07-runtime-20261103/population')


def one(row):
    root = Path(row['root'])
    output = root/'calibration-cache1'
    try:
        with (root/'calibration-cache1.log').open('x') as stream:
            subprocess.run([sys.executable, '-B', str(ROOT/'tools/profile_algo07_numerics.py'),
                            'run', '--snapshot', str(root), '--output', str(output),
                            '--mode', 'capture', '--no-cprofile', '--timeout', '300'],
                           cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                           timeout=400, check=True)
        baseline = root/'prepared-geometry/results'
        candidate = output/'results'
        a = json.loads((baseline/'summary.json').read_text())
        b = json.loads((candidate/'summary.json').read_text())
        assert a['result'] == b['result'], 'incumbent reconstruction values differ'
        af, bf = [sorted(p.glob('call-*.json')) for p in (baseline, candidate)]
        assert [p.name for p in af] == [p.name for p in bf] and af
        for pa, pb in zip(af, bf, strict=True):
            assert json.loads(pa.read_text()) == json.loads(pb.read_text()), pa.name
            with np.load(pa.with_suffix('.npz')) as xa, np.load(pb.with_suffix('.npz')) as xb:
                assert xa.files == xb.files
                for key in xa.files:
                    np.testing.assert_array_equal(xa[key], xb[key])
        return dict(case=row['case'], passed=True, checked_calls=len(af),
                    associated=b['result']['associated'],
                    seconds=b['seconds'], kernel_seconds=b['kernel_seconds'],
                    input_tensors_and_output_values_exact=True, root=str(root))
    except Exception as exc:
        return dict(case=row['case'], passed=False, root=str(root), error=repr(exc))


if __name__ == '__main__':
    os.environ.update(OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
                      PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=f'{ROOT}/src:{ROOT}/tools')
    rows = json.loads((POPULATION/'reconstruction-parity-v1.json').read_text())['results']
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for future in concurrent.futures.as_completed([pool.submit(one, row) for row in rows]):
            result = future.result()
            results.append(result)
            print(json.dumps(result), flush=True)
    with (POPULATION/'calibration-cache1-parity.json').open('x') as stream:
        json.dump(dict(results=results, passed=all(r['passed'] for r in results), workers=2,
                       scope='Exact incumbent reconstructions and tensors, not full refits'),
                  stream, indent=2)
