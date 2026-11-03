"""Transfer independent scan nuisance states into shared-position window starts."""
from collections.abc import Sequence
import numpy as np


def constituent_window_starts(
    local_states: Sequence[np.ndarray],
    columns: Sequence[np.ndarray],
    positions: np.ndarray,
    dimension: int,
) -> np.ndarray:
    """Preserve each scan's nuisance coordinates and replace only shared position.

    Callers must bind each local state to its original scan and column map.
    This helper accepts only independent nuisance layouts, with columns 0/1
    reserved for the common east/north coordinates. It does not transfer labels.
    """
    if dimension < 2 or len(local_states) != len(columns) or not local_states:
        raise ValueError('nonempty aligned scan states and column maps required')
    positions = np.asarray(positions, dtype=float)
    if positions.ndim != 2 or positions.shape[1] != 2 or len(positions) == 0 or not np.all(np.isfinite(positions)):
        raise ValueError('finite two-dimensional starting positions required')
    template = np.zeros(dimension)
    seen = {0, 1}
    for raw_state, raw_columns in zip(local_states, columns, strict=True):
        state = np.asarray(raw_state, dtype=float)
        mapping = np.asarray(raw_columns)
        if state.ndim != 1 or not np.all(np.isfinite(state)):
            raise ValueError('local states must be finite vectors')
        if mapping.ndim != 1 or mapping.dtype.kind not in 'iu' or len(mapping) != len(state):
            raise ValueError('integer column map must match local state')
        if len(mapping) < 2 or not np.array_equal(mapping[:2], [0, 1]):
            raise ValueError('position must occupy columns0/1')
        if np.any(mapping < 0) or np.any(mapping >= dimension) or len(set(mapping.tolist())) != len(mapping):
            raise ValueError('invalid or duplicate columns')
        nuisance = set(mapping[2:].tolist())
        if seen.intersection(nuisance):
            raise ValueError('scan nuisance columns must be independent')
        seen.update(nuisance)
        template[mapping[2:]] = state[2:]
    if seen != set(range(dimension)):
        raise ValueError('column maps must cover the complete window state')
    starts = np.repeat(template[None, :], len(positions), axis=0)
    starts[:, :2] = positions
    return starts
