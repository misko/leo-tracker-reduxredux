"""Order-independent source-specific receiver detection evidence."""
import numpy as np


def source_bits(source, owners, candidate_views, windows):
    bits = np.zeros((windows, 2), dtype=int)
    for candidate, possible_sources in owners.items():
        if source not in possible_sources:
            continue
        window, receiver = candidate_views[candidate]
        if len(possible_sources) == 1:
            bits[window, receiver] = 1
        elif bits[window, receiver] != 1:
            bits[window, receiver] = -1
    return bits
