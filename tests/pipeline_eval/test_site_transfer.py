from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification import site_transfer as trial
from tools.pipeline_eval.qualification import site_transfer_samples as samples


def probes_at(times, frequencies):
    return [
        samples.cold._probe_row(
            i,
            0,
            0,
            round(t * samples.cold.RATE),
            [samples.cold._peak(1, frequency, 42.0, 0.4)],
        )
        for i, (t, frequency) in enumerate(zip(times, frequencies, strict=True))
    ]


def test_donor_binding_and_residual_temporal_order():
    pool, receipts = samples.donors()
    assert len(receipts) == 6
    assert sum(r["matched_rows"] for r in receipts) == 15134
    assert len(pool) == sum(r["qualified_tracks"] for r in receipts) == 85
    _, times, values = samples._window(pool, np.random.default_rng(103))
    assert (np.diff(times) > 0).all()
    assert 0 <= times[0] < times[-1] <= 40
    assert np.median(values) == pytest.approx(0)


def test_replay_preserves_clock_epoch_and_slot_occupancy(monkeypatch):
    offsets = np.array([0.01, 2.01])
    residuals = np.array([35.0, -35.0])
    monkeypatch.setattr(samples, "_window", lambda pool, rng: ({}, offsets, residuals))
    probes = probes_at((5, 6, 7), (1000, 1500, 2000))
    row = dict(first_counter=0, probes=probes)
    (audit,) = samples._inject(row, [], None)
    assert not probes[1]["candidates"]
    assert [p["valid_start_counter"] for p in probes] == [50_000_000, 60_000_000, 70_000_000]
    valid = [probe["candidates"][0] for probe in (probes[0], probes[2])]
    assert [peak["integer_epoch_sample"] for peak in valid] == [42, 42]
    assert [peak["fractional_tracking_cfo_hz"] for peak in valid] == [1035, 1965]
    assert audit["retained"] == 2 and audit["retained_span_s"] == pytest.approx(2)


def test_projection_unwraps_and_retains_native_probe_midpoints():
    timestamps = np.arange(18)
    probes = probes_at(timestamps, 118000 - timestamps * 2000)
    probes[0]["probe_start_ms"] = 1
    capture = SimpleNamespace(
        first_counter=0,
        sample_rate_hz=samples.cold.RATE,
        probe_ms=samples.cold.PROBE_MS,
        anchor_utc_ns=1000,
        cutoff_utc_ns=999,
        catalog_timestamp_ns=998,
        duration_s=18.0,
        probes=probes,
    )
    assert set(samples.projection(capture)) == {
        "anchor_utc_ns",
        "cutoff_utc_ns",
        "catalog_timestamp_ns",
        "duration_s",
        "tracks",
    }
    (track,) = samples.projection(capture)["tracks"]
    assert track["receiver"] == 1 and track["channel"] == 1
    assert track["times"][0] == pytest.approx(0.011)
    assert np.diff(track["values"]) == pytest.approx([-2000] * 17)


def test_acceptance_binds_prepared_observation_and_supplied_tile_for_both_receivers():
    offer = dict(id="tile", capture_id="native", tile=dict(id="tile", center=[1, 2], width_km=25))
    packet = dict(observation={"tracks": []}, catalogue="causal")
    bindings = dict(native_sha256="native", catalog_sha256="catalog")
    digest = trial.cold_scenes._sha(trial.encoded(packet | {"offer": offer["tile"]}))
    predictions = [
        dict(**offer, **bindings, method=method, worker_input_sha256=digest)
        for method in trial.METHODS
    ]
    trial._check_pair(predictions, [offer], {"native": (packet, bindings)})
    predictions[-1]["worker_input_sha256"] = "different"
    with pytest.raises(ValueError, match="same prospective packet"):
        trial._check_pair(predictions, [offer], {"native": (packet, bindings)})
