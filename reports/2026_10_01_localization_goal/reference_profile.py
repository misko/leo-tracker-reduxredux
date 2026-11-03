"""REFERENCE-INFORMED model diagnostic, excluded from localization benchmarks.

Profile nuisance coordinates at the operator reference from three starts.
Neither hyperparameters nor a localization result are selected by this script.
An unresolved conditional fit cannot establish the best reference objective.
"""
# ruff: noqa: E402, I001
import time

START = time.monotonic()
import argparse
import hashlib
import importlib.util
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
    helper = HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    expected = 'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5'
    if digest(helper) != expected:
        raise ValueError('reference authority changed')
    spec = importlib.util.spec_from_file_location('reference_authority', helper)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    lat0, lon0 = np.radians(reference.CENTER)
    lat, lon = np.radians(reference.REFERENCE)
    east = np.cos(lat)*np.sin(lon-lon0)
    north = np.cos(lat0)*np.sin(lat)-np.sin(lat0)*np.cos(lat)*np.cos(lon-lon0)
    dot = np.sin(lat0)*np.sin(lat)+np.cos(lat0)*np.cos(lat)*np.cos(lon-lon0)
    length = np.hypot(east, north)
    position = reference.EARTH_RADIUS_KM*np.arctan2(length, dot)*np.array([east, north])/length
    if reference.distance_m(reference.latlon_from_enu(*position), reference.REFERENCE) > .001:
        raise ValueError('reference coordinate conversion mismatch')
    original = np.asarray(receipt['best']['mean'])
    starts = [original.copy(), np.zeros_like(original), np.zeros_like(original)]
    starts[-1][2] = 2.
    precision = np.r_[0., 0., 1., np.full(original.size-3, 4.)]
    cases = []
    for i, state in enumerate(starts):
        state[:2] = position
        started = time.monotonic()
        fit = fit_batched_soft(state, ports, precision,
                               lambda x: np.linalg.norm(x[:2]) <= 250., fixed_position=True,
                               max_iterations=64, deadline=min(START+85., started+27.))
        cases.append(dict(start_index=i, reason=fit.reason, converged=fit.converged,
                          iterations=fit.iterations, objectives=list(fit.objectives),
                          mean=fit.mean.tolist(), seconds=time.monotonic()-started))
    result = dict(unit_id=receipt['unit_id'], reference_informed=True,
                  qualification='conditional diagnostic; never a localization benchmark result',
                  parent_sha256=digest(path), reference_source_sha256=expected,
                  original_unconstrained_objective=receipt['best']['objectives'][-1],
                  cases=cases, total_seconds=time.monotonic()-START, source_sha256={})
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
    print(json.dumps(dict(original=result['original_unconstrained_objective'],
                         cases=[dict(reason=c['reason'], objective=c['objectives'][-1],
                                     seconds=c['seconds']) for c in cases])))


if __name__ == '__main__':
    main()
