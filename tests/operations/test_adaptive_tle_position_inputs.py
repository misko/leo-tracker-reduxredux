from types import SimpleNamespace

import pytest

import leo.operations.adaptive_tle_position_inputs as subject
from leo.contracts.digests import canonical_digest


def test_prepares_all_eligible_tracks_with_fixed_position_independent_split(monkeypatch):
    start = 2_000_000_000_000
    rows = tuple(
        SimpleNamespace(
            observation_id=canonical_digest({"row": index}),
            support_center_utc_ns=start + index * 1_000_000_000,
            measured_cfo_hz=float(index),
        )
        for index in range(6)
    )
    graph = SimpleNamespace(observations=rows)
    trajectory = SimpleNamespace(
        hypotheses=(SimpleNamespace(tracklet_ids=("track",)),), tracklets=(1, 2)
    )
    monkeypatch.setattr(subject, "timing_is_qualified_for_tle", lambda timing: True)
    monkeypatch.setattr(subject, "project_scanner_candidates", lambda source: ())
    monkeypatch.setattr(
        subject, "reconstruct_persistent_hop_trajectories", lambda *args, **kwargs: trajectory
    )
    monkeypatch.setattr(subject, "persistent_hop_tracklet_graph", lambda *args: graph)
    monkeypatch.setattr(
        subject.CataloguePredictionSupportV1,
        "from_graph",
        lambda graph: SimpleNamespace(content_digest="sha256:" + "4" * 64),
    )
    monkeypatch.setattr(subject, "exclude_labelled_starlink_debris", lambda value: (value, ()))
    catalogue = SimpleNamespace(
        names=("STARLINK-A", "OTHER"), satellite_numbers=(123, 999)
    )
    monkeypatch.setattr(subject, "parse_element_sets", lambda value: catalogue)
    source = SimpleNamespace(
        timing=SimpleNamespace(first_sample_estimate_utc_ns=start),
        input_manifest_sha256="sha256:" + "1" * 64,
        analysis_manifest_sha256="sha256:" + "2" * 64,
    )
    snapshot = SimpleNamespace(
        digest="sha256:" + "3" * 64, collected_utc_ns=start - 600_000_000_000
    )
    prepared = subject.prepare_adaptive_tle_position_inputs(
        "scan",
        inputs=SimpleNamespace(load=lambda session: source),
        archive=SimpleNamespace(
            select_latest_before=lambda cutoff: snapshot, read=lambda selected: "tle"
        ),
    )
    assert prepared.reconstructed_track_count == 2
    assert prepared.eligible_track_count == 1
    assert prepared.eligible_observation_count == 6
    assert prepared.candidate_indices.tolist() == [0]
    assert prepared.tracks[0].training_mask.sum() in (3, 4)
    assert prepared.track_evidence[0]["partition_seed"].startswith("sha256:")


def test_rejects_unqualified_utc(monkeypatch):
    monkeypatch.setattr(subject, "timing_is_qualified_for_tle", lambda timing: False)
    source = SimpleNamespace(timing=object())
    with pytest.raises(subject.AdaptiveTleInputUnavailable, match="qualified UTC"):
        subject.prepare_adaptive_tle_position_inputs(
            "scan", inputs=SimpleNamespace(load=lambda session: source), archive=object()
        )
