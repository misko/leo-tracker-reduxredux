"""Exact marginal and entropy probes without changing factor log weights."""
import numpy as np
from source_partition_fast import partition


def probe(n_tracks, factors, candidates, reference):
    if len(factors) != len(candidates) or len(reference) != n_tracks:
        raise ValueError('factor/candidate/reference mismatch')
    width = factors[0][2].shape[1] if factors else 0
    augmented = []
    for candidate, (support, values, derivatives) in zip(candidates, factors, strict=True):
        extra = np.zeros((len(values), n_tracks + 1))
        subsets = np.arange(len(values))
        for local, track in enumerate(support):
            if candidate == reference[track]:
                extra[:, track] = (subsets >> local) & 1
        extra[:, -1] = np.where(np.isfinite(values), values, 0.)
        augmented.append((support, values, np.column_stack((derivatives, extra))))
    score, gradient = partition(n_tracks, augmented)
    probability = gradient[width:width + n_tracks]
    entropy = score - gradient[-1]
    assert np.all(probability >= -1e-8) and np.all(probability <= 1 + 1e-8)
    assert entropy >= -1e-7
    return score, gradient[:width], dict(reference_probability=probability, entropy=float(max(0., entropy)))
