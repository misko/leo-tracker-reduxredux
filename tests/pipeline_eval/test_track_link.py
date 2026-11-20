import json
from collections import Counter

import numpy as np
import pytest

from tools.pipeline_eval.variants import track_link

LANE = (1, 3, 11.5e9)
PERIOD = 1 / 4.4e-6


def orbit_one(t):
    return 128_000 - 2_200 * t + 9 * t**2


def orbit_two(t):
    return 106_000 - 500 * t - 5 * t**2


def wrapped(frequency):
    return (frequency + PERIOD / 2) % PERIOD - PERIOD / 2


def test_crossing_wrap_and_dropout_preserve_each_emitter():
    tracker = track_link.Tracker()
    omitted = {12.0, 12.5, 13.0, 13.5}
    for t in np.arange(0.0, 46.5, 0.5):
        options = [orbit_two(t)]
        if t not in omitted:
            options.append(orbit_one(t))
        if t in {8.0, 16.0, 24.0, 32.0, 40.0}:
            options.append(2_100.0)
        merged = []
        for peak in options:
            if all(abs(wrapped(peak - previous)) >= 350.0 for previous in merged):
                merged.append(peak)
        tracker.ingest(float(t), LANE, [wrapped(peak) for peak in merged])

    document, stats = tracker.document()
    tracks = document["tracks"]
    assert len(tracks) == 2
    owners = Counter()
    for track in tracks:
        times, values = track["times"], track["values"]
        (owner,) = [
            source for source in (orbit_one, orbit_two) if np.ptp(values - source(times)) < 1e-6
        ]
        owners[owner] += 1
        assert len(times) >= 88
        assert times[0] == 0.0 and times[-1] == 46.0
    assert owners == {orbit_one: 1, orbit_two: 1}
    assert stats["confirmed_missed_visits_bridged"] >= len(omitted)
    assert stats["candidate_max_link_gap_s"] == pytest.approx(2.5)


def test_causal_snapshot_and_bounded_support_during_a_dense_pass():
    tracker = track_link.Tracker()
    times = np.arange(0.0, 140.0, 0.1)

    def cfo(t):
        return 112_000 - 600 * t - 4 * t**2

    for t in times[:650]:
        tracker.ingest(float(t), LANE, [wrapped(cfo(t))])
    prefix = tracker.document()[0]["tracks"][0]
    assert prefix["times"][-1] == pytest.approx(times[649])
    assert len(prefix["times"]) <= track_link.MAX_SUPPORT
    for t in times[650:]:
        tracker.ingest(float(t), LANE, [wrapped(cfo(t))])
    (track,) = tracker.document()[0]["tracks"]
    assert prefix["times"][-1] == pytest.approx(times[649])
    assert track["times"][-1] == pytest.approx(times[-1])
    assert len(track["times"]) <= track_link.MAX_SUPPORT
    assert np.ptp(track["values"] - cfo(track["times"])) < 1e-6


def test_ambiguous_peak_pair_is_skipped_and_later_track_can_recover():
    def cfo(t):
        return orbit_one(np.minimum(t, 25.0)) - 1_750.0 * np.maximum(t - 25.0, 0.0)

    tracker = track_link.Tracker()
    for t in np.arange(0.0, 50.0, 0.5):
        expected = cfo(t)
        peaks = [expected + 220.0, expected - 220.0] if t == 36.0 else [expected]
        tracker.ingest(float(t), LANE, [wrapped(peak) for peak in peaks])
    document, stats = tracker.document()
    (track,) = document["tracks"]
    assert 36.0 not in track["times"] and 36.5 in track["times"]
    assert stats["ambiguous_tracks"] == 1
    assert np.ptp(track["values"] - cfo(track["times"])) < 1e-6


def _write_native(path, cfo=orbit_one):
    probes = []
    for index in range(100):
        probes.append(
            dict(
                actual_rf_hz=11.5e9,
                candidates=[
                    dict(
                        candidate_rank=0,
                        fractional_margin=3.0,
                        passed_fractional_margin_gate=True,
                        fractional_tracking_cfo_hz=cfo(index * 0.5 + 0.01),
                    )
                ],
                channel=3,
                receiver_id=0,
                valid_start_counter=index * 5_000_000,
                visit_index=index,
            )
        )
    native = {
        "clock_anchor": dict(
            sample_counter=0, before={"realtime_ns": 100}, after={"realtime_ns": 104}
        ),
        "last_sample_counter": 500_000_000,
        "source": dict(probe_ms=20, probes=probes, sample_rate_hz=10_000_000, visit_ms=40),
    }
    path.write_text(json.dumps(native, separators=(",", ":")))


