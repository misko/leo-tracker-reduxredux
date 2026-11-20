import numpy as np
import pytest

from tools.pipeline_eval.qualification import challenge_scenes as study
from tools.pipeline_eval.qualification import challenge_scenes_generator as source


def test_orbit_shift_uses_only_the_satellite_epoch():
    class Satellite:
        def sgp4_array(self, date, fraction):
            return date, fraction

    day = np.array([2459834, 2459834])
    fraction = np.array([0.01, 0.02])
    retimed = source.RetimedOrbit(Satellite(), 0.9)
    out_day, out_fraction = retimed.sgp4_array(day, fraction)
    assert np.array_equal(out_day, day)
    assert (out_fraction - fraction) * 86400 == pytest.approx([0.9, 0.9])


def test_perturbation_keeps_timing_contract_and_candidate_schema(monkeypatch):
    timestamps = np.arange(4, 45, 0.192)
    indices = np.rint(source.base.RATE * timestamps).astype(np.int64)
    probes = [
        source.base._probe_row(i, 0, 1, int(counter), [source.base._peak(1, 10, 20, 0.3)])
        for i, counter in enumerate(indices)
    ]

    def perturb(*args):
        return np.full(len(timestamps), 500.0), np.full(len(timestamps), 120.0)

    monkeypatch.setattr(source, "_changed_geometry", perturb)
    monkeypatch.setattr(source, "GAP_PROBABILITY", 1.0)
    truth = {
        "latlon": [30, 20],
        "clock_bias_s": 0.001,
        "sample_clock_rate_hz": source.base.RATE,
        "emitters": [{"block": 0, "channel": 2, "norad": 137}],
    }
    case = {"probes": probes, "first_counter": 0}
    history = source._perturb(case, truth, {137: object()}, np.random.default_rng(447))
    assert abs(history["phase"][0]["seconds"]) <= 3.0
    assert 4 <= history["lanes"][0]["gap_s"][1] - history["lanes"][0]["gap_s"][0] <= 8
    assert history["lanes"][0]["missed"] == sum(not row["candidates"] for row in probes)
    for probe, counter in zip(probes, indices, strict=True):
        assert probe["valid_start_counter"] == counter
        assert probe["probe_start_ms"] == 0
        for peak in probe["candidates"]:
            assert set(peak) == set(source.base.CANDIDATE_FIELDS)
            assert 285 <= peak["fractional_tracking_cfo_hz"] <= 735
            epoch = peak["integer_epoch_sample"] + peak["fractional_epoch_offset_samples"]
            assert 138.65 <= epoch <= 141.35


def test_pair_validation_rejects_different_serialized_inputs_and_old_capture():
    query = {"id": "q", "capture_id": "capture", "tile": {"center": [10, 20], "width_km": 25}}
    baseline = dict(
        query,
        native_sha256="packet",
        catalog_sha256=study.cold_scenes.CATALOG_SHA256,
        worker_input_sha256="both",
        cohort="exact",
    )
    rows = [dict(baseline, method=m) for m in study.METHODS]
    manifests = {"exact": {"cases": {"capture": "packet"}}}
    study._checked_records(rows, {"exact": [query]}, manifests)
    rows[1]["worker_input_sha256"] = "different"
    with pytest.raises(ValueError, match="different serialized"):
        study._checked_records(rows, {"exact": [query]}, manifests)
    with pytest.raises(ValueError, match="reuses"):
        study._disjoint([*manifests.values(), {"cases": {"another_capture": "packet"}}])
