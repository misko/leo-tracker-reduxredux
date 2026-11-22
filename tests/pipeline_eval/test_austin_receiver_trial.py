from importlib import import_module
from pathlib import Path

import pytest


def test_phase_score_uses_strongest_verified_factor_and_counts_empty_windows(monkeypatch):
    path = Path(__file__).resolve().parents[2]/"reports/ALGO08/single-core-2x"
    monkeypatch.syspath_prepend(str(path))
    trial = import_module("austin_receiver_trial")
    weak = (0, 500, 0., 123., .25, .22)
    strong = (1, 50, .25, -800., .6, .1)
    result = trial.score([weak, strong], 50. + trial.wave.RATE/trial.wave.FRAME_HZ)
    assert result["winning_rank"] == 1 and result["phase_error_samples"] == pytest.approx(.25)
    assert result["signed_cfo_hz"] == -800. and result["within_tolerance"]
    assert not trial.score([], 50.)["within_tolerance"]
    assert trial.score([strong], None)["phase_error_samples"] is None
