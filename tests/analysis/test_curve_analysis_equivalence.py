"""Metadata-only curve refits may reuse a search; measurement changes may not."""

import importlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np


def test_fingerprint_covers_observations_calibration_candidates_and_priors(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    fingerprint = importlib.import_module(
        "reuse_equivalent_curve_search"
    ).analysis_input_fingerprint
    study = SimpleNamespace(
        receipt=dict(bank_sha256="bank1", regional_center=[37.5, -122], radius_km=250),
        initial=np.zeros(8),
        sigma=np.ones(1),
        bounds=np.full(1, 3),
        phase_radius_km=np.full(1, 24),
        fitted_c=False,
        phase_enabled=True,
        drift_sigma_hz_s=0.5,
        drift_bound_hz_s=1,
        curved_keys={"curve"},
        times=np.arange(5.0),
        tracks=[
            dict(
                key="curve",
                receiver=1,
                channel=1,
                rf_hz=11.5e9,
                times=np.arange(5.0),
                values=np.arange(5.0),
                observation_ids=[str(i) for i in range(5)],
                pieces=[dict(degree=4, coefficients_hz=[1, 2, 3, 4, 5])],
            )
        ],
    )
    original = fingerprint(study)
    study.tracks[0]["pieces"] = [dict(degree=1, coefficients_hz=[100, 200])]
    assert fingerprint(study) == original
    for field, changed in (
        ("values", np.arange(5.0) + 1),
        ("times", np.arange(5.0) + 0.01),
        ("rf_hz", 11.6e9),
        ("observation_ids", [str(i + 1) for i in range(5)]),
    ):
        old = study.tracks[0][field]
        study.tracks[0][field] = changed
        assert fingerprint(study) != original
        study.tracks[0][field] = old
    study.receipt["bank_sha256"] = "bank2"
    assert fingerprint(study) != original
    study.receipt["bank_sha256"] = "bank1"
    study.curved_keys = set()
    assert fingerprint(study) != original
    study.curved_keys = {"curve"}
    study.drift_bound_hz_s = 5
    assert fingerprint(study) != original
