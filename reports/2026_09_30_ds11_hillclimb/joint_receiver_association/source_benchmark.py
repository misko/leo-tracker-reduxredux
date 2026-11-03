"""Real candidate-support benchmark; synthetic finite weights prevent pruning."""
import json
from pathlib import Path
import time
import numpy as np
from scipy.special import logsumexp
from source_partition import partition
from doppler_pilot import read, digest

HERE = Path(__file__).resolve().parent


def main():
    doc = read(HERE / 'input-16.json')
    lane = max(doc['lanes'], key=lambda l: len(l['left']) + len(l['right']))
    tids = lane['left'] + lane['right']
    meta = {t['track_id']: t for t in doc['tracks']}
    rng = np.random.default_rng(20261001)
    weights, gradients = {}, {}
    for i, tid in enumerate(tids):
        for candidate in meta[tid]['candidate_norad']:
            weights[i, candidate] = float(rng.normal(-10., 2.))
            gradients[i, candidate] = rng.normal(size=3)
    factors = []
    for candidate in sorted({c for i, c in weights}):
        support = [i for i in range(len(tids)) if (i, candidate) in weights]
        bits = ((np.arange(1 << len(support))[:, None] >> np.arange(len(support))) & 1)
        factors.append((support, bits @ np.array([weights[i, candidate] for i in support]), bits @ np.array([gradients[i, candidate] for i in support])))
    start = time.monotonic()
    actual, derivative = partition(len(tids), factors)
    elapsed = time.monotonic() - start
    expected, gradient = 0., np.zeros(3)
    for i, tid in enumerate(tids):
        values = np.array([weights[i, c] for c in meta[tid]['candidate_norad']])
        normal = logsumexp(values)
        expected += normal
        gradient += np.exp(values - normal) @ np.array([gradients[i, c] for c in meta[tid]['candidate_norad']])
    assert abs(actual - expected) < 1e-8
    assert np.max(np.abs(gradient - derivative)) < 1e-8
    output = dict(tracks=len(tids), sources=len(factors), nonempty_source_subsets=sum(len(f[1]) - 1 for f in factors), elapsed_s=elapsed, score_discrepancy=actual - expected, derivative_discrepancy=float(np.max(np.abs(gradient - derivative))), sources_sha256={str(p): digest(p) for p in (Path(__file__), HERE / 'source_partition.py', HERE / 'test_source_partition.py', HERE / 'input-16.json')})
    with (HERE / 'source-benchmark.json').open('x') as f:
        json.dump(output, f, indent=2, allow_nan=False)
    print(json.dumps(output, indent=2), flush=True)


if __name__ == '__main__':
    main()
