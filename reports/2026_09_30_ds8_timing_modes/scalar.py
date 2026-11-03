"""Independent bracketed scalar validation for every detected timing peak."""
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar

from run import HERE, REPORTS, module, read


def main():
    prior = read(HERE/'results.json')
    for name, digest in prior['hashes'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
    helper = module('budget', REPORTS/'2026_09_29_scan_budget/run.py').helper
    old = read(REPORTS/'2026_09_29_scan_budget/manifest.json')
    new = read(REPORTS/'2026_09_29_rank24_control/plan.json')
    inputs = {}
    for scans in [next(s for s in old['sets'] if s['unit']=='DS8_n24_0')['scans'],next(s for s in new['sets'] if s['dataset']=='DS8')['scans']]:
        inputs.update({s['session_id']:s['input'] for s in scans})
    sessions = list(dict.fromkeys(r['session_id'] for r in prior['rows']))
    docs = helper.baseline.load_documents(dict(config=old['config'],inputs=[inputs[s] for s in sessions]))
    models = {d['session_id']:helper.TrendMixturePosition([d],old['config'],helper.baseline.Stationary,.2) for d in docs}
    grid = prior['grid_s']
    rows = []
    for row in prior['rows']:
        model = models[row['session_id']]
        position = row['position']
        def score(t):
            return model.evaluate([*position,t],gradient=False)['score']
        peaks = []
        for j in row['peak_indices']:
            bounds = (grid[max(0,j-1)],grid[min(len(grid)-1,j+1)])
            fit = minimize_scalar(lambda t:-score(t),bounds=bounds,method='bounded',options=dict(xatol=1e-10,maxiter=100))
            x = [*position,float(fit.x)]
            out = model.evaluate(x,held=True)
            derivative = float(out['gradient'][2])
            numerical = (score(x[2]+1e-5)-score(x[2]-1e-5))/2e-5
            audit = abs(derivative-numerical)
            qualified = bool(fit.success and abs(x[2])<4.999 and abs(derivative)<=.01 and audit<=.02 and out['score']>=row['grid_scores'][j]-1e-7)
            peaks.append(dict(grid_index=j,x=x,score=out['score'],held_score=sum(t['held_log_score'] for t in out['rows']),
                              success=bool(fit.success),message=str(fit.message),gradient=derivative,gradient_audit=audit,qualified=qualified))
        valid = [p for p in peaks if p['qualified']]
        best = max(valid,key=lambda p:p['score']) if valid else None
        rows.append(dict(session_id=row['session_id'],arm=row['arm'],peaks=peaks,selected=best,
                         training_gain=None if best is None else best['score']-row['inherited_training'],
                         held_gain=None if best is None else best['held_score']-row['inherited_held']))
    paths = [HERE/'results.json',HERE/'scalar.py',HERE/'SCALAR_PROTOCOL.md']
    with (HERE/'scalar-results.json').open('x') as out:
        json.dump(dict(rows=rows,hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}),out,indent=2,allow_nan=False)
    for r in rows:
        print(r['session_id'],r['arm'],r['training_gain'],r['held_gain'],sum(p['qualified'] for p in r['peaks']),len(r['peaks']))


if __name__=='__main__':
    main()
