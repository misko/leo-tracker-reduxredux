import numpy as np
import pytest

import candidate_prevalence_diagnostic as diagnostic


def test_residual_classification_is_full_alias_invariant():
    alias = diagnostic.DEFAULT_ALIAS_HZ
    step = diagnostic.NATIVE_RESIDUAL_BIN_HZ
    cases = (
        (0.0, "zero"),
        (step, "plus_or_minus_one"),
        (-step, "plus_or_minus_one"),
        (253 * step, "edge"),
        (-256 * step, "edge"),
        (7 * step, "other_nonzero"),
    )
    for residual, expected in cases:
        baseline = diagnostic.classify_residual(residual)
        assert baseline[0] == expected
        for shift in range(-3, 4):
            shifted = diagnostic.classify_residual(residual + shift * alias)
            assert shifted[0] == expected
            assert shifted[1] == baseline[1]
            assert shifted[2] == pytest.approx(baseline[2], abs=1e-8)


def test_exact_join_preserves_unmatched_and_ambiguous_without_forcing():
    projected = [(0, 0, 0, 0), (1, 0, 0, 0), (2, 1, 0, 1)]
    metadata = [
        {"key": [0, 0, 0, 0], "value": "matched"},
        {"key": [1, 0, 0, 0], "value": "first"},
        {"key": [1, 0, 0, 0], "value": "second"},
        {"key": [9, 1, 0, 0], "value": "metadata-only"},
    ]
    joined, receipt = diagnostic.join_projected_metadata(projected, metadata)
    assert joined[0]["value"] == "matched"
    assert joined[1:] == [None, None]
    assert receipt["matched_row_count"] == 1
    assert receipt["ambiguous_projected_count"] == 1
    assert receipt["unmatched_projected_count"] == 1
    assert receipt["unmatched_metadata_key_count"] == 2
    assert receipt["ambiguous_metadata_key_count"] == 1
    assert receipt["forced_matches"] == 0


def test_prevalence_accounts_raw_duplicates_and_catalog_signal_mass():
    dimensions = {
        "receiver": np.array([0, 0, 1, 1]),
        "channel": np.array([1, 1, 2, 2]),
        "time_bin": np.array([0, 0, 1, 1]),
        "margin_bin": np.array([0, 1, 2, 3]),
        "rank": np.array([0, 1, 0, 1]),
        "residual_class": np.array(["zero", "zero", "edge", "plus_or_minus_one"]),
    }
    original_to_unique = np.array([0, 0, 1, 2])
    row_catalog_mass = np.array(
        [
            [0.2, 0.1],
            [0.1, 0.2],
            [0.4, 0.0],
            [0.0, 0.5],
        ]
    )
    result = diagnostic.aggregate_prevalence(
        dimensions,
        original_to_unique,
        row_catalog_mass,
        np.array([101, 202]),
    )
    assert result["row_count"] == 4
    assert result["unique_peak_count"] == 3
    assert result["deduplicated_equivalent_count"] == pytest.approx(3.0)
    assert result["total_signal_mass"] == pytest.approx(1.5)
    classes = {row["value"]: row for row in result["tables"]["residual_class"]}
    assert classes["zero"]["raw_count"] == 2
    assert classes["zero"]["deduplicated_equivalent_count"] == pytest.approx(1.0)
    assert classes["zero"]["signal_mass"] == pytest.approx(0.6)
    assert [item["signal_mass"] for item in classes["zero"]["catalog_contributions"]] == pytest.approx(
        [0.3, 0.3]
    )
    assert sum(row["raw_count"] for row in result["joint_strata"]) == 4
    assert sum(row["deduplicated_equivalent_count"] for row in result["joint_strata"]) == pytest.approx(3.0)
    assert sum(row["signal_mass"] for row in result["joint_strata"]) == pytest.approx(1.5)
