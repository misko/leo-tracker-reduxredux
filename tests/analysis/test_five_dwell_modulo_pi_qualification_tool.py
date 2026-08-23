from __future__ import annotations

import numpy as np
import pytest

from tools import report_five_dwell_modulo_pi_qualification as report


def test_frozen_cohort_has_five_distinct_fresh_runs_and_four_paths_each() -> None:
    assert len(report.DWELLS) == 5
    assert len({item.session_id for item in report.DWELLS}) == 5
    assert len({item.run_id for item in report.DWELLS}) == 5
    assert all(item.run_id.startswith("reprocess-") for item in report.DWELLS)
    assert all(len(item.paths) == 4 for item in report.DWELLS)
    assert all(len({path.scope_digest for path in item.paths}) == 4 for item in report.DWELLS)


def test_controlled_trackers_differ_only_in_declared_symmetry_order() -> None:
    order_one = report.PilotPhaseDopplerTrackingConfig(phase_symmetry_order=1)
    order_two = report.PilotPhaseDopplerTrackingConfig(phase_symmetry_order=2)
    left = report.asdict(order_one)
    right = report.asdict(order_two)
    assert left.pop("phase_symmetry_order") == 1
    assert right.pop("phase_symmetry_order") == 2
    assert left == right


def test_wilson_interval_is_bounded_and_rejects_bad_geometry() -> None:
    low, high = report.wilson_interval(5, 5)
    assert 0 < low < high == pytest.approx(1.0)
    assert report.wilson_interval(0, 5)[0] == pytest.approx(0.0)
    with pytest.raises(ValueError):
        report.wilson_interval(1, 0)
    with pytest.raises(ValueError):
        report.wilson_interval(6, 5)


def test_showcase_uses_symmetry_contrast_not_branch_transition_count() -> None:
    rows = (
        {
            "symmetry_rms_reduction_rad": 0.1,
            "production_modulo_pi": {"phase_update_fraction": 1.0},
            "start_time_s": 1.0,
            "path_label": "many-transitions",
            "transition_count": 99,
        },
        {
            "symmetry_rms_reduction_rad": 0.4,
            "production_modulo_pi": {"phase_update_fraction": 0.9},
            "start_time_s": 2.0,
            "path_label": "larger-controlled-contrast",
            "transition_count": 0,
        },
    )
    assert report.select_showcase(rows)["path_label"] == "larger-controlled-contrast"


def test_paired_block_bootstrap_reports_positive_rms_reduction() -> None:
    modulo = np.asarray([0.1, -0.2, 0.15, -0.1] * 8)
    ordinary = np.asarray([1.0, -1.1, 0.9, -1.2] * 8)
    low, high = report.paired_block_bootstrap_interval(modulo, ordinary, seed=17, replicates=500)
    assert 0 < low <= high


def test_claim_scope_does_not_promote_phase_lock_to_satellite_identity() -> None:
    source = report._render_report(
        {
            "provenance": {
                "pipeline_release_id": report.EXPECTED_RELEASE,
                "main_revision": "main",
            },
            "method": {"bootstrap_replicates": 100},
            "totals": {
                "fully_qualified_count": 1,
                "symmetry_improved_count": 1,
                "symmetry_improved_fraction": 1.0,
                "analyzed_window_count": 1,
                "phase_lock_qualified_count": 1,
                "showcase_exact_supported_frames": 20,
                "showcase_rolled_supported_frames": 0,
                "showcase_rolled_frames": 20,
                "showcase_rolled_support_wilson_95": (0.0, 0.2),
                "maximum_reproduction_rms_error_rad": 0.0,
            },
            "dwells": [],
        }
    )
    assert "no identity claim" in source
    assert "not say the satellite physically flips phase" in source
