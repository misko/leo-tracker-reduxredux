from types import SimpleNamespace

import pytest

from leo.application import regional_position_inputs as module


def setup_source(monkeypatch):
    source = SimpleNamespace(
        capture_mode="adaptive",
        qualified=True,
        timing=SimpleNamespace(first_sample_estimate_utc_ns=10**18),
        input_manifest_sha256="sha256:" + "a" * 64,
        analysis_manifest_sha256="sha256:" + "b" * 64,
    )
    points = []
    for i in range(40):
        for rank in (0, 1):
            points.append(
                SimpleNamespace(
                    source_group_id=f"window-{i:03}",
                    candidate_id=f"candidate-{i:03}-{rank}",
                    margin=0.1 + rank * 0.1,
                    candidate_rank=rank,
                    support_center_utc_ns=10**18 + i * 10**9,
                    measured_cfo_hz=i * 100 + rank,
                    receiver_id=i % 2,
                    actual_rf_hz=11.2e9,
                    channel=1,
                )
            )
    monkeypatch.setattr(module, "timing_is_qualified_for_tle", lambda _: True)
    monkeypatch.setattr(module, "project_scanner_candidates", lambda _: tuple(points))

    def trajectories(selected, **kwargs):
        assert len(selected) == 40
        assert all(p.candidate_rank == 1 for p in selected)
        return SimpleNamespace(tracklets=[SimpleNamespace(points=selected[rx::2]) for rx in (0, 1)])

    monkeypatch.setattr(module, "reconstruct_persistent_hop_trajectories", trajectories)
    return source, points


def test_original_winner_frequency_and_both_receivers(monkeypatch):
    source, _ = setup_source(monkeypatch)
    prepared = module.prepare_position_windows(source)
    assert prepared.observations.measured_hz.tolist() == [i * 100 + 1 for i in range(40)]
    assert len(prepared.bootstrap_tracks) == 2
    assert len(prepared.observations.window_ids) == 40
    assert prepared.start_utc_ns == 10**18
    # Evaluation metadata cannot affect input selection or its digest.
    source.reference_latitude_deg = -40
    source.reference_longitude_deg = 120
    again = module.prepare_position_windows(source)
    assert again.evidence_sha256 == prepared.evidence_sha256


def test_ineligible_capture_and_missing_utc_are_explicit(monkeypatch):
    source, _ = setup_source(monkeypatch)
    source.qualified = False
    with pytest.raises(module.PositionInputUnavailable, match="qualified adaptive"):
        module.prepare_position_windows(source)
    source.qualified = True
    monkeypatch.setattr(module, "timing_is_qualified_for_tle", lambda _: False)
    with pytest.raises(module.PositionInputUnavailable, match="qualified UTC"):
        module.prepare_position_windows(source)


def test_sparse_scan_is_insufficient_not_an_invented_location(monkeypatch):
    source, points = setup_source(monkeypatch)
    monkeypatch.setattr(module, "project_scanner_candidates", lambda _: tuple(points[:10]))
    with pytest.raises(module.PositionInputUnavailable, match="twenty"):
        module.prepare_position_windows(source)
