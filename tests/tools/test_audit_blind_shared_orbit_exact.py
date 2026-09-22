from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

from leo.analysis.research.blind_shared_orbit import BlindOrbitCandidateBatch


def _subject():
    path = Path(__file__).parents[2] / "tools/research/audit_blind_shared_orbit_exact.py"
    spec = importlib.util.spec_from_file_location("audit_blind_shared_orbit_exact", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exact_audit_separates_constant_offset_from_shape_error():
    subject = _subject()
    count = 8
    nominal = np.asarray([np.linspace(-10.0, 10.0, count)])
    slope = np.asarray([np.linspace(1.0, 2.0, count)])
    batch = BlindOrbitCandidateBatch(
        norad=np.asarray([123]),
        nominal_hz=nominal,
        phase_minus1_hz=nominal - slope,
        phase_plus1_hz=nominal + slope,
        phase_minus2_hz=nominal - 2 * slope,
        phase_plus2_hz=nominal + 2 * slope,
        age_h=np.ones((1, count)) * 10.0,
    )
    training = np.asarray([True] * 5 + [False] * 3)
    track = {
        "episode_id": "episode",
        "observed_hz": nominal[0] + 7.0,
        "training": training,
        "segment": np.zeros(count, dtype=int),
        "catalogue_size": 100,
    }

    class Exact:
        def predict_hz(self, episode_id, norad, phase):
            assert (episode_id, norad) == ("episode", 123)
            return nominal[0] + slope[0] * phase + 2.0

    diagnostic = {
        "candidate_norad": [123],
        "candidate_posterior": [0.8],
        "unassigned_posterior": 0.2,
        "heldout_log_predictive": -1.0,
    }
    config = {"signal_sigma_hz": 250.0, "unassigned_sigma_hz": 30_000.0, "signal_prior": 0.5}
    result = subject.audit_episode(
        track, batch, Exact(), diagnostic, {"123": 0.1}, config
    )

    assert np.isclose(result["raw_maximum_error_hz"], 2.0)
    assert result["offset_centered_maximum_error_hz"] < 1e-12
    assert result["worst_norad"] == 123
    assert result["worst_candidate_phase_s_range"] == [1.0, 1.0]
