import json
import math
import time
from types import SimpleNamespace

import numpy as np
import paired_rx_grouped_width as grouped_width
import paired_rx_width_diagnostic as original_width


def _family_receipt():
    families = []
    representatives = []
    for family_index, (rows, representative) in enumerate(
        [([0, 1], 1), ([2, 3], 2)]
    ):
        member_ids = [f"candidate-{row}" for row in rows]
        representative_id = f"candidate-{representative}"
        families.append(
            {
                "representative_candidate_id": representative_id,
                "member_candidate_ids": member_ids,
                "probe_key": ["capture", family_index],
                "lineage": [
                    {"candidate_id": candidate_id, "input_row_index": row}
                    for candidate_id, row in zip(member_ids, rows, strict=True)
                ],
            }
        )
        representatives.append({"candidate_id": representative_id})
    return {
        "schema": "alias-family-capture-export/v1",
        "dataset": "DS10",
        "session_id": "capture",
        "selected_unit_ids": ["DS10-S01"],
        "accounting": {"raw_row_count": 4, "grouped_family_count": 2},
        "representative_original_indices": [1, 2],
        "geometry": {
            "source_row_count": 4,
            "representative_row_count": 2,
            "source_group_count": 2,
            "representative_group_count": 2,
            "all_source_groups_preserved": True,
        },
        "grouping": {"families": families, "representative_rows": representatives},
    }


def test_grouped_layout_freezes_full_group_median_before_filtering_without_mutation():
    source = SimpleNamespace(
        session_id="capture",
        dataset="DS10",
        times=np.array([0.0, 2.0, 10.0, 14.0]),
        measured=np.array([100.0, 101.0, 200.0, 201.0]),
        rf=np.full(4, 11e9),
        receiver=np.array([0, 0, 1, 1]),
        channel=np.ones(4, dtype=int),
        group=np.array([7, 7, 8, 8]),
        margin=np.array([0.1, 0.2, 0.3, 0.4]),
    )
    original_times = source.times.copy()

    reduced, representatives = grouped_width.grouped_layout(
        source, _family_receipt()
    )

    np.testing.assert_array_equal(representatives, [1, 2])
    np.testing.assert_allclose(reduced.times, [1.0, 12.0])
    np.testing.assert_allclose(reduced.measured, [101.0, 200.0])
    np.testing.assert_array_equal(np.unique(reduced.group), [7, 8])
    np.testing.assert_array_equal(source.times, original_times)


def _synthetic_case(sigma_hz=260.0, count=8000, seed=4):
    rng = np.random.default_rng(seed)
    differences = rng.normal(0.0, sigma_hz, count)
    return original_width.ScoredDifferenceGroups(
        unit_id="synthetic",
        dataset="DS10",
        times=np.arange(count, dtype=float),
        starts=np.arange(count),
        counts=np.ones(count, dtype=int),
        differences=differences,
        weights=np.ones(count),
        margins=np.full(count, 0.5),
        model=np.zeros(count),
        pairing={},
    )


def test_scalar_fit_has_one_parameter_and_recovers_normalized_difference_width():
    result = grouped_width.fit_scalar_width(
        [_synthetic_case()],
        initial_sigma_hz=116.0,
        deadline=time.monotonic() + 10.0,
    )

    assert result["success"]
    assert result["parameter_count"] == 1
    assert abs(result["sigma_difference_hz"] - 260.0) < 12.0
    assert np.isclose(
        result["implied_equal_independent_per_receiver_sigma_hz"],
        result["sigma_difference_hz"] / math.sqrt(2.0),
    )
    assert result["bounds_hz"] == [100.0, 3000.0]


def test_scalar_fit_retains_lower_bound_instead_of_inventing_narrower_width():
    result = grouped_width.fit_scalar_width(
        [_synthetic_case(sigma_hz=20.0)],
        initial_sigma_hz=116.0,
        deadline=time.monotonic() + 10.0,
    )

    assert result["at_lower_bound"]
    assert np.isclose(result["sigma_difference_hz"], 100.0, atol=1e-7)


def _status(unit_id, pair_count, alternatives):
    return {
        "unit_id": unit_id,
        "dataset": "DS10",
        "paired_group_count": pair_count,
        "difference_alternative_count": alternatives,
    }


def test_comparison_requires_same_pair_counts_and_never_compares_cross_input_nll():
    case = _synthetic_case(count=30)
    status = _status("synthetic", 30, 30)
    original = {
        "synthetic": {
            "pair_count": 30,
            "difference_alternative_count": 60,
        }
    }
    fitted = {
        "sigma_difference_hz": 100.0,
        "implied_equal_independent_per_receiver_sigma_hz": 100.0 / math.sqrt(2),
        "negative_log_likelihood": 10.0,
    }

    receipt = grouped_width.comparison_receipt(
        [case], [status], original, 116.0, fitted
    )

    assert receipt["paired_group_counts_unchanged"]
    assert receipt["cross_input_nll_comparison_valid"] is False
    assert receipt["original_ungrouped"]["difference_alternative_count"] == 60
    assert receipt["alias_grouped"]["difference_alternative_count"] == 30
    assert status["paired_group_count_unchanged"]
    assert status["original_difference_alternative_count"] == 60

    bad_status = _status("synthetic", 29, 30)
    with np.testing.assert_raises_regex(ValueError, "counts differ"):
        grouped_width.comparison_receipt(
            [case], [bad_status], original, 116.0, fitted
        )


def test_export_loader_parses_only_requested_capture(tmp_path):
    requested = tmp_path / "requested.json"
    unrequested = tmp_path / "unrequested.json"
    receipt = {
        "schema": "alias-family-capture-export/v1",
        "sealed": True,
        "session_id": "requested",
        "dataset": "DS10",
        "accounting": {"raw_row_count": 4, "grouped_family_count": 2},
    }
    requested.write_text(json.dumps(receipt))
    unrequested.write_text("not JSON")
    cohort = {
        "records_by_session": {
            "requested": {
                "session_id": "requested",
                "dataset": "DS10",
                "sha256": grouped_width.digest(requested),
                "raw_row_count": 4,
                "grouped_family_count": 2,
            },
            "unrequested": {
                "session_id": "unrequested",
                "dataset": "DS10",
                "sha256": grouped_width.digest(unrequested),
                "raw_row_count": 1,
                "grouped_family_count": 1,
            },
        },
        "receipt_paths": {
            "requested": requested,
            "unrequested": unrequested,
        },
    }

    loaded, path, receipt_sha256 = grouped_width._load_export_receipt(
        cohort, "requested"
    )

    assert loaded == receipt
    assert path == requested
    assert receipt_sha256 == grouped_width.digest(requested)
