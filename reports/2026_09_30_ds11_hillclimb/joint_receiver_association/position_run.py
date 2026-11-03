"""Bounded training-only fit, or full-objective derivative/parity verification."""
import argparse
import json
from pathlib import Path
import time
import numpy as np
from scipy.optimize import minimize
from joint_position import JointPosition
from doppler_pilot import fast, digest, read

HERE = Path(__file__).resolve().parent


def load(index, arm):
    base = HERE.parent.parent / '2026_09_30_ds11_single10'
    plan = read(base / 'plan.json')
    bound_path = HERE / f'input-{index:02d}.json'
    bound = read(bound_path)
    cal_path = HERE / 'conditional-fit.json'
    calibration = read(cal_path)
    assert calibration['signed_screen_passed']
    sources = {}
    for obj in (bound, calibration):
        for p, h in obj['sources'].items():
            assert digest(p) == h, p
    original_path = base / f'runs/{index:02d}_iid.json'
    original = read(original_path)['selected']
    doc = fast.load_documents(dict(config=plan['config'], inputs=[plan['inputs'][index]]))[0]
    for path in (base / 'plan.json', original_path, bound_path, cal_path, Path(__file__), HERE / 'joint_position.py', HERE / 'POSITION_PROTOCOL.md', HERE / 'matching.py', HERE / 'doppler_pilot.py'):
        sources[str(path)] = digest(path)
    return JointPosition(doc, plan['config'], bound, calibration, arm), np.array(original['x']), sources


def audit(model, x, analytic):
    numerical = []
    for axis, step in enumerate((1e-3, 1e-3, 1e-4)):
        d = np.eye(3)[axis] * step
        numerical.append((model.evaluate(x + d, gradient=False)['score'] - model.evaluate(x - d, gradient=False)['score']) / (2 * step))
    return dict(numerical=numerical, analytic=analytic.tolist(), discrepancy=float(np.max(np.abs(analytic - numerical))))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--index', type=int, required=True)
    parser.add_argument('--arm', choices=['doppler', 'receiver', 'signed', 'swapped', 'permuted'], required=True)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    start = time.monotonic()
    model, initial, sources = load(args.index, args.arm)
    first = model.evaluate(initial)
    if args.verify:
        checked = audit(model, initial, first['gradient'])
        assert checked['discrepancy'] <= .02, checked
        parity = None
        if args.arm == 'doppler':
            original = next(r for r in read(HERE / 'doppler-pilot.json')['rows'] if r['index'] == args.index)
            parity = first['score'] - original['training_score']
            assert abs(parity) < 1e-8
        output = dict(verification=checked, parity_difference=parity, initial_score=first['score'])
    else:
        def objective(x):
            out = model.evaluate(x)
            return -out['score'], -out['gradient']
        fit = minimize(objective, initial, method='L-BFGS-B', jac=True, bounds=[(-12., 12.), (-12., 12.), (-5., 5.)], options=dict(maxiter=100, ftol=1e-12, gtol=1e-5))
        final = model.evaluate(fit.x)
        checked = audit(model, fit.x, final['gradient'])
        margin = np.min(np.array([12., 12., 5.]) - np.abs(fit.x))
        qualified = bool(fit.success and margin >= .001 and np.max(np.abs(final['gradient'])) <= .01 and checked['discrepancy'] <= .02)
        joint = model.evaluate(fit.x, gradient=False, held=True)
        output = dict(x=fit.x.tolist(), coordinates_deg=model.geometry.coordinates(fit.x), initial_x=initial.tolist(), initial_score=first['score'], score=final['score'], held_score=joint['score'] - final['score'], expected_pairs=final['expected_pairs'], lane_diagnostics=[{k: v for k, v in row.items() if k != 'gradient'} for row in final['lanes']], optimizer=dict(success=bool(fit.success), message=str(fit.message), iterations=int(fit.nit), evaluations=int(fit.nfev)), derivative_audit=checked, qualified=qualified)
    output.update(index=args.index, arm=args.arm, sources=sources, elapsed_s=time.monotonic() - start, reference_used=False)
    path = HERE / f"{'verify' if args.verify else 'position'}-{args.index:02d}-{args.arm}.json"
    with path.open('x') as f:
        json.dump(output, f, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in output.items() if k not in ('sources', 'lane_diagnostics')}, indent=2), flush=True)


if __name__ == '__main__':
    main()
