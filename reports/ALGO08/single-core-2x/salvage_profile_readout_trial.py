"""Measure stock phase scores with residual readout deferred to the chosen row."""

import argparse
import json
from pathlib import Path
from statistics import median
from time import process_time

import numpy as np

from leo.analysis.research.retained_track_likelihood import BIAS, PERIOD, profile


def score_rows(observed, predicted, inverse):
    """Use the deployed profile's arithmetic to score every candidate and phase."""
    y, f, w = np.asarray(observed), np.atleast_2d(predicted), np.asarray(inverse)
    if y.ndim != 1 or f.shape[1] != len(y) or w.shape != (len(y), len(y)):
        raise ValueError("matching observations, predictions and whitening matrix required")
    raw = y - f
    alias = np.rint(-raw.mean(axis=1) / PERIOD)
    raw += alias[:, None] * PERIOD
    if np.count_nonzero(w) == len(y):
        diagonal = np.diag(w)
        z, one = raw * diagonal, diagonal
    else:
        z = raw @ w.T
        one = w @ np.ones(len(y))
    information = one @ one
    bias = z @ one / (information + 1 / BIAS**2)
    innovations = z - bias[:, None] * one
    cost = np.sum(innovations**2, axis=1) + (bias / BIAS) ** 2
    cost += 0.0 + np.log1p(BIAS**2 * information)
    return dict(cost=cost, alias=alias, bias=bias, raw=raw)


def winning_readout(fields, winner):
    """Keep the original row reduction layout, including on strided inputs."""
    raw, bias = fields["raw"], fields["bias"]
    if raw.flags.c_contiguous:
        residual = raw[winner] - bias[winner]
        rms = np.sqrt(np.mean(residual[None, :] ** 2, axis=1))[0]
    else:
        residuals = raw - bias[:, None]
        residual = residuals[winner]
        rms = np.sqrt(np.mean(residuals**2, axis=1))[winner]
    return dict(alias=fields["alias"][winner], bias=bias[winner], rms=rms, residual=residual)


def compare(observed, predicted, inverse, penalty=None, visible=None):
    stock = profile(observed, predicted, inverse)
    staged = score_rows(observed, predicted, inverse)
    np.testing.assert_array_equal(stock["cost"].view(np.uint64), staged["cost"].view(np.uint64))
    if penalty is not None:
        index = winner(stock["cost"], penalty, visible)
        for key, value in winning_readout(staged, index).items():
            original = stock[key][index]
            if value.tobytes() != original.tobytes():
                raise ValueError(f"The selected phase has different {key}")


def winner(cost, penalty, visible):
    penalized = cost + penalty
    penalized[~visible] = np.inf
    return int(np.argmin(penalized))


def measure(operation, repeats):
    started = process_time()
    for _ in range(repeats):
        operation()
    return process_time() - started


def measure_pair(observed, predicted, inverse, penalty, visible, repeats):
    def full():
        result = profile(observed, predicted, inverse)
        if penalty is not None:
            i = winner(result["cost"], penalty, visible)
            return {key: result[key][i] for key in ("alias", "bias", "rms", "residual")}
        return result["cost"]

    def selected():
        fields = score_rows(observed, predicted, inverse)
        return (winning_readout(fields, winner(fields["cost"], penalty, visible))
                if penalty is not None else fields["cost"])

    timings = {"stock": [], "staged": []}
    for index in range(4):
        operations = [("stock", full), ("staged", selected)]
        if index % 2:
            operations.reverse()
        for mode, operation in operations:
            timings[mode].append(measure(operation, repeats))
    return timings


def benchmark(output):
    rng = np.random.default_rng(30011)
    rows = []
    # The coarse dimensions reflect the profile's catalogue and one long track.
    for kind, phases, points, order, repeats in (
            ("whole_track", 1666 * 81, 221, "C", 1),
            ("time_window", 1666 * 81, 24, "F", 2),
            ("one_trim", 121, 121, "C", 4096)):
        observed = rng.normal(43000, 1200, points)
        predicted = np.array(rng.normal(42000, 700, (phases, points)), order=order)
        inverse = np.diag(1 / rng.uniform(60, 180, points))
        fine = kind == "one_trim"
        penalty = np.linspace(-15, 15, phases)**2 / 9 if fine else None
        visible = rng.integers(0, 2, phases).astype(bool) if fine else None
        compare(observed, predicted, inverse, penalty, visible)
        timings = measure_pair(observed, predicted, inverse, penalty, visible, repeats)
        rows.append(dict(case=kind, phases=phases, points=points, input_order=order,
                         calls_per_sample=repeats, timings_cpu_s=timings,
                         median_cpu_s={name: median(samples) for name, samples in timings.items()},
                         exact_comparison=True))
    output.write_text(json.dumps(dict(seed=30011, synthetic_shapes=rows), indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    benchmark(parser.parse_args().output)
