"""Exact point-cache acquisition pilot using the frozen search and likelihood."""
# Imports follow path binding to the existing research adapter deliberately.
# ruff: noqa: E402, I001
import time
from dataclasses import asdict
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / '2026_10_01_localization_approaches'
sys.path.insert(0, str(PREVIOUS))
from adapter import prepare
from acquire import AcquisitionResult, FixedHeightTrackLikelihood, Seed, coarse_to_fine
from leo.analysis.localization_search import MemoizedPointScorer


def propose_memoized(scan, height, *, deadline_s=50.):
    started = time.monotonic()
    ports = [FixedHeightTrackLikelihood(track, scan.bank, scan.config, height, 4.)
             for _, track in scan.tracks]

    def score(points):
        total = np.zeros(len(points))
        for start in range(0, len(points), 32):
            if time.monotonic()-started >= deadline_s:
                raise TimeoutError('memoized acquisition reached wall budget')
            chunk = points[start:start+32]
            for port in ports:
                values = port(chunk, np.empty((1, 0)))[:, 0, :]
                maximum = np.max(values, axis=1)
                total[start:start+len(chunk)] += maximum+np.log(
                    np.exp(values-maximum[:, None]).sum(axis=1))
        return total

    cached = MemoizedPointScorer(score)
    seeds, scores, requested, spacing = coarse_to_fine(cached)
    result = AcquisitionResult(
        tuple(Seed(float(p[0]), float(p[1]), float(s)) for p, s in zip(seeds, scores, strict=True)),
        requested, len(ports), spacing, time.monotonic()-started,
    )
    return result, dict(requested_points=cached.requested_points,
                        evaluated_unique_points=cached.evaluated_points)


if __name__ == '__main__':
    import argparse
    import hashlib
    import json

    start = time.monotonic()
    parser = argparse.ArgumentParser()
    parser.add_argument('unit')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise FileExistsError(output)
    scan, height, _ = prepare(args.unit)
    proposal, counts = propose_memoized(scan, height)
    reference_path = next((PREVIOUS/'benchmark-v1/primary/A1').glob('*/'+args.unit+'.json'))
    expected = json.loads(reference_path.with_suffix('.seal.json').read_text())['prediction_sha256']
    assert 'sha256:'+hashlib.sha256(reference_path.read_bytes()).hexdigest() == expected
    reference = json.loads(reference_path.read_text())['proposal']
    def coordinates(rows):
        return np.array([[r['east_km'], r['north_km']] for r in rows])
    actual = asdict(proposal)
    result = dict(unit=args.unit, proposal=actual, counts=counts, inputs=scan.inputs,
                  qualification='acquisition-only equivalence pilot, no position reference used',
                  baseline_receipt=str(reference_path), baseline_receipt_sha256=expected,
                  seeds_bit_identical=bool(np.array_equal(coordinates(actual['seeds']),
                                                         coordinates(reference['seeds']))),
                  max_score_difference=float(max(abs(a['cumulative_log_score']-
                                                     b['cumulative_log_score'])
                                                 for a, b in zip(
                                                     actual['seeds'], reference['seeds'],
                                                     strict=True))),
                  wall_seconds=time.monotonic()-start)
    result['source_sha256'] = {}
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename:
            path = Path(filename).resolve()
            if path.suffix == '.py' and path.is_relative_to(HERE.parents[1]):
                result['source_sha256'][str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    fields = ('counts', 'seeds_bit_identical', 'max_score_difference', 'wall_seconds')
    print(json.dumps({k: v for k, v in result.items() if k in fields}))
