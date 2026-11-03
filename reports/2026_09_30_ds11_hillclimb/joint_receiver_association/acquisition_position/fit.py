"""Position fitting without reference coordinates or reference-error selection."""
import inspect
import json
from pathlib import Path
import sys
import time
import numpy as np
from scipy.optimize import minimize
from common import HERE, PARENT, JOBS, base, read, digest, fast, bindings, verify_sources
from whole_source_fast import WholeSourcePosition
from position_run import audit


def load(cohort, index, arm):
    family = next(f for c, i, f in JOBS if (c, i) == (cohort, index))
    planpath = base(cohort) / 'plan.json'
    plan = read(planpath)
    entry = plan['inputs'][index]
    boundpath = HERE / f'input-{cohort}-{index:02d}.json'
    calpath = PARENT / f'acquisition_calibration/fit-{family}.json'
    initialpath = base(cohort) / f'runs/{index:02d}_iid.json'
    bound, calibration = read(boundpath), read(calpath)
    for obj in (bound, calibration):
        verify_sources(obj)
    assert calibration['screen']['passed']
    assert all(a['selected']['qualified'] for a in calibration['arms'].values())
    doc = fast.load_documents(dict(config=plan['config'], inputs=[entry]))[0]
    obs_path = next(a['path'] for a in entry['artifacts'] if a['kind'] == 'observations')
    bank_path = next(a['path'] for a in entry['artifacts'] if a['kind'] == 'candidates' and a['path'].endswith('.npz'))
    manifest_path = next(a['path'] for a in entry['artifacts'] if a['kind'] == 'candidates' and a['path'].endswith('.json'))
    manifest = read(manifest_path)
    assert all(s['collected_utc_ns'] < doc['start_utc_ns'] for s in manifest['provider_sources'])
    idpath = PARENT.parent / 'source_balance/catalogue_identities.json' if cohort == 'original' else base(cohort) / 'catalogue_identities.json'
    identity = read(idpath)['scans'][str(index)]
    assert identity['bank_sha256'] == digest(bank_path)
    assert identity['manifest_sha256'] == digest(manifest_path)
    assert identity['observation_sha256'] == digest(obs_path)
    assert identity['session_id'] == entry['session_id']
    assert calibration['sample_rate_hz'] == read(obs_path)['sample_rate_hz']
    assert sorted({t['rf_hz'] for t in doc['tracks']}) == calibration['frequencies']
    with np.load(bank_path, allow_pickle=False) as bank:
        for t in manifest['tracks']:
            np.testing.assert_array_equal(bank[f"candidate_ids_{t['index']}"], identity['tracks'][t['track_id']]['candidate_ids'])
    initial = np.array(read(initialpath)['selected']['x'])
    sources = bindings([planpath, boundpath, calpath, initialpath, idpath, HERE / 'PROTOCOL.md', HERE / 'common.py', Path(__file__), *[PARENT / p for p in ('whole_source_fast.py', 'whole_source_position.py', 'source_partition_fast.py', 'source_partition.py', 'joint_position.py', 'position_run.py', 'doppler_pilot.py')], inspect.getfile(fast), inspect.getfile(fast.baseline)])
    return WholeSourcePosition(doc, plan['config'], bound, calibration, arm), initial, sources


def main(cohort, index, arm, verify=False):
    started = time.monotonic()
    model, initial, sources = load(cohort, index, arm)
    first = model.evaluate(initial)
    if verify:
        control, _, _ = load(cohort, index, 'doppler')
        collapsed = control.evaluate(initial)
        exact = control.evaluate(initial, force_partition=True)
        parity = dict(score=abs(collapsed['score'] - exact['score']), gradient=float(np.max(abs(collapsed['gradient'] - exact['gradient']))), expected_sources=abs(collapsed['expected_sources'] - exact['expected_sources']))
        assert parity['score'] < 1e-8 and parity['gradient'] < 1e-7 and parity['expected_sources'] < 1e-7
        checked = audit(model, initial, first['gradient'])
        assert checked['discrepancy'] <= .02
        result = dict(parity=parity, derivative_audit=checked, verified=True)
    else:
        def objective(x):
            value = model.evaluate(x)
            return -value['score'], -value['gradient']
        fit = minimize(objective, initial, method='L-BFGS-B', jac=True, bounds=[(-12., 12.), (-12., 12.), (-5., 5.)], options=dict(maxiter=100, ftol=1e-15, gtol=1e-5))
        final = model.evaluate(fit.x)
        checked = audit(model, fit.x, final['gradient'])
        margin = float(np.min(np.array([12., 12., 5.]) - abs(fit.x)))
        grad = float(np.max(abs(final['gradient'])))
        qualified = bool(fit.success and margin >= .001 and grad <= .01 and checked['discrepancy'] <= .02)
        joint = model.evaluate(fit.x, gradient=False, held=True)
        result = dict(x=fit.x.tolist(), coordinates_deg=model.geometry.coordinates(fit.x), initial_x=initial.tolist(), initial_score=first['score'], score=final['score'], held_score=joint['score'] - final['score'], expected_sources=final['expected_sources'], qualified=qualified, derivative_audit=checked, bound_margin=margin, gradient_max=grad, optimizer=dict(success=bool(fit.success), message=str(fit.message), iterations=int(fit.nit), evaluations=int(fit.nfev)))
    result.update(cohort=cohort, index=index, arm=arm, sources=sources, elapsed_s=time.monotonic() - started, reference_used=False)
    prefix = 'verify' if verify else 'fit'
    with (HERE / f'{prefix}-{cohort}-{index:02d}-{arm}.json').open('x') as f:
        json.dump(result, f, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in result.items() if k != 'sources'}), flush=True)


if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]), sys.argv[3], '--verify' in sys.argv)