def test_run_passes_its_native_tracks_to_solver_and_preserves_withholding(tmp_path, monkeypatch):
    native = tmp_path / "native.json"
    _write_native(native)
    catalogue = tmp_path / "90-catalog.tle"
    catalogue.write_bytes(b"test catalogue")
    regions = [dict(id="tile", center=[13.0, -16.0])]
    case = dict(
        id="roof",
        native_path=native,
        catalog_path=catalogue,
        regions=regions,
        observation_path=tmp_path / "must-not-be-needed.json",
    )
    seen = []

    def solve(observation, offered, raw):
        seen.append(observation)
        assert offered == regions and raw == b"test catalogue"
        assert observation["cutoff_utc_ns"] == 100
        assert observation["catalog_timestamp_ns"] == 90
        (track,) = observation["tracks"]
        assert (track["receiver"], track["channel"], track["rf_hz"]) == LANE
        assert len(track["values"]) == 100
        assert np.ptp(track["values"] - orbit_one(track["times"])) < 1e-6
        return dict(
            status="withheld",
            latlon=None,
            best_latlon=[13.0, -16.0],
            region_id=None,
            reason="position_at_tile_boundary",
            diagnostics={"work": {"grid_fits": 3}},
        )

    monkeypatch.setattr(track_link.receiver, "solve", solve)
    result = track_link.run(case, tmp_path)
    assert len(seen) == 2 and result["status"] == "withheld"
    assert result["metrics"]["native_probes"] == 100
    assert result["arms"]["c0"] == result["arms"]["fitted_c"]
    assert result["arms"]["c0"]["latlon"] is None
    assert result["arms"]["c0"]["forced_latlon"] == [13.0, -16.0]
    json.dumps(result, allow_nan=False)


def test_run_with_missing_factors_is_unavailable(tmp_path):
    record = track_link.run(dict(graph_path=tmp_path / "already-linked.json"), tmp_path)
    assert record["status"] == "unavailable"
    assert all(arm["latlon"] is None for arm in record["arms"].values())


def test_unphysical_rising_arc_cannot_publish_the_control_fix(tmp_path, monkeypatch):
    def rising(t):
        return -68_000 + 2_800 * t + 7 * t**2

    native = tmp_path / "native.json"
    _write_native(native, rising)
    catalogue = tmp_path / "90-catalog.tle"
    catalogue.write_bytes(b"test catalogue")
    regions = [dict(id="tile", center=[13.0, -16.0])]

    def solve(observation, offered, raw):
        has_tracks = bool(observation["tracks"])
        return dict(
            status="fix" if has_tracks else "withheld",
            latlon=[13.0, -16.0] if has_tracks else None,
            best_latlon=[13.0, -16.0] if has_tracks else None,
            region_id="tile" if has_tracks else None,
            reason="accepted" if has_tracks else "insufficient_tracks",
            diagnostics={"work": {"grid_fits": int(has_tracks)}},
        )

    monkeypatch.setattr(track_link.receiver, "solve", solve)
    case = dict(id="rising", native_path=native, catalog_path=catalogue, regions=regions)
    result = track_link.run(case, tmp_path)
    assert result["status"] == "withheld"
    assert result["reason"] == "insufficient_tracks"
    assert result["arms"]["c0"]["latlon"] is None
    assert result["metrics"]["control_latlon"] == [13.0, -16.0]
    assert result["metrics"]["candidate_tracks"] == 0
    assert result["metrics"]["control_tracks"] == 1


def test_future_catalog_is_unavailable(tmp_path):
    native = tmp_path / "native.json"
    _write_native(native)
    catalogue = tmp_path / "101-future.tle"
    catalogue.write_bytes(b"test catalogue")
    regions = [dict(id="tile", center=[13.0, -16.0])]
    case = dict(id="roof", native_path=native, catalog_path=catalogue, regions=regions)
    result = track_link.run(case, tmp_path)
    assert result["status"] == "unavailable"
    assert all(arm["latlon"] is None for arm in result["arms"].values())
