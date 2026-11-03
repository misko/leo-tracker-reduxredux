"""Five frozen fits on one separate recording, with durable bounded receipts."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
from scipy.optimize import minimize
from position_run import audit
from joint_position import JointPosition
from doppler_pilot import fast, read, digest

HERE = Path(__file__).resolve().parent
ARMS = ('doppler', 'receiver', 'signed', 'swapped', 'permuted')


def fit(arm):
    start = time.monotonic()
    base = HERE.parent / 'additional'
    plan = read(base / 'plan.json')
    bound = read(HERE / 'additional-input-01.json')
    calibration = read(HERE / 'conditional-fit.json')
    paths = (base / 'plan.json', base / 'runs/01_iid.json', HERE / 'additional-input-01.json', HERE / 'conditional-fit.json', HERE / 'joint_position.py', HERE / 'matching.py', HERE / 'position_run.py', HERE / 'ADDITIONAL_PROTOCOL.md', Path(__file__))
    sources = {str(p): digest(p) for p in paths}
    for obj in (bound, calibration):
        for p, h in obj['sources'].items():
            assert digest(p) == h, p
    initial = np.array(read(base / 'runs/01_iid.json')['selected']['x'])
    doc = fast.load_documents(dict(config=plan['config'], inputs=[plan['inputs'][1]]))[0]
    model = JointPosition(doc, plan['config'], bound, calibration, arm)
    def objective(x):
        out = model.evaluate(x)
        return -out['score'], -out['gradient']
    result = minimize(objective, initial, method='L-BFGS-B', jac=True, bounds=[(-12., 12.), (-12., 12.), (-5., 5.)], options=dict(maxiter=100, ftol=1e-12, gtol=1e-5))
    final = model.evaluate(result.x)
    checked = audit(model, result.x, final['gradient'])
    qualified = bool(result.success and np.min(np.array([12., 12., 5.]) - np.abs(result.x)) >= .001 and np.max(np.abs(final['gradient'])) <= .01 and checked['discrepancy'] <= .02)
    joint = model.evaluate(result.x, gradient=False, held=True)
    output = dict(index=1, arm=arm, x=result.x.tolist(), coordinates_deg=model.geometry.coordinates(result.x), score=final['score'], held_score=joint['score'] - final['score'], qualified=qualified, derivative_audit=checked, optimizer=dict(success=bool(result.success), message=str(result.message), iterations=int(result.nit)), expected_pairs=final['expected_pairs'], sources=sources, elapsed_s=time.monotonic() - start)
    with (HERE / f'additional-01-{arm}.json').open('x') as f:
        json.dump(output, f, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in output.items() if k != 'sources'}), flush=True)


def child(arm):
    start = time.monotonic()
    log = HERE / f'additional-01-{arm}.log'
    with log.open('x') as f:
        try:
            code = subprocess.run([sys.executable, str(Path(__file__)), '--arm', arm], stdout=f, stderr=subprocess.STDOUT, timeout=90).returncode
        except subprocess.TimeoutExpired:
            code = 124
    receipt = dict(arm=arm, exit_code=code, wall_s=time.monotonic() - start, log_sha256=digest(log), runner_sha256=digest(Path(__file__)))
    with (HERE / f'additional-01-{arm}.receipt.json').open('x') as f:
        json.dump(receipt, f, indent=2)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--arm', choices=ARMS)
    args = parser.parse_args()
    if args.arm:
        fit(args.arm)
    else:
        with ThreadPoolExecutor(max_workers=3) as pool:
            for future in as_completed([pool.submit(child, arm) for arm in ARMS]):
                print(json.dumps(future.result()), flush=True)
