import pytest

from tools.report_wrapped_physical_diagnostics import paired_summary


def test_physical_probe_comparison_rejects_changed_starts_and_unmatched_locations():
    base = dict(
        input_digest="input",
        orbit_digest="orbit",
        candidate_norad=[20],
        seeds=[0],
        site={},
        phase_receipt={},
        candidate_pool_digest="pool",
        random_seed=0,
        search_plan={},
        config={"iterations": 3, "band_drift_sigma_hz_s": None},
    )
    rows = [
        dict(
            east_m=0.0,
            north_m=0.0,
            distance_m=0.0,
            arms={"zero-c": {"score": 1.0}, "fitted-c": {"score": 2.0}},
        )
    ]
    assert paired_summary(base, base, rows, rows)[0]["reference_gain"] == 0
    with pytest.raises(ValueError, match="starting states"):
        paired_summary(base, dict(base, seeds=[1]), rows, rows)
    with pytest.raises(ValueError, match="locations differ"):
        paired_summary(base, base, rows, [dict(rows[0], east_m=1.0)])
    with pytest.raises(ValueError, match="iteration budgets differ"):
        paired_summary(base, dict(base, config={"iterations": 4}), rows, rows)
    assert (
        paired_summary(
            base, dict(base, config={"iterations": 3, "band_drift_sigma_hz_s": 1.0}), rows, rows
        )[0]["reference_gain"]
        == 0
    )
