"""Bounded four-worker reconstruction check of all frozen two-family incumbents."""

import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DEST = Path('/srv/bulk/leo/research/algo07-runtime-20261103/population')
MANIFEST = ROOT/'reports/2026_11_03_algo07_runtime_reference/frozen.json'
REFERENCE = DEST.parent/'slow-additive/reference_kernel.py'
CASES = ['DS26-0006', 'DS26-0042', 'DS26-0050', 'DS26-0086', 'DS26-0116',
         'DS26-0128', 'DS26-0142', 'DS26-0152', 'DS26-0154', 'DS26-0183',
         'DS26-0239', 'DS26-0255', 'DS26-0299', 'DS27-0024', 'DS28-0012', 'DS28-0015']


def command(values, log, timeout=400):
    with log.open('x') as stream:
        subprocess.run([sys.executable, '-B', *map(str, values)], cwd=ROOT,
                       stdout=stream, stderr=subprocess.STDOUT, timeout=timeout, check=True)


def one(case):
    root = DEST/(case+'-r3' if case == 'DS26-0006' else case+'-v1')
    try:
        if case != 'DS26-0006':
            command([ROOT/'tools/profile_algo07_research_snapshot.py', '--manifest', MANIFEST,
                     '--case', case, '--output', root, '--reference-kernel', REFERENCE],
                    DEST/(case+'-prepare.log'))
        for arm in ['reference', 'candidate']:
            if case == 'DS26-0006' and arm == 'reference':
                continue
            cmd = [ROOT/'tools/profile_algo07_numerics.py', 'run', '--snapshot', root,
                   '--output', root/arm, '--mode', 'capture', '--timeout', '300', '--no-cprofile']
            if arm == 'reference':
                cmd += ['--reference']
            command(cmd, DEST/(case+'-'+arm+'.log'))
        a, b = [json.loads((root/arm/'results/summary.json').read_text())
                for arm in ['reference', 'candidate']]
        metrics = []
        af = sorted((root/'reference/results').glob('call-*.json'))
        bf = sorted((root/'candidate/results').glob('call-*.json'))
        assert [p.name for p in af] == [p.name for p in bf] and af
        for pa, pb in zip(af, bf, strict=True):
            va, vb = json.loads(pa.read_text()), json.loads(pb.read_text())
            for key in ['joint_map_indices', 'phase_pair_count', 'visible_prior_mass']:
                assert va[key] == vb[key], key
            delta = {}
            for key, atol in [('negative_twice_log_density', 1e-6),
                              ('phase_marginals', 1e-8), ('orbital_map_mean', 1e-6)]:
                groups = [(va[key], vb[key])] if key == 'negative_twice_log_density' else zip(
                    va[key], vb[key], strict=True)
                maxima = []
                for ga, gb in groups:
                    xa, xb = np.asarray(ga), np.asarray(gb)
                    np.testing.assert_allclose(xa, xb, atol=atol, rtol=0)
                    maxima.append(float(np.max(abs(xa-xb))))
                delta[key] = max(maxima)
            # Neither arm may silently receive a different tensor input.
            with np.load(pa.with_suffix('.npz')) as xa, np.load(pb.with_suffix('.npz')) as xb:
                assert xa.files == xb.files
                for key in xa.files:
                    np.testing.assert_array_equal(xa[key], xb[key])
            metrics.append(delta)
        assert a['result']['associated'] == b['result']['associated']
        assert len(a['kernel_calls']) == len(b['kernel_calls'])
        return dict(case=case, passed=True, root=str(root), associated=a['result']['associated'],
                    calls=len(a['kernel_calls']), checked_calls=len(af), differences=metrics,
                    baseline_seconds=a['seconds'], candidate_seconds=b['seconds'],
                    baseline_kernel_seconds=a['kernel_seconds'],
                    candidate_kernel_seconds=b['kernel_seconds'])
    except Exception as exc:
        return dict(case=case, passed=False, root=str(root), error=repr(exc))


if __name__ == '__main__':
    os.environ.update(OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
                      PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=f'{ROOT}/src:{ROOT}/tools')
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for f in concurrent.futures.as_completed([pool.submit(one, case) for case in CASES]):
            row = f.result()
            results.append(row)
            print(json.dumps({k:v for k,v in row.items() if k != 'differences'}), flush=True)
    with (DEST/'reconstruction-parity-v1.json').open('x') as stream:
        json.dump(dict(results=results, passed=all(r['passed'] for r in results),
                       scope='Paired incumbent reconstruction and exact inputs; not full reassociation',
                       workers=4), stream, indent=2)
