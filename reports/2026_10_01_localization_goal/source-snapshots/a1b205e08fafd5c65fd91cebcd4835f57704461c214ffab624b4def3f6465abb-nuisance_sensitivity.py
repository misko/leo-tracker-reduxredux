"""Prespecified quarter/fourfold nuisance-precision refits, without GPS.

Warm starts from a sealed fitted state make this a sensitivity diagnostic,
not an independent scan benchmark. Objectives across priors are incomparable
as model evidence; no variant is selected from this experiment.
"""
# ruff: noqa: E402, I001
import time

START = time.monotonic()
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'2026_10_01_localization_approaches'))
from adapter import prepare
from leo.analysis.localization_batched import fit_batched_soft


def digest(path):
    return 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('receipt')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    path, output = Path(args.receipt), Path(args.output)
    if output.exists():
        raise FileExistsError(output)
    if digest(path) != json.loads(path.with_suffix('.seal.json').read_text())['prediction_sha256']:
        raise ValueError('receipt seal mismatch')
    receipt = json.loads(path.read_text())
    scan, _, ports = prepare(receipt['unit_id'])
    if scan.inputs != receipt['inputs']:
        raise ValueError('input mismatch')
    initial = np.asarray(receipt['best']['mean'])
    cases = []
    for multiplier in (.25, 4.):
        precision = np.r_[0., 0., 1., np.full(initial.size-3, 4.)] * multiplier
        started = time.monotonic()
        fit = fit_batched_soft(initial, ports, precision,
                               lambda s: np.linalg.norm(s[:2]) <= 250.,
                               max_iterations=64, deadline=min(START+85., started+40.))
        cases.append(dict(nuisance_precision_multiplier=multiplier, mean=fit.mean.tolist(),
                          objectives=list(fit.objectives), converged=fit.converged,
                          reason=fit.reason, iterations=fit.iterations,
                          displacement_from_original_m=float(
                              np.linalg.norm(fit.mean[:2]-initial[:2])*1000),
                          seconds=time.monotonic()-started))
    result = dict(unit_id=receipt['unit_id'], parent_sha256=digest(path), inputs=scan.inputs,
                  qualification='warm-start nuisance sensitivity, not benchmark or model selection',
                  no_reference_positions_read=True, cases=cases,
                  total_seconds=time.monotonic()-START, source_sha256={})
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename:
            source = Path(filename).resolve()
            if source.suffix == '.py' and source.is_relative_to(HERE.parents[1]):
                result['source_sha256'][str(source)] = digest(source)
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    with output.with_suffix('.seal.json').open('x') as stream:
        json.dump(dict(prediction_sha256=digest(output)), stream)
    print(json.dumps([{k: v for k, v in c.items() if k not in ('mean', 'objectives')}
                      for c in cases]))


if __name__ == '__main__':
    main()
