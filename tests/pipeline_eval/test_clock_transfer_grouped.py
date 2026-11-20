from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification import clock_transfer_grouped_results as results
from tools.pipeline_eval.variants import clock_transfer_grouped as model


def test_rf_calibration_adds_no_unrestricted_rank_with_multiple_bands_and_receivers():
    path = np.array([0, 0, 0, 1, 1, 1, 2, 2])
    rf = np.array([10.8, 11.2, 12.4, 11.3, 11.7, 12.2, 10.8, 12.4]) * 1e9
    sat = np.array([10, 11, 10, 10, 11, 11, 12, 10])
    audit = model.calibration_gauge(path, rf, sat)
    assert audit["c_norm"] > 1
    assert audit["c_null_error"] < 1e-12
    assert audit["unrestricted_rank"] == audit["rank_with_c"]
    columns = model.columns(np.arange(len(path)), path, rf, sat, [0, 1, 2], [10, 11, 12])
    np.testing.assert_allclose(columns[:, 6:].sum(axis=1), rf / model.RF)


def test_carrier_prior_requires_temporal_overlap_in_distinct_capture_contexts():
    def track(path, rf, time, sat):
        return SimpleNamespace(path=path, rf=rf, time=np.array(time), orbit=[sat])

    rows = [
        track(0, 10.8e9, [0, 15], 10),
        track(0, 11.2e9, [10, 24], 10),
        track(0, 10.8e9, [0, 15], 11),
        track(0, 10.8e9, [5, 22], 11),
        track(0, 10.8e9, [0, 15], 12),
        track(1, 10.8e9, [14, 28], 12),
    ]
    assert model.overlap_families([(row, 0) for row in rows]) == [10]


def trial_target():
    def projection(samples):
        states = np.zeros((2, samples, 3))
        states[..., 0] = 6500.0
        return states, np.zeros_like(states)

    p, v = projection(3)
    fp, fv = projection(4)
    return model.Track(
        block=1,
        path=0,
        rf=model.RF,
        time=np.array([31.0, 36.0, 40.0]),
        observed=np.full(3, 1000.0),
        orbit=np.array([10, 11]),
        phase=np.zeros(2),
        levels=np.zeros(2),
        losses=np.zeros(2),
        p=p,
        v=v,
        held_time=np.array([51.0, 52.0, 53.0, 54.0]),
        held_peaks=np.full((4, 1), 1000.0),
        held_keep=np.ones((4, 1), dtype=bool),
        held_p=fp,
        held_v=fv,
    )


def test_first_unknown_target_identity_depends_on_carrier_labels_and_head_only():
    target = trial_target()
    geo = np.zeros(3)
    args = (geo, [0], {0: 0.0}, [10, 11], np.array([0.0, 0.0, 1000.0, -1000.0]))
    first = model.target_prediction(target, *args, "carried")
    tampered = replace(target, held_peaks=np.full((4, 1), -3600.0))
    second = model.target_prediction(tampered, *args, "carried")
    sham = model.target_prediction(target, *args, "identity_sham")
    assert first["orbit"] == second["orbit"] == 10
    assert first["held_rms_hz"] == 0
    assert second["held_rms_hz"] == 4600
    assert sham["orbit"] == 11
    assert model.target_prediction(target, geo, [0], {0: 0}, [], np.zeros(2), "carried") is None


def test_capped_loss_and_rf_comparison_keep_unsupported_targets_explicit():
    good = dict(held_loss=4, held_rms_hz=800, head_loss=1, block=3, orbit=4, held_points=5)
    combined = model.measures([good, None], 2)
    assert combined["loss"] == (4 + model.CAP) / 2
    assert combined["predicted_tracks"] == 1
    assert combined["rms_hz"] == 800
    assert combined["supported_blocks"] == combined["supported_orbits"] == 1
    with pytest.raises(ValueError, match="different raw visits"):
        results.paired([dict(carried=good, control=dict(good, held_points=4))], "control")
