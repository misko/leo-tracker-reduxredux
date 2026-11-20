from importlib import import_module

import pytest

scoring = import_module("reports.2026_11_18_v5_blind_comparison.summarize")
replay = import_module("reports.2026_11_18_v5_blind_comparison.run_grid_panel")


def test_coverages_and_distances_have_separate_denominators():
    rows = [dict(status="fix", error_km=1.0), dict(status="fix", error_km=9.0),
            dict(status="withheld", error_km=None)]
    stats = scoring.summarize_group(rows)
    assert stats["attempts"] == 3 and stats["error_km"]["n"] == 2
    assert stats["error_km"]["p50"] == 5 and stats["within_km"]["5"] == 1
    empty = scoring.summarize_group([dict(status="withheld", error_km=None)])
    assert empty["error_km"]["p95"] is None and empty["numerical_outputs"] == 0


def test_paired_comparison_requires_same_case_and_two_coordinates():
    rows = []
    for case, legacy, grid in [("a", 9, None), ("b", 2, 3), ("c", 3, 1)]:
        for m, a, e in [("v5", "fitted_c", legacy), ("receiver", "shape", grid)]:
            rows.append(dict(case=case, method=m, arm=a, condition="present", error_km=e))
    test = scoring.paired(rows, "v5", "fitted_c", "receiver", "shape")
    assert test["common_cases"] == ["b", "c"]
    assert test["right_closer"] == 1 and test["right_minus_left_km"]["p50"] == -.5


def test_calibration_reports_same_observation_residuals_separately():
    rows = [
        dict(case="a", method="v5", condition="present", arm="c0", error_km=2.0,
             rms_hz=50.0, matched_rms_hz=45.0),
        dict(case="a", method="v5", condition="present", arm="fitted_c", error_km=3.0,
             rms_hz=40.0, matched_rms_hz=42.0),
    ]
    pair = scoring.paired(rows, "v5", "c0", "v5", "fitted_c")
    assert pair["paired_selected_rms_change_hz"]["p50"] == -10.0
    assert pair["paired_same_observation_rms_change_hz"]["p50"] == -3.0
    assert pair["right_minus_left_km"]["p50"] == 1.0


def test_ds26_four_regions_retain_original_prior_and_fixed_radial_offsets():
    center = [37.906, -122.545]
    for case in ["DS26-0002", "DS26-0311"]:
        regions = replay.offers(center, case)
        assert regions == replay.offers(center, case)
        assert regions["one"] == [dict(id="original", center=center)]
        distances = (scoring.field_score.distance_km(center, r["center"]) for r in regions["four"])
        radii = sorted(distances)
        assert radii == pytest.approx([0, 45, 65, 250], abs=1e-8)
