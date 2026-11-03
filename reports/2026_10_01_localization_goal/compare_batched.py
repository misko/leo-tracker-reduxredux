"""Bounded cached-seed equivalence diagnostic; no evaluator GPS is read."""
import time

START = time.monotonic()
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / '2026_10_01_localization_approaches'
sys.path.insert(0, str(PREVIOUS))
from adapter import prepare
from leo.analysis.localization_batched import fit_batched_soft
from leo.analysis.localization_soft import fit_joint_soft


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('unit')
    parser.add_argument('--output', required=True)
    parser.add_argument('--iterations', type=int, default=6)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise FileExistsError(output)
    seed_path = next((PREVIOUS/'benchmark-v1/primary/A1').glob('*/'+args.unit+'.json'))
    receipt = json.loads(seed_path.read_text())
    expected = json.loads(seed_path.with_suffix('.seal.json').read_text())['prediction_sha256']
    assert 'sha256:'+hashlib.sha256(seed_path.read_bytes()).hexdigest() == expected
    seed = receipt['proposal']['seeds'][0]
    results = []
    for name, solver in [('original', fit_joint_soft), ('batched', fit_batched_soft)]:
        scan, height, ports = prepare(args.unit)
        x = np.zeros(5+len(scan.bank.norad_ids))
        x[:2] = seed['east_km'], seed['north_km']
        precision = np.r_[0., 0., 1., np.full(x.size-3, 4.)]
        started = time.monotonic()
        fit = solver(x, ports, precision, lambda s: np.linalg.norm(s[:2]) <= 250.,
                     max_iterations=args.iterations, deadline=START+85.)
        results.append(dict(method=name, fit_seconds=time.monotonic()-started,
                            mean=fit.mean.tolist(), objectives=list(fit.objectives),
                            reason=fit.reason, iterations=fit.iterations))
    sources = {}
    root = HERE.parents[1]
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename:
            path = Path(filename).resolve()
            if path.suffix == '.py' and path.is_relative_to(root):
                sources[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    result = dict(qualification='cached-seed diagnostic, not independent end-to-end benchmark',
                  unit=args.unit, seed=seed, seed_receipt=str(seed_path), seed_sha256=expected,
                  inputs=scan.inputs, source_sha256=sources, results=results,
                  max_state_difference=float(np.max(np.abs(np.array(results[0]['mean'])-results[1]['mean']))),
                  seconds=time.monotonic()-START)
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in result.items() if k in ('unit', 'max_state_difference', 'seconds')}))


if __name__ == '__main__':
    main()
