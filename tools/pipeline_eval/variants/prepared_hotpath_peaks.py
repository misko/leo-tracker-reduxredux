"""Select the original retained peaks with a row-wise maximum reduction."""

import numpy as np


def retained_peaks(residuals, score_rows, count, epoch_separation, cfo_separation, epoch_count):
    if len(score_rows) != len(residuals):
        raise ValueError("each CFO must have a score row")
    if not len(score_rows) or not epoch_count:
        return ()
    frequencies = np.asarray(residuals)
    scores = np.asarray(score_rows, dtype=float)
    if scores.shape != (len(frequencies), epoch_count):
        raise ValueError("unexpected score grid dimensions")

    if epoch_count == 1:
        eligible = scores > 0
    else:
        padded = np.pad(scores, ((0, 0), (1, 1)), constant_values=-np.inf)
        left, right = padded[:, :-2], padded[:, 2:]
        eligible = (scores >= left) & (scores >= right) & ((scores > left) | (scores > right))
    remaining = np.where(eligible, scores, -np.inf)
    lanes = np.arange(len(frequencies))
    absolute = np.abs(frequencies)
    nearby = np.abs(frequencies[:, None] - frequencies) <= cfo_separation
    offsets = np.arange(1 - epoch_separation, epoch_separation)
    selected = []
    for _ in range(count):
        epochs = remaining.argmax(axis=1)
        scores = remaining[lanes, epochs]
        # The first maximum in a lane is its smallest eligible epoch.
        r = np.lexsort((lanes, epochs, absolute, -scores))[0]
        e, best = epochs[r], scores[r]
        if best == -np.inf:
            break
        selected.append((float(best), int(e), float(frequencies[r])))
        remaining[r, e] = -np.inf
        remaining[np.ix_(nearby[r], (e + offsets) % epoch_count)] = -np.inf
    return tuple(selected)
