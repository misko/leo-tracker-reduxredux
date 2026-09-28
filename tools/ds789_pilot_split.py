"""Training-symbol CFO fits with untouched-symbol and injected-shift diagnostics."""

from dataclasses import asdict

import numpy as np

from leo.analysis.research.frame_cfo import (
    ordinary_profile_cfo,
    profiled_coherence,
    robust_profile_cfo,
)


def evaluate_frame(matched, times, *, seed):
    """Input contains even-Qin rows only; alternate rows define the split."""
    matched = np.asarray(matched)
    times = np.asarray(times)
    if matched.shape != (150, 8) or times.shape != (150,):
        raise ValueError("expected 150 even-Qin rows and eight tones")
    training, held = matched[::2], matched[1::2]
    train_times, held_times = times[::2], times[1::2]
    rng = np.random.default_rng(seed)
    scrambled = held * (1j ** rng.integers(0, 4, len(held)))[:, None]
    rows = []
    for name, fit in (("ordinary", ordinary_profile_cfo), ("robust", robust_profile_cfo)):
        kwargs = dict(maximum_residual_cfo_hz=2000.0, coarse_step_hz=100.0, fine_step_hz=5.0)
        if name == "robust":
            kwargs["maximum_iterations"] = 4
        result = fit(training, train_times, **kwargs)
        shifts = []
        for shift in (-250.0, 250.0):
            injected = training * np.exp(2j * np.pi * shift * train_times[:, None])
            estimate = fit(injected, train_times, **kwargs)
            shifts.append(
                {
                    "injected_hz": shift,
                    "estimated_hz": estimate.frequency_hz,
                    "shift_error_hz": estimate.frequency_hz - result.frequency_hz - shift,
                    "boundary": estimate.search_boundary,
                    "expected_within_bounds": abs(result.frequency_hz + shift) < 2000.0,
                }
            )
        rows.append(
            {
                "method": name,
                "fit": asdict(result),
                "held_coherence": profiled_coherence(held, held_times, result.frequency_hz),
                "scrambled_coherence": profiled_coherence(
                    scrambled, held_times, result.frequency_hz
                ),
                "injections": shifts,
            }
        )
    return {
        "baseline_held_coherence": profiled_coherence(held, held_times, 0.0),
        "baseline_scrambled_coherence": profiled_coherence(scrambled, held_times, 0.0),
        "methods": rows,
    }
