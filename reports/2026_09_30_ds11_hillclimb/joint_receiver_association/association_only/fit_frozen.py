import json
from pathlib import Path
import sys
import time
import numpy as np
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'acquisition_position'))
from common import JOBS, base, read, digest
from fit import load
from position_run import audit
from model import AssociationOnlyPosition


def main(cohort, index, arm, verify=False):
    started = time.monotonic()
    old, initial, sources = load(cohort, index, arm)
    previous = HERE.parent / 'acquisition_position'
    model = AssociationOnlyPosition(old.geometry.document, read(base(cohort) / 'plan.json')['config'], read(previous / f'input-{cohort}-{index:02d}.json'), old.calibration, arm, initial)
    sources.update({str(p): digest(p) for p in (Path(__file__), HERE / 'model.py', HERE / 'test_model.py', HERE / 'PROTOCOL.md')})
    first = model.evaluate(initial)
    if verify:
        for tid, track in model.tracks.items():
            np.testing.assert_array_equal(model.receiver_probabilities(track, tid, initial), old.receiver_probabilities(track, tid, initial))
            np.testing.assert_array_equal(model.receiver_probabilities(track, tid, initial), model.receiver_probabilities(track, tid, initial + [1., 1., .1]))
        checked = audit(model, initial, first['gradient'])
        assert checked['discrepancy'] <= .02
        result = dict(verified=True, derivative_audit=checked)
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
    result.update(cohort=cohort, index=index, arm=arm, sources=sources, elapsed_s=time.monotonic() - started, reference_used=False, receiver_geometry_frozen=True)
    prefix = 'verify' if verify else 'fit'
    with (HERE / f'{prefix}-{cohort}-{index:02d}-{arm}.json').open('x') as f:
        json.dump(result, f, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in result.items() if k != 'sources'}), flush=True)


if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]), sys.argv[3], '--verify' in sys.argv)
