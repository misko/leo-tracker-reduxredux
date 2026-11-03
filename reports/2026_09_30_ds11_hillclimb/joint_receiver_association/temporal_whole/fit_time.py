import json
from pathlib import Path
import sys
import time
import numpy as np
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'acquisition_position'))
from common import JOBS, base, read, digest, verify_sources
from fit import load
from position_run import audit
from time_model import TemporalWholeSourcePosition


def main(cohort, index, arm, verify=False):
    started = time.monotonic()
    old, initial, sources = load(cohort, index, 'signed' if arm == 'candidate' else 'doppler')
    family = next(f for c, i, f in JOBS if (c, i) == (cohort, index))
    taupath = HERE.parent / f'temporal_acquisition/fit-{family}.json'
    temporal = read(taupath)
    verify_sources(temporal)
    assert temporal['fit']['qualified']
    selected_arm = 'signed' if arm == 'candidate' and temporal['passed'] else 'doppler'
    model = TemporalWholeSourcePosition(old.geometry.document, read(base(cohort) / 'plan.json')['config'], read(HERE.parent / 'acquisition_position' / f'input-{cohort}-{index:02d}.json'), old.calibration, selected_arm, temporal['tau_s'])
    sources.update({str(p): digest(p) for p in (Path(__file__), HERE / 'time_model.py', HERE / 'batched_filter.py', HERE / 'test_time_model.py', HERE / 'PROTOCOL.md', taupath)})
    begin = time.monotonic()
    first = model.evaluate(initial)
    evaluation_s = time.monotonic() - begin
    if verify:
        checked = audit(model, initial, first['gradient'])
        assert checked['discrepancy'] <= .02
        model.tau_s = 0.
        independent = model.evaluate(initial)
        expected = old.evaluate(initial)
        parity = dict(score=abs(independent['score'] - expected['score']), gradient=float(np.max(abs(independent['gradient'] - expected['gradient']))))
        assert parity['score'] < 1e-8 and parity['gradient'] < 1e-7
        result = dict(verified=True, derivative_audit=checked, zero_tau_parity=parity, evaluation_s=evaluation_s)
    else:
        def objective(x):
            value = model.evaluate(x)
            return -value['score'], -value['gradient']
        fit = minimize(objective, initial, method='L-BFGS-B', jac=True, bounds=[(-12., 12.), (-12., 12.), (-5., 5.)], options=dict(maxiter=100, ftol=1e-13, gtol=.001, maxls=25))
        final = model.evaluate(fit.x)
        checked = audit(model, fit.x, final['gradient'])
        margin = float(np.min(np.array([12., 12., 5.]) - abs(fit.x)))
        gradient = float(np.max(abs(final['gradient'])))
        joint = model.evaluate(fit.x, gradient=False, held=True)
        result = dict(x=fit.x.tolist(), coordinates_deg=model.geometry.coordinates(fit.x), initial_x=initial.tolist(), score=final['score'], held_score=joint['score'] - final['score'], expected_sources=final['expected_sources'], qualified=bool(fit.success and margin >= .001 and gradient <= .01 and checked['discrepancy'] <= .02), derivative_audit=checked, bound_margin=margin, gradient_max=gradient, optimizer=dict(success=bool(fit.success), message=str(fit.message), iterations=int(fit.nit), evaluations=int(fit.nfev)))
    result.update(cohort=cohort, index=index, family=family, arm=arm, selected_arm=selected_arm, fallback=arm == 'candidate' and selected_arm == 'doppler', tau_s=temporal['tau_s'], sources=sources, elapsed_s=time.monotonic() - started, reference_used=False)
    prefix = 'verify' if verify else 'fit'
    with (HERE / f'{prefix}-{cohort}-{index:02d}-{arm}.json').open('x') as f:
        json.dump(result, f, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in result.items() if k != 'sources'}), flush=True)


if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]), sys.argv[3], '--verify' in sys.argv)
