import json
from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification import (
    track_transfer,
    track_transfer_upgrade,
    track_transfer_worker,
)
from tools.pipeline_eval.variants import robust_em


def test_measured_common_frequency_is_only_one_lane():
    actual = {"receiver": 1, "channel": 3, "rf_hz": 11_325_000_000}
    info = track_transfer.availability("starloc", {"tracks": [actual] * 11})
    assert info["radio_lanes"] == 1
    assert not info["contract_eligible"]
    with pytest.raises(ValueError, match="tag"):
        track_transfer.availability("starloc", {"tracks": [actual, dict(actual, receiver=2)]})


def test_one_frequency_calibration_cancels_exactly_with_shared_lane_bias():
    def row(lane, rf):
        return SimpleNamespace(lane=lane, rf=rf)

    beacon = [row(0, 11_325_000_000)] * 7
    geometry = track_transfer_worker.calibration_geometry(beacon)
    assert geometry["lane_offset_and_c_rank"] == geometry["lane_offset_rank"] == 1
    assert not geometry["c_has_independent_rf_contrast"]
    assert (
        track_transfer_worker.calibration_geometry(beacon + [row(2, 12_075_000_000)])[
            "lane_offset_and_c_rank"
        ]
        == 2
    )
    assert track_transfer_worker.calibration_geometry(beacon + [row(0, 11_575_000_000)])[
        "c_has_independent_rf_contrast"
    ]


def test_shared_offset_requires_aligned_levels_and_checks_qin_folding():
    def arc(level):
        return SimpleNamespace(
            track=SimpleNamespace(lane=0, drift=np.zeros(4)),
            shape_loss=np.zeros(1),
            residual=np.full((1, 4), level),
            phase=np.zeros((1, 4)),
            phase_seed=np.zeros(1),
        )

    aligned_by_qin = [arc(15_000), arc(15_000 + robust_em.PERIOD), arc(140_000)]
    (report,) = track_transfer_worker.offset_support(aligned_by_qin)
    assert report["shape_supported_independent_offset"] == 3
    assert report["shared_offset_folded"] == 2
    assert report["shared_offset_unwrapped"] == 1
    (report,) = track_transfer_worker.offset_support([arc(0), arc(2_900)])
    assert report["shared_offset_unwrapped"] == 2


def test_horizon_rejects_a_track_candidate_that_sets_during_the_track(monkeypatch):
    track = SimpleNamespace(lane=0, rf=11_325_000_000, t=np.arange(2))
    worker, grid = track_transfer_worker, track_transfer_worker.grid
    tile = SimpleNamespace(
        ecef_center_km=np.zeros(3), enu_frame=np.eye(3), stats={"fine_satellites": 3}
    )
    # Three orbit paths end below the geometric horizon, at 20°, and above 30°.
    position = np.array(
        [[[1, 0, 0.3], [1, 0, -0.02]], [[1, 0, 0.4], [1, 0, 0.36]], [[1, 0, 0.7], [1, 0, 0.75]]]
    )
    monkeypatch.setattr(worker.robust_em, "observations", lambda _: ([track], {}))
    monkeypatch.setattr(grid, "prepare_sky", lambda *_: None)
    monkeypatch.setattr(grid, "make_tile", lambda *_: tile)
    monkeypatch.setattr(grid, "_interpolated_states", lambda *_: (position, None, None))
    monkeypatch.setattr(worker.robust_em, "shortlist", lambda *_: None)
    check = worker.compatibility({}, {"center": [0, 0]}, "")
    assert [r["orbit_track_pairs"] for r in check["horizon"].values()] == [3, 2, 2, 1]


def test_linked_glrt_packet_preserves_frequency_and_clock_and_excludes_ids(monkeypatch):
    capture = SimpleNamespace(
        anchor_utc_ns=2000, cutoff_utc_ns=1900, catalog_timestamp_ns=1800, duration_s=10.0
    )
    linked = SimpleNamespace(
        receiver=1,
        channel=8,
        rf_hz=12_690_312_500,
        times=np.array([2.1, 9.1]),
        cfo=np.array([-1500.0, 70.0]),
        satellite_id=42,
    )
    monkeypatch.setattr(track_transfer.identity_oracles, "tracklets", lambda _: [linked])
    observation = track_transfer.linked_observation(capture)
    tile = dict(id="opaque", center=[10, 20], width_km=25)
    packet = json.loads(track_transfer.request(observation, "causal", tile))
    assert set(packet) == {"observation", "catalogue", "offer"}
    assert packet["observation"]["tracks"] == [
        dict(receiver=2, channel=8, rf_hz=linked.rf_hz, times=[2.1, 9.1], values=[-1500.0, 70.0])
    ]
    assert packet["observation"]["anchor_utc_ns"] == 2000
    with pytest.raises(ValueError, match="future"):
        track_transfer.request(dict(observation, catalog_timestamp_ns=1901), "future", tile)
    with pytest.raises(ValueError, match="fields"):
        track_transfer.request(dict(observation, true_latlon=[10, 20]), "causal", tile)


def test_omitted_false_publications_are_distinct_from_forced_guesses():
    binding = dict(
        id="opaque",
        dataset="starloc",
        group="aliased",
        contract_eligible=False,
        radio_lanes=1,
        observable="beacon",
        tile={"center": [0.0, 0.1]},
    )
    result = dict(
        status="withheld",
        reason="single_lane",
        metrics={},
        arms={arm: {"latlon": None, "forced_latlon": [0.0, 0.2]} for arm in track_transfer.ARMS},
    )
    receipt = dict(result=result, worker_wall_s=0.2, method="robust_em")
    row = track_transfer._score_row(binding, receipt, "omitted", [0.0, 0.0])
    assert row["tile_error_km"] == pytest.approx(11.1195, rel=1e-4)
    assert row["arms"]["c0"]["issued_error_km"] is None
    assert row["arms"]["c0"]["forced_error_km"] == pytest.approx(22.239, rel=1e-4)
    assert not any(row["false_published"].values())


def test_upgrade_replays_the_same_canonical_input_and_counts_only_model_stages():
    raw = b'{"observation":{},"offer":{}}'
    binding = {"input_sha256": track_transfer._sha(raw)}
    assert track_transfer_upgrade.bound_packet(raw, binding) == json.loads(raw)
    with pytest.raises(ValueError, match="changed"):
        track_transfer_upgrade.bound_packet(b'{"offer":{},"observation":{}}', binding)
    result = dict(metrics=dict(observation_s=0.2, orbit_s=0.06, fit_s=0.05, startup_s=1.2))
    assert track_transfer_upgrade.modeled_stages(result) == pytest.approx(0.31)
    assert track_transfer_upgrade.modeled_stages(dict(metrics={})) is None
