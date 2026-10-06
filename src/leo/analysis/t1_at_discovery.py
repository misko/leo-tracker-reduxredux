"""Full-bank absolute timing discovery for T1-AT; no NORAD shortlist or IO."""

import time
from collections.abc import Callable, Sequence

import numpy as np

from leo.contracts.t1_at import T1AtCandidateV1, T1AtModeV1

ALIAS_HZ = 1 / 4.4e-6
Prediction = Callable[[str, np.ndarray, float], tuple[np.ndarray, np.ndarray, np.ndarray]]


def circular(value):
    return (value + ALIAS_HZ / 2) % ALIAS_HZ - ALIAS_HZ / 2


def timing_modes(offsets, groups):
    if not len(offsets):
        return []
    offsets = np.asarray(offsets)
    bins = np.rint(offsets / 0.05).astype(int)
    pairs = np.unique(np.column_stack((bins, groups)), axis=0)
    grid = np.arange(-400, 401)
    counts = np.array([len(np.unique(pairs[abs(pairs[:, 0] - b) <= 2, 1])) for b in grid])
    answer = []
    while counts.max(initial=0) >= 10:
        b = grid[int(np.argmax(counts))]
        answer.append(float(np.median(offsets[abs(bins - b) <= 2])))
        counts[abs(grid - b) <= 4] = 0
    return answer


def discover_modes(
    candidates: Sequence[T1AtCandidateV1],
    numbers: Sequence[int],
    predict: Prediction,
    *,
    maximum_seconds: float = 600,
):
    """Predictor returns calibrated Hz, visibility and dHz/d(absolute orbit time).

    Input candidates are already top-1, in predictor row order. Receiver/RF terms
    must stay evaluated at actual receive time when the orbit time is shifted.
    Both arms receive the union of their timing modes before discrete selection.
    """
    if len({c.window_id for c in candidates}) != len(candidates):
        raise ValueError("discovery requires top-1 windows, not alternate peaks")
    return discover_window_modes(
        np.array([c.refined_cfo_hz for c in candidates]),
        tuple(c.window_id for c in candidates),
        tuple(c.candidate_id for c in candidates),
        numbers,
        predict,
        maximum_seconds=maximum_seconds,
    )


def discover_window_modes(
    measured,
    window_ids,
    candidate_ids,
    numbers,
    predict,
    *,
    maximum_seconds=600,
    arms=("fitted-c", "zero-c"),
):
    """Location-independent numerical port, including unrefined original windows."""
    if not np.isfinite(maximum_seconds) or not 0 < maximum_seconds <= 1800:
        raise ValueError("discovery budget must be in (0, 1800] seconds")
    if not arms or len(set(arms)) != len(arms) or not set(arms) <= {"fitted-c", "zero-c"}:
        raise ValueError("invalid discovery RF arms")
    measured = np.asarray(measured, float)
    if (
        measured.shape != (len(window_ids),)
        or not np.isfinite(measured).all()
        or len(candidate_ids) != len(window_ids)
        or len(set(window_ids)) != len(window_ids)
        or len(set(candidate_ids)) != len(candidate_ids)
    ):
        raise ValueError("discovery requires finite uniquely identified windows")
    if len(set(numbers)) != len(numbers) or any(n <= 0 for n in numbers):
        raise ValueError("catalogue IDs must be positive and unique")
    deadline = time.monotonic() + maximum_seconds
    _, groups = np.unique(window_ids, return_inverse=True)
    results = {a: [] for a in arms}

    def prediction(arm, indices, offset):
        if time.monotonic() >= deadline:
            raise TimeoutError("T1-AT discovery deadline reached; no completed pool")
        p, visible, rate = map(np.asarray, predict(arm, indices, offset))
        shape = (len(window_ids), len(indices))
        if p.shape != shape or visible.shape != shape or rate.shape != shape:
            raise ValueError("prediction port shape differs from observation/candidate bank")
        if visible.dtype != bool or not np.all(np.isfinite(p)) or not np.all(np.isfinite(rate)):
            raise ValueError("prediction port returned invalid evidence")
        return circular(measured[:, None] - p), visible, rate

    for begin in range(0, len(numbers), 16):
        indices = np.arange(begin, min(begin + 16, len(numbers)))
        offsets = {int(i): [] for i in indices}
        for arm in arms:
            votes = [[] for _ in indices]
            voters = [[] for _ in indices]
            for coarse in np.arange(-20.0, 20.001, 1.0):
                error, visible, rate = prediction(arm, indices, float(coarse))
                safe = abs(rate) > 1.0
                roots = coarse + np.divide(error, rate, out=np.zeros_like(error), where=safe)
                ok = visible & safe & (abs(error) <= abs(rate) * 0.75 + 600) & (abs(roots) <= 20)
                for j in range(len(indices)):
                    votes[j].extend(roots[ok[:, j], j])
                    voters[j].extend(groups[ok[:, j]])
            for j, index in enumerate(indices):
                for offset in timing_modes(votes[j], voters[j]):
                    for _ in range(3):
                        e, v, r = prediction(arm, np.array([index]), offset)
                        e, v, r = e[:, 0], v[:, 0], r[:, 0]
                        rows = np.flatnonzero(v & (abs(e) <= 600))
                        rows = rows[np.argsort(abs(e[rows]), kind="stable")]
                        _, first = np.unique(groups[rows], return_index=True)
                        rows = rows[first]
                        if len(rows) < 10:
                            break
                        step = (np.sum(r[rows] * e[rows]) / 200**2 - offset) / (
                            np.sum(r[rows] ** 2) / 200**2 + 1.0
                        )
                        offset = float(np.clip(offset + np.clip(step, -0.1, 0.1), -20, 20))
                    offsets[int(index)].append(offset)
        for index in indices:
            for offset in sorted(set(offsets[int(index)])):
                for arm in arms:
                    e, v, _ = prediction(arm, np.array([index]), offset)
                    rows = np.flatnonzero(v[:, 0] & (abs(e[:, 0]) <= 600))
                    results[arm].append(
                        T1AtModeV1(
                            catalog_number=int(numbers[index]),
                            absolute_timing_s=offset,
                            candidate_ids=tuple(candidate_ids[i] for i in rows),
                            residual_hz=tuple(float(e[i, 0]) for i in rows),
                        )
                    )
    return {a: tuple(result) for a, result in results.items()}
