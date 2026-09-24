from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np


def module():
    path = Path(__file__).parent / "iteration7_residual_likelihood.py"
    spec = importlib.util.spec_from_file_location("i7test", path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def test_sequences_whiten_time_order_and_account_every_observation():
    m = module()
    data = SimpleNamespace(
        track=np.asarray(["a", "a", "b"], object),
        time_s=np.asarray([2.0, 1.0, 0.0]),
        weights={"a": 2.0, "b": 3.0},
    )
    seqs, accounting = m.sequences(data, np.asarray([8.0, 4.0, 2.0]))
    a = next(row for row in seqs if row["track"] == "a")
    assert np.allclose(a["raw"], [4.0, 8.0])
    assert (
        accounting["track_sequence_count"] == 2
        and accounting["observation_count"] == 3
        and accounting["conditional_innovation_count"] == 3
    )
    assert a["white_one"][0] == 1 and a["white_one"][1] > 0


def test_gaussian_and_robust_profiles_have_bounded_scales():
    m = module()
    seqs = [
        {
            "track": "a",
            "weight_s": 1.0,
            "raw": np.asarray([0.0, 10.0, -10.0]),
            "white_raw": np.asarray([0.0, 10.0, -10.0]),
            "white_one": np.ones(3),
            "observations": 3,
            "transitions": 2,
            "mean_alpha": 0.65,
        }
    ]
    g = m.gaussian_profile(seqs)
    r = m.robust_profile(seqs)
    assert m.SCALE_LO_HZ <= g["scale_hz"] <= m.SCALE_HI_HZ
    assert m.SCALE_LO_HZ <= r["scale_hz"] <= m.SCALE_HI_HZ and r["converged"]
