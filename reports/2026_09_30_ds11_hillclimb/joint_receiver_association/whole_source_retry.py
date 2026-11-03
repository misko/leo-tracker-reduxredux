"""One equivalent-engine continuation of the preserved scan-0 timeout."""
import json
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
from scipy.optimize import minimize
from whole_source_run import load_model
from whole_source_speed_check import accelerate
from position_run import audit
from doppler_pilot import digest, read

HERE = Path(__file__).resolve().parent


def fit():
    start = time.monotonic()
    proof = read(HERE / 'whole-source-speed-check.json')
    assert proof['parity_passed']
    for p, h in proof['sources'].items():
        assert digest(p) == h, p
    assert read(HERE / 'whole-original-00-signed.receipt.json')['exit_code'] == 124
    old, _, initial, sources = load_model('original', 0, 'signed')
    model = accelerate(old, 'original', 0)
    def objective(x):
        out = model.evaluate(x)
        return -out['score'], -out['gradient']
    result = minimize(objective, initial, method='L-BFGS-B', jac=True, bounds=[(-12., 12.), (-12., 12.), (-5., 5.)], options=dict(maxiter=100, ftol=1e-12, gtol=1e-5))
    final = model.evaluate(result.x)
    checked = audit(model, result.x, final['gradient'])
    qualified = bool(result.success and np.min(np.array([12., 12., 5.]) - np.abs(result.x)) >= .001 and np.max(np.abs(final['gradient'])) <= .01 and checked['discrepancy'] <= .02)
    joint = model.evaluate(result.x, gradient=False, held=True)
    for p in (Path(__file__), HERE / 'whole-source-speed-check.json', HERE / 'WHOLE_SOURCE_RUNTIME.md', HERE / 'source_partition_fast.py', HERE / 'whole_source_fast.py', HERE / 'whole-original-00-signed.receipt.json'):
        sources[str(p)] = digest(p)
    output = dict(cohort='original', index=0, arm='signed', engineering_continuation=True, x=result.x.tolist(), coordinates_deg=model.geometry.coordinates(result.x), score=final['score'], held_score=joint['score'] - final['score'], qualified=qualified, derivative_audit=checked, optimizer=dict(success=bool(result.success), message=str(result.message), iterations=int(result.nit), evaluations=int(result.nfev)), expected_sources=final['expected_sources'], lane_diagnostics=final['lanes'], sources=sources, elapsed_s=time.monotonic() - start)
    with (HERE / 'whole-original-00-signed.retry.json').open('x') as f:
        json.dump(output, f, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in output.items() if k not in ('sources', 'lane_diagnostics')}), flush=True)


if __name__ == '__main__':
    if '--child' in sys.argv:
        fit()
    else:
        start = time.monotonic()
        log = HERE / 'whole-original-00-signed.retry.log'
        with log.open('x') as stream:
            try:
                code = subprocess.run([sys.executable, str(Path(__file__)), '--child'], stdout=stream, stderr=subprocess.STDOUT, timeout=90).returncode
            except subprocess.TimeoutExpired:
                code = 124
        receipt = dict(exit_code=code, wall_s=time.monotonic() - start, log_sha256=digest(log), runner_sha256=digest(Path(__file__)))
        with (HERE / 'whole-original-00-signed.retry.receipt.json').open('x') as f:
            json.dump(receipt, f, indent=2)
        print(json.dumps(receipt), flush=True)
