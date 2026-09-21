from dataclasses import replace

import numpy as np
import pytest

import leo.analysis.sparse_scan_position as subject
from leo.analysis.research.regional_doppler import LIGHT_KM_S, REFERENCE_RF_HZ, Region
from leo.analysis.sparse_scan_position import (
    SparseScanPositionConfig,
    SparseScanPositionObservation,
    infer_sparse_scan_position,
)


def _observations(region, east=30.0, north=-20.0):
    receiver = region.points([east], [north]).ecef_km[0]
    rows = []
    for source in range(4):
        for index in range(8):
            angle = 0.45 + source * 1.15 + index * 0.025
            p = np.asarray([6800 * np.cos(angle), 6800 * np.sin(angle), 900 + 180 * source])
            v = np.asarray([-7 * np.sin(angle), 7 * np.cos(angle), 0.15 * (source - 1)])
            delta = p - receiver
            doppler = -REFERENCE_RF_HZ / LIGHT_KM_S * np.dot(delta, v) / np.linalg.norm(delta)
            rows.append(
                SparseScanPositionObservation(
                    f"o-{source}-{index}",
                    1_800_000_000_000_000_000 + index * 1_000_000_000,
                    float(doppler + 12000 * source),
                    f"source-{source}",
                    f"segment-{source}",
                    index < 6,
                    tuple(p),
                    tuple(v),
                )
            )
    return tuple(rows)


def test_sparse_scan_position_recovers_conditional_mode_without_truth_input():
    region = Region(37.8, -122.4, 400, 400)
    result = infer_sparse_scan_position(
        _observations(region),
        region=region,
        config=SparseScanPositionConfig(coarse_spacing_km=40, local_initial_half_width_km=50),
    )
    assert result.state == "complete"
    assert result.conditional_fixed_identity and not result.blind_positioning
    assert not result.calibrated_position_fix and result.candidate_only
    assert np.hypot(result.east_km - 30, result.north_km + 20) < 4
    assert result.training_point_count == 20
    assert result.evaluation_point_count == 8
    assert result.information_rank == 2
    assert len(result.training_residual_hz) == 20
    assert len(result.evaluation_residual_hz) == 8
    assert len(result.map_training_rms_hz) == 17**2


def test_sparse_scan_position_abstains_for_too_few_sources():
    region = Region(37.8, -122.4, 400, 400)
    rows = tuple(row for row in _observations(region) if row.source_id in {"source-0", "source-1"})
    result = infer_sparse_scan_position(rows, region=region)
    assert result.state == "insufficient"
    assert "too-few-distinct-sources" in result.reasons
    assert result.latitude_deg is None


def test_sparse_scan_position_is_deterministic_and_bounded():
    region = Region(37.8, -122.4, 400, 400)
    rows = _observations(region)
    config = SparseScanPositionConfig(coarse_spacing_km=50, local_initial_half_width_km=50)
    assert infer_sparse_scan_position(
        rows, region=region, config=config
    ) == infer_sparse_scan_position(rows, region=region, config=config)
    with pytest.raises(ValueError, match="work bound"):
        excessive = tuple(
            row.__class__(
                row.observation_id,
                row.support_utc_ns,
                row.measured_cfo_hz,
                f"unique-{i}",
                row.segment_id,
                row.training,
                row.satellite_position_ecef_km,
                row.satellite_velocity_ecef_km_s,
            )
            for i, row in enumerate(rows)
        )
        extra = rows[0].__class__(
            "extra",
            rows[0].support_utc_ns,
            rows[0].measured_cfo_hz,
            "unique-extra",
            rows[0].segment_id,
            rows[0].training,
            rows[0].satellite_position_ecef_km,
            rows[0].satellite_velocity_ecef_km_s,
        )
        infer_sparse_scan_position((*excessive, extra), region=region)


def test_sparse_scan_position_rejects_duplicate_ids_and_fixed_noise_change():
    region = Region(37.8, -122.4, 400, 400)
    rows = _observations(region)
    with pytest.raises(ValueError, match="duplicate"):
        infer_sparse_scan_position((rows[0], rows[0]), region=region)
    with pytest.raises(ValueError, match="bounds"):
        SparseScanPositionConfig(measurement_sigma_hz=100)


def test_evaluation_is_computed_only_after_position_search(monkeypatch):
    region = Region(37.8, -122.4, 400, 400)
    original = subject._score_grid
    evaluation_calls = []

    def check(receiver, training, evaluation):
        if evaluation:
            evaluation_calls.append(len(receiver))
        return original(receiver, training, evaluation)

    monkeypatch.setattr(subject, "_score_grid", check)
    result = infer_sparse_scan_position(_observations(region), region=region)
    assert result.state == "complete"
    assert evaluation_calls == [1]


def test_missing_evaluation_support_is_an_explicit_insufficiency():
    region = Region(37.8, -122.4, 400, 400)
    rows = tuple(replace(row, training=True) for row in _observations(region))
    result = infer_sparse_scan_position(rows, region=region)
    assert result.state == "insufficient"
    assert "no-evaluation-support" in result.reasons
    assert result.latitude_deg is None
