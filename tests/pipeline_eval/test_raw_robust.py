from pathlib import Path

import numpy as np
import pytest

from tools.pipeline_eval.qualification import raw_robust, raw_robust_worker


def graph_track(channel):
    return dict(
        times=np.array([2.0, 3.0]),
        values=np.array([75.0, 25.0]),
        receiver=1,
        channel=channel,
        rf_hz=11.2e9,
        satellite=42200,
        old_position=[42.0, 64.0],
    )


def projection(channels=(1, 2)):
    graph = dict(
        metadata=dict(causal_cutoff_utc_ns=100, anchor_utc_ns=103, duration_s=10.0),
        tracks=[graph_track(ch) for ch in channels],
    )
    return raw_robust_worker.anonymous(graph, 100, 95)


def test_anonymous_projection_strips_non_numerical_and_identity_fields():
    packet = projection()

    assert set(packet) == {
        "anchor_utc_ns",
        "cutoff_utc_ns",
        "duration_s",
        "catalog_timestamp_ns",
        "tracks",
    }
    assert all(set(track) == set(raw_robust_worker.TRACK_FIELDS) for track in packet["tracks"])
    assert packet["tracks"][0]["times"] == [2.0, 3.0]


@pytest.mark.parametrize("cutoff,catalog", [(101, 95), (100, 101)])
def test_rejects_rebound_capture_authority_or_future_catalogue(cutoff, catalog):
    original = dict(metadata={"causal_cutoff_utc_ns": 100}, tracks=[])
    with pytest.raises(ValueError, match="outside capture authority"):
        raw_robust_worker.anonymous(original, cutoff, catalog)


def test_projection_audit_distinguishes_order_and_cfo_difference():
    first = projection()
    alternate = projection((2, 1))
    matched = raw_robust.compare_projection(first, alternate)
    assert not matched["exact_document"]
    assert matched["same_lanes_and_timestamps"] == 2
    assert matched["same_lanes_timestamps_and_cfo"] == 2
    assert matched["largest_matched_cfo_difference_hz"] == 0.0
    alternate["tracks"][1]["values"][0] += 17.0
    changed = raw_robust.compare_projection(first, alternate)
    assert changed["same_lanes_timestamps_and_cfo"] == 1
    assert changed["largest_matched_cfo_difference_hz"] == 17.0


def test_archived_projection_is_opened_only_after_fresh_fit(tmp_path, monkeypatch):
    orbit = tmp_path / "catalogue.tle"
    orbit.write_text("test causal catalogue")
    setup = {
        "id": "ID",
        "native": {"path": "native.json", "sha256": "bound-native"},
        "recording": {},
        "catalog": {"path": str(orbit), "sha256": "frozen-catalogue"},
        "observation": "frozen-archive-projection",
        "track_config": {"path": "tracking.json", "sha256": "frozen-track-config"},
        "regions": [{"id": "original", "center": list(raw_robust.v5_lean.ROOF_CENTER)}],
    }
    fresh_data = projection()
    seen = []
    monkeypatch.setattr(raw_robust, "_load_case", lambda _: setup)
    monkeypatch.setattr(raw_robust, "_check", lambda path, _: path)
    monkeypatch.setattr(
        raw_robust,
        "bind_detector",
        lambda *_: (Path("native.json"), "bound-native", {"replayed_here": False}),
    )
    monkeypatch.setattr(
        raw_robust,
        "build_tracks",
        lambda *_: dict(
            projection=fresh_data, metrics={"tracks": 2, "track_peak_rss_kib": 64}, authority={}
        ),
    )
    locked = {"robust_em.py": "frozen-fit"}
    monkeypatch.setattr(raw_robust.robust_em_trials, "source_hashes", lambda: locked)
    monkeypatch.setattr(
        raw_robust,
        "locked_sources",
        lambda: dict(robust_em=locked, frozen_tracker="frozen-tracker"),
    )

    def fit(packet, cpu):
        assert set(packet) == {"observation", "catalogue", "offer"}
        assert packet["observation"] is fresh_data
        seen.append("fit")
        result = dict(
            status="withheld",
            reason="test",
            metrics={},
            arms={arm: {"latlon": None} for arm in raw_robust.ARMS},
        )
        return (dict(result=result, worker_cpu_s=0.01, max_rss_kib=128), 0.03)

    def read_reference(*_):
        assert seen == ["fit"]
        seen.append("archived comparison")
        return projection((2, 1))

    monkeypatch.setattr(raw_robust, "_fit", fit)
    monkeypatch.setattr(raw_robust, "_frozen_port", read_reference)
    saved = raw_robust.predict("ID", "capture-era", tmp_path, 17)
    assert seen == ["fit", "archived comparison"]
    assert saved["native_sha256"] == "bound-native"
    assert saved["projection_audit"]["same_lanes_timestamps_and_cfo"] == 2


def test_standard_entry_point_requires_native_file_even_when_transfer_tracks_exist(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(raw_robust, "_load_case", lambda _: {"id": "TRANSFER", "tracks": "present"})
    result = raw_robust.run({"id": "TRANSFER"}, tmp_path)
    assert result["status"] == "unavailable"
    assert "native GLRT archive" in result["reason"]
    assert "input_binding" not in result
