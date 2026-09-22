from types import SimpleNamespace

import numpy as np
import pytest

import leo.operations.blind_tracking_inputs as subject
from leo.contracts.digests import canonical_digest


class _Satellite:
    def __init__(self, failure=False):
        self.failure = failure

    def sgp4_array(self, jd, fraction):
        count = len(np.asarray(jd))
        errors = np.ones(count, dtype=int) if self.failure else np.zeros(count, dtype=int)
        return errors, np.tile((7000.0, 0.0, 0.0), (count, 1)), np.tile((0.0, 7.5, 0.0), (count, 1))


def _row(number, start):
    return SimpleNamespace(
        observation_id=canonical_digest({"observation": number}),
        support_center_utc_ns=start + number * 1_000_000_000,
        measured_cfo_hz=100.0 + number,
    )


def _arrange(monkeypatch, *, row_count=16):
    start = 2_000_000_000_000
    rows = tuple(_row(number, start) for number in range(row_count))
    graph = SimpleNamespace(observations=rows)
    trajectory = SimpleNamespace(hypotheses=(SimpleNamespace(tracklet_ids=("rf-track",)),))
    monkeypatch.setattr(subject, "timing_is_qualified_for_tle", lambda timing: True)
    monkeypatch.setattr(subject, "project_scanner_candidates", lambda source: (object(),))
    monkeypatch.setattr(
        subject, "reconstruct_persistent_hop_trajectories", lambda *args, **kwargs: trajectory
    )
    monkeypatch.setattr(
        subject, "persistent_hop_tracklet_graph", lambda hypothesis, track_id: graph
    )
    monkeypatch.setattr(subject, "exclude_labelled_starlink_debris", lambda payload: (payload, ()))
    catalogue = SimpleNamespace(
        names=("STARLINK-A", "STARLINK-B", "OTHER"),
        satellite_numbers=(101, 102, 999),
        satellites=(_Satellite(), _Satellite(failure=True), _Satellite()),
        element_epoch_utc_ns=lambda: (
            start - 10_000_000_000,
            start - 10_000_000_000,
            start - 10_000_000_000,
        ),
    )
    monkeypatch.setattr(subject, "parse_element_sets", lambda payload: catalogue)
    source = SimpleNamespace(
        session_id="scan",
        timing=object(),
        input_manifest_sha256="sha256:" + "1" * 64,
        analysis_manifest_sha256="sha256:" + "2" * 64,
    )
    inputs = SimpleNamespace(load=lambda session_id: source)
    snapshot = SimpleNamespace(
        digest="sha256:" + "3" * 64,
        collected_utc_ns=start - 600_000_000_000,
        provider="space-track",
    )
    archive = SimpleNamespace(
        select_latest_before=lambda cutoff: snapshot,
        read=lambda selected: "tle payload",
    )
    return inputs, archive, start


def test_prepares_truth_free_tracks_and_full_causal_starlink_states(monkeypatch):
    inputs, archive, start = _arrange(monkeypatch)
    prepared = subject.prepare_blind_tracking_inputs("scan", inputs=inputs, archive=archive)

    assert prepared.known_position_used_for_track_construction is False
    assert prepared.known_position_used_for_catalogue_selection is False
    assert prepared.site_conditioned_candidates is False
    assert prepared.region.center_latitude_deg == pytest.approx(39.7392)
    assert prepared.tracks[0].support_center_utc_ns[0] == start
    assert 2 <= prepared.tracks[0].training.sum() <= len(prepared.tracks[0].training) - 2
    assert prepared.catalogue.catalog_number.tolist() == [101]
    assert prepared.catalogue.position_ecef_km[0].shape == (1, 16, 1, 3)
    assert any(item.reason == "propagation-failed" for item in prepared.exclusions)
    assert prepared.source_digest.startswith("sha256:")


def test_bounds_rows_and_selects_snapshot_before_guard(monkeypatch):
    inputs, archive, start = _arrange(monkeypatch, row_count=80)
    cutoffs = []
    original = archive.select_latest_before
    archive.select_latest_before = lambda cutoff: (cutoffs.append(cutoff), original(cutoff))[1]
    limits = subject.BlindInputLimits(maximum_observations_per_track=20)

    prepared = subject.prepare_blind_tracking_inputs(
        "scan", inputs=inputs, archive=archive, limits=limits
    )

    assert len(prepared.tracks[0].observation_id) == 20
    assert prepared.omitted_observation_count == 60
    assert any(item.reason == "observation-limit" for item in prepared.exclusions)
    assert prepared.tracks[0].support_center_utc_ns[[0, -1]].tolist() == [
        start,
        start + 79_000_000_000,
    ]
    assert cutoffs == [start - 505_000_000_000]


def test_rejects_unqualified_utc_before_archive_access(monkeypatch):
    inputs, archive, _ = _arrange(monkeypatch)
    monkeypatch.setattr(subject, "timing_is_qualified_for_tle", lambda timing: False)
    archive.select_latest_before = lambda cutoff: pytest.fail("archive must not be read")
    with pytest.raises(subject.BlindInputUnavailable, match="utc-unqualified"):
        subject.prepare_blind_tracking_inputs("scan", inputs=inputs, archive=archive)


def test_region_and_work_bounds_are_explicit():
    with pytest.raises(ValueError, match="dimensions"):
        subject.BlindRegion(width_km=20_001)
    with pytest.raises(ValueError, match="maximum_tracks"):
        subject.BlindInputLimits(maximum_tracks=65)


def test_ambiguous_hypothesis_graph_is_reported(monkeypatch):
    inputs, archive, start = _arrange(monkeypatch)
    first = SimpleNamespace(observations=tuple(_row(number, start) for number in range(16)))
    second = SimpleNamespace(observations=tuple(_row(number + 1, start) for number in range(16)))
    trajectory = SimpleNamespace(
        hypotheses=(
            SimpleNamespace(tracklet_ids=("ambiguous", "usable")),
            SimpleNamespace(tracklet_ids=("ambiguous",)),
        )
    )
    monkeypatch.setattr(
        subject, "reconstruct_persistent_hop_trajectories", lambda *args, **kwargs: trajectory
    )
    monkeypatch.setattr(
        subject,
        "persistent_hop_tracklet_graph",
        lambda hypothesis, track_id: (
            first if track_id == "usable" or hypothesis is trajectory.hypotheses[0] else second
        ),
    )

    prepared = subject.prepare_blind_tracking_inputs("scan", inputs=inputs, archive=archive)

    assert [track.track_id for track in prepared.tracks] == ["usable"]
    assert any(item.reason == "ambiguous-hypothesis-graph" for item in prepared.exclusions)
