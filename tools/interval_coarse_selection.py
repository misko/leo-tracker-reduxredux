"""Research selection given VALID score-error intervals and an exact epoch oracle.

This module does not establish error bounds for any approximate kernel. Supplying
an empirical tolerance does not certify omitted scores. It is not used in production.
"""

import numpy as np


def peaks(rows):
    if rows.shape[1] == 1:
        return rows > 0
    left = np.full_like(rows, -np.inf)
    right = np.full_like(rows, -np.inf)
    left[:, 1:] = rows[:, :-1]
    right[:, :-1] = rows[:, 1:]
    return (rows >= left) & (rows >= right) & ((rows > left) | (rows > right))


def retain(rows, residuals, count, epoch_separation, cfo_separation, *, valid=None):
    mask = peaks(rows)
    if valid is not None:
        mask &= valid[None, :]
    row_indexes, epochs = np.nonzero(mask)
    frequencies = np.asarray(residuals)[row_indexes]
    ordered = np.lexsort((row_indexes, epochs, np.abs(frequencies), -rows[row_indexes, epochs]))
    retained = []
    for index in ordered:
        row, epoch = row_indexes[index], epochs[index]
        candidate = (float(rows[row, epoch]), int(epoch), float(residuals[row]))
        if any(min(abs(epoch - other[1]), rows.shape[1] - abs(epoch - other[1]))
               < epoch_separation and abs(candidate[2] - other[2]) <= cfo_separation
               for other in retained):
            continue
        retained.append(candidate)
        if len(retained) == count:
            break
    return tuple(retained)


def select(screen, error, residuals, count, epoch_separation, cfo_separation, exact_epochs):
    """Return exact selected peaks conditional on supplied intervals covering truth.

The callback returns exact scores for every frequency at requested epoch columns.
Uncertain peaks include boundary neighbors and equal-score ties. If a sampled
bound is false, fall back to the complete oracle; false bounds at never-sampled
points cannot be detected here and must be excluded by a separate kernel proof.
"""
    screen = np.asarray(screen, dtype=float)
    bounds = np.broadcast_to(np.asarray(error, dtype=float), screen.shape)
    residuals = np.asarray(residuals, dtype=float)
    if (screen.ndim != 2 or min(screen.shape) <= 0 or residuals.shape != (screen.shape[0],)
            or not np.isfinite(screen).all() or not np.isfinite(bounds).all()
            or not np.isfinite(residuals).all() or np.any(bounds < 0)
            or count <= 0 or epoch_separation <= 0 or cfo_separation < 0):
        raise ValueError('Invalid score intervals or selection geometry')
    # Round intervals outwards, including a one-ulp expansion at zero error.
    lower = np.nextafter(screen - bounds, -np.inf)
    upper = np.nextafter(screen + bounds, np.inf)
    left = np.full_like(lower, -np.inf)
    right = np.full_like(lower, -np.inf)
    left[:, 1:] = lower[:, :-1]
    right[:, :-1] = lower[:, 1:]
    possible = (upper >= left) & (upper >= right)
    work = screen.copy()
    known = np.zeros(screen.shape[1], dtype=bool)
    requests = []

    def request(columns):
        columns = np.unique(columns)
        columns = columns[~known[columns]]
        if not len(columns):
            return True
        values = np.asarray(exact_epochs(columns), dtype=float)
        if values.shape != (screen.shape[0], len(columns)) or not np.isfinite(values).all():
            raise ValueError('Invalid exact oracle response')
        work[:, columns] = values
        known[columns] = True
        requests.append(len(columns))
        return bool(np.all(values >= lower[:, columns]) and np.all(values <= upper[:, columns]))

    def neighbors(columns):
        return np.unique(np.clip(np.concatenate([columns - 1, columns, columns + 1]),
                                 0, screen.shape[1] - 1))

    def complete(reason):
        request(np.arange(screen.shape[1]))
        return dict(retained=retain(work, residuals, count, epoch_separation, cfo_separation),
                    exact_columns=int(known.sum()), total_columns=len(known), requests=requests,
                    fallback=reason, certified_only_if_input_bounds_valid=True)

    initial = retain(work, residuals, count, epoch_separation, cfo_separation)
    if not initial:
        return complete('no initial peaks')
    if not request(neighbors(np.asarray([x[1] for x in initial]))):
        return complete('sampled bound violation')
    while True:
        valid = known & np.r_[True, known[:-1]] & np.r_[known[1:], True]
        selected = retain(work, residuals, count, epoch_separation, cfo_separation, valid=valid)
        if len(selected) < count:
            return complete('insufficient verified peaks')
        threshold = selected[-1][0]
        uncertain = possible & (upper >= threshold) & ~valid[None, :]
        columns = np.flatnonzero(np.any(uncertain, axis=0))
        if not len(columns):
            return dict(retained=selected, exact_columns=int(known.sum()),
                        total_columns=len(known), requests=requests, fallback=None,
                        certified_only_if_input_bounds_valid=True)
        if not request(neighbors(columns)):
            return complete('sampled bound violation')
