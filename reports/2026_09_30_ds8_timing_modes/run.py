"""Fine training timing profiles on scans selected by endpoint disagreement."""
import hashlib
import importlib.util
import json
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent


def read(path):
    return json.loads(path.read_text())


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def main():
    started = time.monotonic()
    paths = [REPORTS/'2026_09_29_ds8_union40'/f'{a}.json' for a in ['old', 'rank']]
    old, rank = [read(p) for p in paths]
    corrected_path = REPORTS/'2026_09_29_ds8_union_timing/refit_old.json'
    corrected = read(corrected_path)
    hashes = {}
    for result in [old, rank, corrected, read(REPORTS/'2026_09_29_ds8_sampling_diagnostic/results.json')]:
        for name, digest in result['hashes'].items():
            assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
            hashes[name] = digest
    assert all(r['fit']['qualified'] for r in [old, rank, corrected])
    sessions = old['sessions']
    assert sessions == rank['sessions']
    selected = [i for i in range(40) if abs(old['fit']['x'][i+2]-rank['fit']['x'][i+2]) > .1]
    assert len(selected) == 3
    plan = read(REPORTS/'2026_09_29_scan_budget/manifest.json')
    new = read(REPORTS/'2026_09_29_rank24_control/plan.json')
    assert plan['config'] == new['config']
    inputs = {}
    for scans in [next(s for s in plan['sets'] if s['unit']=='DS8_n24_0')['scans'], next(s for s in new['sets'] if s['dataset']=='DS8')['scans']]:
        inputs.update({s['session_id']:s['input'] for s in scans})
    budget = module('budget', REPORTS/'2026_09_29_scan_budget/run.py')
    helper = budget.helper
    timing_path = REPORTS/'2026_09_29_disjoint_frozen_association/run.py'
    timing = module('timing_control', timing_path).timing_fit
    docs = helper.baseline.load_documents(dict(config=plan['config'], inputs=[inputs[sessions[i]] for i in selected]))
    grid = np.linspace(-5, 5, 401)
    rows = []
    for i, doc in zip(selected, docs, strict=True):
        assert doc['session_id'] == sessions[i]
        model = helper.TrendMixturePosition([doc], plan['config'], helper.baseline.Stationary, .2)
        for arm, result in [('corrected', corrected), ('rank', rank)]:
            position = result['fit']['x'][:2]
            inherited_tau = result['fit']['x'][i+2]
            scores, _ = budget.training_scores(model, position, grid)
            indices = [j for j in range(len(grid)) if (j==0 or scores[j]>scores[j-1]) and (j==len(grid)-1 or scores[j]>scores[j+1])]
            best_grid = int(np.argmax(scores))
            audit = abs(scores[best_grid]-model.evaluate([*position,grid[best_grid]], gradient=False)['score'])
            assert audit < 1e-7
            inherited = model.evaluate([*position,inherited_tau], gradient=False, held=True)
            replay, _ = budget.training_scores(model, position, np.array([inherited_tau]))
            assert abs(replay[0]-inherited['score']) < 1e-7
            attempts = []
            for label, tau in [('inherited', inherited_tau)]+[(f'grid_{j}',float(grid[j])) for j in indices]:
                fit = dict(timing(model, np.array(position), [tau]), start=label, initial_tau_s=tau)
                if fit['qualified']:
                    out = model.evaluate(fit['x'], gradient=False, held=True)
                    fit['held_score'] = sum(r['held_log_score'] for r in out['rows'])
                attempts.append(fit)
            valid = [f for f in attempts if f['qualified']]
            best = max(valid, key=lambda f:f['score']) if valid else None
            rows.append(dict(session_id=sessions[i], arm=arm, position=position,
                             inherited_tau_s=inherited_tau, inherited_training=inherited['score'],
                             inherited_held=sum(r['held_log_score'] for r in inherited['rows']),
                             grid_scores=scores.tolist(), peak_indices=indices, attempts=attempts, selected=best,
                             scalar_audit=audit))
    for p in paths+[corrected_path,HERE/'run.py',HERE/'PROTOCOL.md',timing_path,REPORTS/'2026_09_29_marginal_timing_fit/timing_model.py']:
        hashes[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    result = dict(rows=rows,grid_s=grid.tolist(),hashes=hashes,elapsed_seconds=time.monotonic()-started)
    with (HERE/'results.json').open('x') as out:
        json.dump(result,out,indent=2,allow_nan=False)
    for r in rows:
        b=r['selected']
        print(r['session_id'],r['arm'],'peaks',len(r['peak_indices']),'qualified',b is not None,
              'training_gain',None if b is None else b['score']-r['inherited_training'],flush=True)
    print('elapsed_seconds',result['elapsed_seconds'])


if __name__ == '__main__':
    main()
