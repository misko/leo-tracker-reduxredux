"""Bounded, append-only single-scan comparisons using immutable DS11 exports."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import itertools
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = HERE.parent / '2026_09_30_ds11_single10'
PYTHON = '/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python'
SCREEN = list(range(0, 32, 4))
REFERENCE = (37.849056280893684, -122.48575489722863)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def distance(point):
    lat, lon = map(math.radians, point)
    a, b = map(math.radians, REFERENCE)
    h = math.sin((lat-a)/2)**2 + math.cos(lat)*math.cos(a)*math.sin((lon-b)/2)**2
    return 2*6371008.8*math.asin(math.sqrt(max(0., min(1., h))))


def percentile(values, q):
    values = sorted(values)
    p = (len(values)-1)*q
    lo = int(p)
    return values[lo] + (values[min(lo+1, len(values)-1)]-values[lo])*(p-lo)


def qualify(success, x, gradient, audit, bounds):
    free = [i for i, (lo, hi) in enumerate(bounds) if lo != hi]
    boundary = any(min(x[i]-bounds[i][0], bounds[i][1]-x[i]) < .001 for i in free)
    maximum = max([abs(float(gradient[i])) for i in free] + [0.])
    finite = all(math.isfinite(float(v)) for v in list(x)+list(gradient)+[audit])
    return bool(success and finite and not boundary and maximum <= .01 and audit <= .02), boundary, maximum


def load_plugin(family):
    path = HERE / family / 'model.py'
    spec = importlib.util.spec_from_file_location('ds11_' + family, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fit_one(family, variant, index, stage):
    import numpy as np
    from scipy.optimize import minimize
    sys.path.insert(0, str(ROOT / 'tools'))
    import ds7_fast_baseline_adapter as baseline
    baseline.baseline.profile = baseline.profile
    started = time.monotonic()
    plan = json.loads((BASE / 'plan.json').read_text())
    entry = plan['inputs'][index]
    for artifact in entry['artifacts']:
        assert 'sha256:' + digest(artifact['path']) == artifact['sha256']
    docs = baseline.load_documents(dict(config=plan['config'], inputs=[entry]))
    incumbent_path = BASE / 'runs' / f'{index:02d}_iid.json'
    incumbent = json.loads(incumbent_path.read_text())['selected']
    assert incumbent is not None
    plugin = load_plugin(family)
    model = plugin.build_model(docs, plan['config'], variant, index=index)
    bounds = getattr(model, 'bounds', [(-12., 12.), (-12., 12.), (-5., 5.)])
    seeds = [incumbent['x']] + [[east, 0., 0.] for east in (-2., 0., 2.)]
    starts = []
    for seed in seeds:
        seed = [max(lo, min(hi, v)) for v, (lo, hi) in zip(seed, bounds)]
        def objective(x):
            r = model.evaluate(x, gradient=True)
            return -float(r['score']), -np.asarray(r['gradient'])
        result = minimize(objective, seed, jac=True, method='L-BFGS-B', bounds=bounds,
                          options=dict(maxiter=100, maxfun=160, ftol=1e-13, gtol=1e-6, maxls=25))
        discrepancies = []
        for axis, step in enumerate((1e-4, 1e-4, 1e-5)):
            if bounds[axis][0] == bounds[axis][1]:
                continue
            delta = np.eye(3)[axis]*step
            numerical = (model.evaluate(result.x+delta, gradient=False)['score'] -
                         model.evaluate(result.x-delta, gradient=False)['score'])/(2*step)
            discrepancies.append(abs(numerical + result.jac[axis]))
        audit = float(max(discrepancies, default=0.))
        qualified, boundary, maximum = qualify(result.success, result.x, result.jac, audit, bounds)
        starts.append(dict(seed=seed, x=result.x.tolist(), score=float(-result.fun),
                           success=bool(result.success), message=str(result.message),
                           gradient=maximum, audit=audit, boundary=boundary, qualified=qualified,
                           nfev=int(result.nfev), nit=int(result.nit)))
    valid = [s for s in starts if s['qualified']]
    selected = max(valid, key=lambda s: s['score']) if valid else None
    if selected:
        selected = dict(selected)
        geometry = baseline.Stationary(docs[0], plan['config'])
        x = np.asarray(selected['x'])
        selected['estimate_deg'] = list(geometry.coordinates(x))
        # Score both endpoints under the unchanged IID measurement model.
        def iid_scores(point):
            train_total, held_total = 0., 0.
            for track in docs[0]['tracks']:
                prediction, visible = geometry.prediction(track, np.asarray(point))
                train, joint, audits, _ = baseline.profile(track['y'][None, :]-prediction, track['mask'])
                assert all(a['converged'] for a in audits)
                t = np.logaddexp.reduce(np.where(visible, train, -np.inf))
                j = np.logaddexp.reduce(np.where(visible, joint, -np.inf))
                train_total += float(t-math.log(track['catalogue_size']))
                held_total += float(j-t)
            return dict(train=train_total, held=held_total)
        selected['common_iid'] = iid_scores(x)
        selected['incumbent_common_iid'] = iid_scores(incumbent['x'])
        assert abs(selected['incumbent_common_iid']['train']-incumbent['score']) < 1e-6
    sources = [HERE/'harness.py', HERE/'PROTOCOL.md', HERE/family/'model.py',
               BASE/'plan.json', incumbent_path, ROOT/'tools/ds7_baseline_adapter.py',
               ROOT/'tools/ds7_fast_baseline_adapter.py']
    record = dict(family=family, variant=variant, index=index, stage=stage,
                  session=entry['session_id'], bounds=bounds, starts=starts, selected=selected,
                  metadata=getattr(model, 'metadata', {}), elapsed_s=time.monotonic()-started,
                  artifacts=entry['artifacts'], sources={str(p):digest(p) for p in sources})
    output = HERE/family/'runs'/stage/f'{variant}_{index:02d}.json'
    with output.open('x') as stream:
        json.dump(record, stream, indent=2, allow_nan=False)


def batch(family, variants, indices, stage):
    folder = HERE/family/'runs'/stage
    folder.mkdir(parents=True, exist_ok=True)
    for variant, index in itertools.product(variants, indices):
        base = folder/f'{variant}_{index:02d}'
        receipt = base.with_suffix('.receipt.json')
        if receipt.exists():
            print('Existing terminal attempt retained:', receipt, flush=True)
            continue
        if base.with_suffix('.log').exists() or base.with_suffix('.json').exists():
            raise RuntimeError(f'Unreceipted attempt requires process audit: {base}')
        cmd = ['sudo', '-n', 'env', 'OPENBLAS_NUM_THREADS=1', 'OMP_NUM_THREADS=1',
               'MKL_NUM_THREADS=1', 'timeout', '--kill-after=5s', '90s', 'nice', '-n', '19',
               PYTHON, str(HERE/'harness.py'), 'fit', family, variant, str(index), stage]
        started = time.monotonic()
        with base.with_suffix('.log').open('x') as log:
            completed = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT)
        row = dict(family=family, variant=variant, index=index, exit_code=completed.returncode,
                   wall_s=time.monotonic()-started, command=cmd)
        with receipt.open('x') as stream:
            json.dump(row, stream, indent=2)
        print(json.dumps(row), flush=True)


def summarize(family, stage):
    folder = HERE/family/'runs'/stage
    rows = []
    for receipt in sorted(folder.glob('*.receipt.json')):
        r = json.loads(receipt.read_text())
        output = receipt.with_name(receipt.name.replace('.receipt.json', '.json'))
        result = json.loads(output.read_text()) if output.exists() else None
        selected = result['selected'] if result else None
        old = json.loads((BASE/'runs'/f"{r['index']:02d}_iid.json").read_text())['selected']
        rows.append(dict(index=r['index'], variant=r['variant'], exit_code=r['exit_code'],
                         qualified=bool(selected and r['exit_code']==0),
                         error_m=distance(selected['estimate_deg']) if selected else None,
                         baseline_error_m=distance(old['estimate_deg']), wall_s=r['wall_s'],
                         common_iid_held_gain=(selected['common_iid']['held']-
                                              selected['incumbent_common_iid']['held']) if selected else None))
    summaries = []
    for variant in sorted({r['variant'] for r in rows}):
        group = [r for r in rows if r['variant']==variant]
        good = [r for r in group if r['qualified']]
        errors = [r['error_m'] for r in good]
        old = [r['baseline_error_m'] for r in group]
        median = statistics.median(errors) if errors else None
        p90 = percentile(errors, .9) if errors else None
        wins = sum(r['error_m'] < r['baseline_error_m'] for r in good)
        gate = (set(r['index'] for r in group)==set(SCREEN) and len(good)==8 and wins>=4
                and median <= .9*statistics.median(old) and p90 <= 1.1*percentile(old,.9))
        summaries.append(dict(variant=variant, attempts=len(group), qualified=len(good),
                              median_m=median, p90_m=p90, max_m=max(errors) if errors else None,
                              baseline_median_m=statistics.median(old), baseline_p90_m=percentile(old,.9),
                              wins=wins, subkm=sum(e<1000 for e in errors),
                              common_iid_held_gain=sum(r['common_iid_held_gain'] for r in good),
                              median_wall_s=statistics.median(r['wall_s'] for r in group), screen_gate=gate))
    print(json.dumps(dict(summary=summaries, rows=rows), indent=2))


if __name__ == '__main__':
    action = sys.argv[1]
    if action == 'fit':
        fit_one(sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5])
    elif action == 'batch':
        indices = SCREEN if sys.argv[4]=='screen' else list(range(32)) if sys.argv[4]=='all' else [int(x) for x in sys.argv[4].split(',')]
        batch(sys.argv[2], sys.argv[3].split(','), indices, sys.argv[5])
    elif action == 'summarize':
        summarize(sys.argv[2], sys.argv[3])
    else:
        raise ValueError(action)
