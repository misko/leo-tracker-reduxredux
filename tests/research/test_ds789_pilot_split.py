import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from ds789_pilot_split import evaluate_frame  # noqa: E402


def test_frequency_recovery_and_held_isolation():
    times = np.arange(150) * 8.8e-6
    rng = np.random.default_rng(42)
    values = np.exp(2j * np.pi * 731.37 * times[:, None]) * np.ones((1, 8))
    values += 0.05 * (rng.normal(size=values.shape) + 1j * rng.normal(size=values.shape))
    original = evaluate_frame(values, times, seed=17)
    changed = values.copy()
    changed[1::2] = rng.normal(size=(75, 8)) + 1j * rng.normal(size=(75, 8))
    alternate = evaluate_frame(changed, times, seed=17)
    for a, b in zip(original["methods"], alternate["methods"], strict=True):
        assert a["fit"] == b["fit"]
        assert a["injections"] == b["injections"]
        assert a["fit"]["frequency_hz"] == pytest.approx(731.37, abs=2)
        assert a["held_coherence"] > 0.98
        assert a["held_coherence"] > b["held_coherence"] + 0.8
        assert a["held_coherence"] > a["scrambled_coherence"] + 0.8
        for shift in a["injections"]:
            assert abs(shift["shift_error_hz"]) < 0.1


def test_reject_wrong_symbol_contract():
    with pytest.raises(ValueError, match="150 even-Qin"):
        evaluate_frame(np.ones((300, 8)), np.arange(300), seed=1)
