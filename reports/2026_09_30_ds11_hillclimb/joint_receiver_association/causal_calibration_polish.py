"""Resolve premature relative-tolerance termination without relaxing qualification."""
import json
from pathlib import Path
import time
import numpy as np
from scipy.optimize import minimize
from causal_calibration_geometry import helper
from doppler_pilot import read, digest

HERE = Path(__file__).resolve().parent


def main():
    start = time.monotonic()
    original_path = HERE / 'causal-calibration-geometry.json'
    original = read(original_path)
    fit = original['fit']
    assert fit['success'] and not fit['boundary'] and not fit['qualified'] and fit['gradient_audit'] < .0001
    for p, h in original['sources'].items():
        assert digest(p) == h, p
    plan = read(HERE.parent.parent / '2026_09_30_ds10_scale_weighting/plan.json')
    entries = [plan['inputs'][i] for i in original['indices']]
    docs = helper.baseline.load_documents(dict(config=original['config'], inputs=entries))
    model = helper.TrendMixturePosition(docs, original['config'], helper.baseline.Stationary, .2)
    x = np.array(fit['x'])
    bounds = [(-12., 12.)] * 2 + [(-5., 5.)] * (len(x) - 2)
    def objective(z):
        out = model.evaluate(z)
        return -out['score'], -out['gradient']
    result = minimize(objective, x, jac=True, method='L-BFGS-B', bounds=bounds, options=dict(maxiter=100, maxfun=160, ftol=1e-15, gtol=1e-6, maxls=25))
    differences = []
    for i, step in enumerate([1e-4, 1e-4] + [1e-5] * (len(x) - 2)):
        d = np.eye(len(x))[i] * step
        numerical = (model.evaluate(result.x + d, gradient=False)['score'] - model.evaluate(result.x - d, gradient=False)['score']) / (2 * step)
        differences.append(abs(numerical + result.jac[i]))
    boundary = any(min(v - lo, hi - v) < .001 for v, (lo, hi) in zip(result.x, bounds))
    gradient = float(np.max(np.abs(result.jac)))
    qualified = bool(result.success and not boundary and gradient <= .01 and max(differences) <= .02 and -result.fun >= fit['score'] - 1e-7)
    revised = dict(x=result.x.tolist(), score=float(-result.fun), success=bool(result.success), message=str(result.message), boundary=boundary, projected_gradient=gradient, gradient_audit=float(max(differences)), qualified=qualified, iterations=int(result.nit), evaluations=int(result.nfev))
    sources = dict(original['sources'])
    for p in (original_path, Path(__file__), HERE / 'CAUSAL_CALIBRATION_POLISH.md'):
        sources[str(p)] = digest(p)
    output = {k: v for k, v in original.items() if k not in ('fit', 'sources', 'elapsed_s')}
    output.update(fit=revised, original_unqualified_preserved=True, sources=sources, elapsed_s=time.monotonic() - start)
    with (HERE / 'causal-calibration-geometry.polished.json').open('x') as f:
        json.dump(output, f, indent=2, allow_nan=False)
    print(json.dumps(dict(qualified=qualified, score=revised['score'], gradient=gradient, audit=revised['gradient_audit'], elapsed_s=output['elapsed_s']), indent=2), flush=True)


if __name__ == '__main__':
    main()
