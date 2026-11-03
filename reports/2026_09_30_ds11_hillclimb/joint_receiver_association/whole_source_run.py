"""Bounded exact whole-source verification and positional pilot."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
from scipy.optimize import minimize
from position_run import audit, load
from whole_source_position import WholeSourcePosition
from doppler_pilot import fast, read, digest

HERE = Path(__file__).resolve().parent


def load_model(cohort, index, arm):
    sources = {}
    if cohort == 'original':
        old, initial, sources = load(index, arm)
        base = HERE.parent.parent / '2026_09_30_ds11_single10'
        plan = read(base / 'plan.json')
        bound = read(HERE / f'input-{index:02d}.json')
        doc = old.geometry.document
    else:
        assert index == 1
        base = HERE.parent / 'additional'
        plan = read(base / 'plan.json')
        bound = read(HERE / 'additional-input-01.json')
        initial = np.array(read(base / 'runs/01_iid.json')['selected']['x'])
        doc = fast.load_documents(dict(config=plan['config'], inputs=[plan['inputs'][index]]))[0]
        for path in (base / 'plan.json', base / 'runs/01_iid.json', HERE / 'additional-input-01.json'):
            sources[str(path)] = digest(path)
    calibration = read(HERE / 'conditional-fit.json')
    for obj in (bound, calibration):
        for p, h in obj['sources'].items():
            assert digest(p) == h, p
    model = WholeSourcePosition(doc, plan['config'], bound, calibration, arm)
    control = WholeSourcePosition(doc, plan['config'], bound, calibration, 'doppler')
    for path in (Path(__file__), HERE / 'WHOLE_SOURCE_PROTOCOL.md', HERE / 'whole_source_position.py', HERE / 'source_partition.py', HERE / 'test_source_partition.py', HERE / 'test_whole_source_position.py', HERE / 'conditional-fit.json', HERE / 'joint_position.py', HERE / 'position_run.py'):
        sources[str(path)] = digest(path)
    return model, control, initial, sources


def fit(cohort, index, arm, verify=False):
    start = time.monotonic()
    model, control, initial, sources = load_model(cohort, index, arm)
    if verify:
        a, b = control.evaluate(initial), control.evaluate(initial, force_partition=True)
        parity = dict(score=a['score'] - b['score'], gradient=float(np.max(np.abs(a['gradient'] - b['gradient']))), expected_sources=a['expected_sources'] - b['expected_sources'])
        assert abs(parity['score']) < 1e-8 and parity['gradient'] < 1e-7 and abs(parity['expected_sources']) < 1e-7
        begin = time.monotonic()
        first = model.evaluate(initial)
        evaluation_s = time.monotonic() - begin
        checked = audit(model, initial, first['gradient'])
        assert checked['discrepancy'] <= .02
        output = dict(parity=parity, derivative_audit=checked, score=first['score'], expected_sources=first['expected_sources'], evaluation_s=evaluation_s)
    else:
        def objective(x):
            out = model.evaluate(x)
            return -out['score'], -out['gradient']
        result = minimize(objective, initial, method='L-BFGS-B', jac=True, bounds=[(-12., 12.), (-12., 12.), (-5., 5.)], options=dict(maxiter=100, ftol=1e-12, gtol=1e-5))
        final = model.evaluate(result.x)
        checked = audit(model, result.x, final['gradient'])
        qualified = bool(result.success and np.min(np.array([12., 12., 5.]) - np.abs(result.x)) >= .001 and np.max(np.abs(final['gradient'])) <= .01 and checked['discrepancy'] <= .02)
        joint = model.evaluate(result.x, gradient=False, held=True)
        output = dict(x=result.x.tolist(), coordinates_deg=model.geometry.coordinates(result.x), score=final['score'], held_score=joint['score'] - final['score'], qualified=qualified, derivative_audit=checked, optimizer=dict(success=bool(result.success), message=str(result.message), iterations=int(result.nit), evaluations=int(result.nfev)), expected_sources=final['expected_sources'], lane_diagnostics=final['lanes'])
    output.update(cohort=cohort, index=index, arm=arm, sources=sources, elapsed_s=time.monotonic() - start)
    path = HERE / f"whole-{'verify-' if verify else ''}{cohort}-{index:02d}-{arm}.json"
    with path.open('x') as f:
        json.dump(output, f, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in output.items() if k not in ('sources', 'lane_diagnostics')}), flush=True)


def child(cohort, index, arm):
    start = time.monotonic()
    prefix = HERE / f'whole-{cohort}-{index:02d}-{arm}'
    log = prefix.with_suffix('.log')
    with log.open('x') as f:
        try:
            code = subprocess.run([sys.executable, str(Path(__file__)), '--cohort', cohort, '--index', str(index), '--arm', arm], stdout=f, stderr=subprocess.STDOUT, timeout=90).returncode
        except subprocess.TimeoutExpired:
            code = 124
    receipt = dict(cohort=cohort, index=index, arm=arm, exit_code=code, wall_s=time.monotonic() - start, log_sha256=digest(log), runner_sha256=digest(Path(__file__)))
    with prefix.with_suffix('.receipt.json').open('x') as f:
        json.dump(receipt, f, indent=2)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--cohort', choices=['original', 'additional'])
    parser.add_argument('--index', type=int)
    parser.add_argument('--arm', choices=['doppler', 'signed'])
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if args.arm:
        fit(args.cohort, args.index, args.arm, args.verify)
    else:
        assert all((HERE / f'whole-verify-original-{i:02d}-signed.json').exists() for i in (0, 16))
        jobs = [(c, i, a) for c, i in [('original', 0), ('original', 16), ('additional', 1)] for a in ('doppler', 'signed')]
        with ThreadPoolExecutor(max_workers=3) as pool:
            for future in as_completed([pool.submit(child, *job) for job in jobs]):
                print(json.dumps(future.result()), flush=True)
