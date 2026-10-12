"""Nested random-block evidence for continuous versus separate CFO curves.

Degree selection, unwrapping and integer alias alignment use training rows only.
This is trajectory prediction evidence, not satellite or position validation.
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PredictiveCurveConfiguration:
    block_s: float = 2.0
    outer_folds: int = 5
    repeats: int = 2
    inner_folds: int = 3
    seed: int = 20261013
    degrees: tuple[int, ...] = (2, 3, 4)

    def __post_init__(self):
        if not np.isfinite(self.block_s) or self.block_s <= 0:
            raise ValueError("invalid predictive block duration")
        if min(self.outer_folds, self.inner_folds) < 2 or self.repeats < 1:
            raise ValueError("invalid predictive fold configuration")
        if self.degrees != (2, 3, 4):
            raise ValueError("invalid predictive degrees")


def _circular(values, spacing):
    return (values + spacing / 2) % spacing - spacing / 2


def _matrix(times, center, degree):
    return np.polynomial.polynomial.polyvander((times - center) / 20, degree)


def _fit(times, values, weights, center, degree):
    matrix = _matrix(times, center, degree)
    coefficients, _, rank, _ = np.linalg.lstsq(
        matrix * np.sqrt(weights)[:, None], values * np.sqrt(weights), rcond=None
    )
    if rank != degree + 1:
        raise ValueError("rank-deficient predictive curve")
    return coefficients


def _assignment(blocks, folds, seed):
    unique = np.unique(blocks)
    if len(unique) < folds:
        raise ValueError("insufficient predictive blocks")
    shuffled = np.random.default_rng(seed).permutation(unique)
    mapping = {int(block): i % folds for i, block in enumerate(shuffled)}
    return np.array([mapping[int(block)] for block in blocks])


def _train(times, raw, weights, parents, mask, spacing, degree, separate):
    """Return a predictor derived only from the selected training rows."""
    center = float(np.average(times[mask], weights=weights[mask]))
    training = np.full(len(times), np.nan)
    groups = np.unique(parents)
    previous = None
    for group in groups:
        rows = np.flatnonzero(mask & (parents == group))
        if len(rows) < degree + 2:
            raise ValueError("insufficient predictive parent training rows")
        values = np.unwrap(raw[rows] * 2 * np.pi / spacing) * spacing / (2 * np.pi)
        if not separate and previous is not None:
            earlier, earlier_values = previous
            boundary = (times[earlier[-1]] + times[rows[0]]) / 2
            left = earlier[-12:]
            right = rows[:12]
            a = _fit(times[left], earlier_values[-len(left) :], weights[left], boundary, 2)[0]
            b = _fit(times[right], values[: len(right)], weights[right], boundary, 2)[0]
            values += round((a - b) / spacing) * spacing
        training[rows] = values
        previous = rows, values
    if separate:
        coefficients = {
            int(group): _fit(
                times[mask & (parents == group)],
                training[mask & (parents == group)],
                weights[mask & (parents == group)],
                center,
                degree,
            )
            for group in groups
        }
        prediction = np.empty(len(times))
        for group in groups:
            rows = parents == group
            prediction[rows] = _matrix(times[rows], center, degree) @ coefficients[int(group)]
    else:
        coefficients = _fit(times[mask], training[mask], weights[mask], center, degree)
        prediction = _matrix(times, center, degree) @ coefficients
    return prediction


def compare_predictive_curves(series, config=None):
    """Compare outer held-out errors with inner training-only degree selection.

    The original series inventory and component membership are conditioned upon.
    All records sharing a time block remain in the same fold. Shared source probes
    are deduplicated by fixed GLRT weight, before splitting, in both curve arms.
    """
    config = config or PredictiveCurveConfiguration()
    ordered = sorted(series, key=lambda s: (s.times_s[0], s.member_ids))
    if len(ordered) < 2:
        raise ValueError("predictive comparison needs multiple parent series")
    spacing = ordered[0].alias_spacing_hz
    if any(s.lane_key != ordered[0].lane_key or s.alias_spacing_hz != spacing for s in ordered):
        raise ValueError("predictive comparison requires one receiver/RF lane")
    records = {}
    for parent, item in enumerate(ordered):
        for i, source in enumerate(item.source_ids):
            row = (item.times_s[i], item.values_hz[i], item.weights[i], item.point_ids[i], parent)
            old = records.get(source)
            if old is None or (-row[2], row[3]) < (-old[2], old[3]):
                records[source] = row
    sources = sorted(records, key=lambda s: (records[s][0], s))
    times, raw, weights = [np.array([records[s][i] for s in sources]) for i in range(3)]
    parents = np.array([records[s][4] for s in sources])
    blocks = np.floor(times / config.block_s).astype(int)
    folds = []
    repeat_errors = {"joined": [], "separate": []}
    for repeat in range(config.repeats):
        assignment = _assignment(blocks, config.outer_folds, config.seed + repeat)
        errors = {mode: np.empty(len(times)) for mode in repeat_errors}
        for fold in range(config.outer_folds):
            train, test = assignment != fold, assignment == fold
            inner = _assignment(blocks[train], config.inner_folds, config.seed + 1000 + repeat)
            receipt = {
                "repeat": repeat,
                "fold": fold,
                "test_blocks": np.unique(blocks[test]).tolist(),
                "models": {},
            }
            for mode in repeat_errors:
                separate = mode == "separate"
                candidates = []
                for degree in config.degrees:
                    inner_residual = np.empty(sum(train))
                    try:
                        for inner_fold in range(config.inner_folds):
                            inner_train = train.copy()
                            inner_train[train] = inner != inner_fold
                            inner_test = train.copy()
                            inner_test[train] = inner == inner_fold
                            prediction = _train(
                                times, raw, weights, parents, inner_train, spacing, degree, separate
                            )
                            inner_residual[inner == inner_fold] = _circular(
                                raw[inner_test] - prediction[inner_test], spacing
                            )
                        rms = float(np.sqrt(np.average(inner_residual**2, weights=weights[train])))
                        candidates.append((rms, degree))
                    except ValueError:
                        continue
                if not candidates:
                    raise ValueError("no trainable predictive degree in an outer fold")
                best = min(c[0] for c in candidates)
                degree = min(d for rms, d in candidates if rms <= 1.1 * best + 5)
                prediction = _train(times, raw, weights, parents, train, spacing, degree, separate)
                residual = _circular(raw[test] - prediction[test], spacing)
                errors[mode][test] = residual
                receipt["models"][mode] = {
                    "degree": degree,
                    "inner_scores": candidates,
                    "test_rows": np.flatnonzero(test).tolist(),
                    "predictions_hz": prediction[test].tolist(),
                    "held_rms_hz": float(np.sqrt(np.average(residual**2, weights=weights[test]))),
                }
            folds.append(receipt)
        for mode in repeat_errors:
            repeat_errors[mode].append(
                float(np.sqrt(np.average(errors[mode] ** 2, weights=weights)))
            )
    rms = {mode: float(np.median(values)) for mode, values in repeat_errors.items()}
    return {
        "rows": len(times),
        "source_ids": sources,
        "parent_ids": [s.member_ids for s in ordered],
        "block_ids": blocks.tolist(),
        "seed": config.seed,
        "folds": folds,
        "repeat_rms_hz": repeat_errors,
        "rms_hz": rms,
        "joined_gain_hz": rms["separate"] - rms["joined"],
        "scope": "Nested conditional curve prediction only; not satellite or position accuracy.",
    }
