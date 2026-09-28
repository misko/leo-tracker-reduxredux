from __future__ import annotations

from time import process_time_ns

import numpy as np
from test_peak_selection import _reference, candidate


def _time(call, repetitions: int = 25) -> float:
    started = process_time_ns()
    for _ in range(repetitions):
        call()
    return (process_time_ns() - started) / repetitions / 1e6


def main() -> None:
    rng = np.random.default_rng(20260927)
    residuals = tuple(float(value) for value in range(-400_000, 400_001, 80_000))
    rows = tuple(rng.random(3333) for _ in residuals)
    arguments = (residuals, rows, 8, 20, 80_000.0, 3333)
    expected = _reference(*arguments)
    actual = candidate._retain_score_map_peaks(*arguments)
    if actual != expected:
        raise RuntimeError("candidate differs from stable full sort")
    baseline_ms = _time(lambda: _reference(*arguments))
    candidate_ms = _time(lambda: candidate._retain_score_map_peaks(*arguments))
    print(
        {
            "baseline_cpu_ms": baseline_ms,
            "candidate_cpu_ms": candidate_ms,
            "speedup": baseline_ms / candidate_ms,
            "retained": len(actual),
        }
    )


if __name__ == "__main__":
    main()
