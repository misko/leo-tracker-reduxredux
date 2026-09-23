"""Verify that target means cannot consume post-cutoff catalogue information."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location(
    "pilot_causality_subject", Path(__file__).with_name("run_pilot.py")
)
PILOT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PILOT)
HOUR = 3_600_000_000_000


def record(text, epoch, collected):
    return {"text": text, "epoch_utc_ns": epoch * HOUR, "first_collected_utc_ns": collected * HOUR}


def fake_study(monkeypatch):
    monkeypatch.setattr(
        PILOT,
        "parse_element_sets",
        lambda text: SimpleNamespace(
            satellites=[SimpleNamespace(bstar=0.0, no_kozai=1.0, ecco=0.01)]
        ),
    )
    return SimpleNamespace(
        tle_key=lambda text: text,
        phase_seconds=lambda old, new, epoch: 0.2 if old == "previous" else 999.0,
        predict_rate=lambda model, recent, features: recent,
    )


def test_post_cutoff_history_cannot_change_point_mean(monkeypatch):
    study = fake_study(monkeypatch)
    history = [record("previous", 8, 9), record("current", 10, 11)]
    before = PILOT.target_point_phase(study, "current", history, 12 * HOUR, 14 * HOUR, {})
    # This newer predecessor would win by element epoch if collection causality leaked.
    after = PILOT.target_point_phase(
        study,
        "current",
        history + [record("later-arrival", 9, 13)],
        12 * HOUR,
        14 * HOUR,
        {},
    )
    assert after == before
    assert before[0] == pytest.approx(0.4)
    assert before[1]["causal_age_h"] == 4


def test_current_element_must_itself_be_available_before_cutoff(monkeypatch):
    with pytest.raises(ValueError, match="current causal element absent"):
        PILOT.target_point_phase(
            fake_study(monkeypatch),
            "current",
            [record("previous", 8, 9), record("current", 10, 13)],
            12 * HOUR,
            14 * HOUR,
            {},
        )


def test_rate_fit_output_is_json_serializable(monkeypatch):
    def optimizer(fun, initial, **kwargs):
        assert np.all(np.isfinite(fun(initial)))
        return SimpleNamespace(x=np.asarray(initial), success=True, nfev=1)

    monkeypatch.setattr(PILOT, "least_squares", optimizer)
    single = SimpleNamespace(
        offset_coordinate=lambda origin, *xy: origin,
        receiver_ecef=lambda *point: (np.zeros(3), None),
        REFERENCE_RF_HZ=11.2e9,
        LIGHT_KM_S=299792.458,
    )
    data = {
        "source": np.array([1, 1, 1]),
        "age_h": np.ones(3),
        "y": np.array([2.0, 3.0, 4.0]),
        "segment": np.zeros(3, dtype=int),
        "training": np.array([True, True, False]),
    }
    states = {key: np.ones((3, 3)) for key in ("p0", "p1", "pm1")}
    states.update({key: np.zeros((3, 3)) for key in ("v0", "v1", "vm1")})
    result = PILOT.fit_model(data, single, (38.0, -122.0, 250.0), states, 0.16, True, np.zeros(2))
    assert json.loads(json.dumps(result))["rate_at_bound_count"] == 0
