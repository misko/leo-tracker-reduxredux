"""Bounded paired single-scan confirmation, with no reference-based selection."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('ds11_harness', HERE.parent/'harness.py')
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)
INDICES = (10, 18, 35, 60, 75)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fit(variant, index):
    import numpy as np
    from scipy.optimize import minimize
    import confirmation_model as model
    started = time.monotonic()
    plan_path = HERE/'plan.json'
    plan = json.loads(plan_path.read_text())
    entries = [r for r in plan['inputs'] if r['full_manifest_index'] == index]
    if index not in INDICES or len(entries) != 1 or variant not in ('original', 'fresh'):
        raise ValueError('invalid confirmation input')
    entry = entries[0]
    for artifact in entry['artifacts']:
        if 'sha256:'+digest(artifact['path']) != artifact['sha256']:
            raise ValueError('input artifact changed')
    docs = model.core.fast.load_documents(dict(config=plan['config'], inputs=[entry]))
    engine = model.build_model(docs, plan['config'], variant, index)
    bounds = [(-12., 12.), (-12., 12.), (-5., 5.)]
    seeds = [[float(e), 0., 0.] for e in (-2, 0, 2)]
    incumbent_path = HERE/'runs'/f'original_{index:02d}.json'
    baseline = None
    if variant == 'fresh':
        baseline = json.loads(incumbent_path.read_text())
        if (baseline['schema'] != 'ds11-causal-confirmation-fit/v1' or baseline['variant'] != 'original'
                or baseline['full_manifest_index'] != index or baseline['session'] != entry['session_id']):
            raise ValueError('baseline recording or arm binding differs')
        for source, expected in baseline['sources'].items():
            if digest(source) != expected:
                raise ValueError('baseline source changed')
        if baseline['fourth_seed'] is not None:
            seeds.append(baseline['fourth_seed'])
    starts = []
    fourth_seed = None
    reused = variant == 'fresh' and engine.metadata['changed_slots'] == 0
    if reused:
        starts = baseline['starts']
        fourth_seed = baseline['fourth_seed']
    else:
        # Original arm appends its best qualified three-start endpoint exactly
        # once. The fresh arm later receives that identical fourth seed.
        cursor = 0
        while cursor < len(seeds):
            seed = seeds[cursor]
            def objective(x):
                r = engine.evaluate(x)
                return -float(r['score']), -np.asarray(r['gradient'])
            result = minimize(objective, seed, jac=True, method='L-BFGS-B', bounds=bounds,
                              options=dict(maxiter=100, maxfun=160, ftol=1e-13,
                                           gtol=1e-6, maxls=25))
            discrepancies = []
            for axis, step in enumerate((1e-4, 1e-4, 1e-5)):
                delta = np.eye(3)[axis]*step
                numeric = (engine.evaluate(result.x+delta, False)['score']-
                           engine.evaluate(result.x-delta, False)['score'])/(2*step)
                discrepancies.append(abs(numeric+result.jac[axis]))
            audit = float(max(discrepancies))
            qualified, boundary, maximum = harness.qualify(result.success, result.x, result.jac, audit, bounds)
            starts.append(dict(seed=seed, x=result.x.tolist(), score=float(-result.fun),
                               success=bool(result.success), message=str(result.message),
                               gradient=maximum, audit=audit, boundary=boundary,
                               qualified=qualified, nfev=int(result.nfev), nit=int(result.nit)))
            cursor += 1
            if variant == 'original' and cursor == 3:
                valid = [s for s in starts if s['qualified']]
                if valid:
                    fourth_seed = max(valid, key=lambda s:s['score'])['x']
                    seeds.append(fourth_seed)
        if variant == 'fresh':
            fourth_seed = baseline['fourth_seed']
    valid = [s for s in starts if s['qualified']]
    selected = dict(max(valid, key=lambda s:s['score'])) if valid else None
    if selected:
        selected['estimate_deg'] = list(engine.engine.coordinates(np.asarray(selected['x'])))
        if reused and selected['estimate_deg'] != baseline['selected']['estimate_deg']:
            raise ValueError('no-op output differs from baseline')
    sources = [Path(__file__), HERE/'confirmation_model.py', HERE/'FIT_PROTOCOL.md',
               HERE.parent/'harness.py', HERE.parent/'causal_fresh/model.py', plan_path,
               harness.ROOT/'tools/ds7_baseline_adapter.py', harness.ROOT/'tools/ds7_fast_baseline_adapter.py']
    if baseline:
        sources.append(incumbent_path)
    output = dict(schema='ds11-causal-confirmation-fit/v1', variant=variant,
                  full_manifest_index=index, session=entry['session_id'], bounds=bounds,
                  starts=starts, fourth_seed=fourth_seed, selected=selected,
                  reused_unchanged_output=reused, metadata=engine.metadata,
                  elapsed_s=time.monotonic()-started, artifacts=entry['artifacts'],
                  sources={str(p):digest(p) for p in sources})
    with (HERE/'runs'/f'{variant}_{index:02d}.json').open('x') as stream:
        json.dump(output, stream, indent=2, allow_nan=False)


def batch(variant, indices):
    (HERE/'runs').mkdir(exist_ok=True)
    for index in indices:
        base = HERE/'runs'/f'{variant}_{index:02d}'
        receipt = base.with_suffix('.receipt.json')
        if receipt.exists():
            continue
        if base.with_suffix('.json').exists() or base.with_suffix('.log').exists():
            raise RuntimeError('unreceipted attempt needs audit')
        command = ['sudo', '-n', 'env', 'OPENBLAS_NUM_THREADS=1', 'OMP_NUM_THREADS=1',
                   'MKL_NUM_THREADS=1', 'timeout', '--kill-after=5s', '90s', 'nice', '-n', '19',
                   harness.PYTHON, str(Path(__file__)), 'fit', variant, str(index)]
        started = time.monotonic()
        with base.with_suffix('.log').open('x') as log:
            completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
        row = dict(variant=variant, full_manifest_index=index, exit_code=completed.returncode,
                   wall_s=time.monotonic()-started, command=command, runner_sha256=digest(__file__))
        with receipt.open('x') as stream:
            json.dump(row, stream, indent=2)
        print(json.dumps(row), flush=True)


if __name__ == '__main__':
    if sys.argv[1] == 'fit':
        fit(sys.argv[2], int(sys.argv[3]))
    elif sys.argv[1] == 'batch':
        batch(sys.argv[2], [int(i) for i in sys.argv[3].split(',')])
    else:
        raise ValueError(sys.argv[1])
