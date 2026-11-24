import pytest

from reports.ALGO08.v3 import ds30_0359_combined as held
from reports.ALGO08.v3.ds30_0173_combined import pool_cases


def test_rank_six_keeps_its_frozen_release_case_and_cutoff():
    row = held.assigned()
    assert (row["case"], row["rank"], row["roster_size"]) == ("DS30-0359", 6, 87)
    assert row["release_pair_sha256"] == held.PAIR_PIN
    assert row["order"] == ["routed", "installed"]
    with pytest.raises(ValueError, match="enrolled input"):
        held.staged_archive(0, held.INPUTS["cutoff_utc_ns"] + 1, held.INPUTS["archive_sha256"])


def test_three_case_reduction_keeps_the_unfavorable_and_withheld_pair():
    def row(label, time, decision, delta, setup):
        return dict(
            case=label, admission=dict(sources={"science": "same"}, actual_worker_order=["installed", "routed"]),
            jobs=dict(installed={"decision": "complete"}, routed={"decision": decision}),
            time={name: dict(installed=10, routed=time) for name in ("elapsed_s", "cpu_s")},
            paid_setup_and_time={name: dict(combined_setup=setup, failed_start=0.)
                                 for name in ("elapsed_s", "cpu_s")},
            candidate_minus_installed_horizontal_m={"c0": delta, "fitted_c": delta},
        )

    rows = (row("DS30-0163", 4., "complete", -2., 1.),
            row("DS30-0173", 8., "complete", 5., 1.),
            row("DS30-0359", 12., "withheld", None, 1.))
    result = pool_cases(rows, ("DS30-0163", "DS30-0173", "DS30-0359"))
    assert result["enrolled_cases"] == result["clock_pairs"] == 3
    assert result["fixes"] == {"installed": 3, "routed": 2}
    assert result["withholds"] == {"installed": 0, "routed": 1}
    assert result["comparable_position_pairs"] == {"c0": 2, "fitted_c": 2}
    assert result["candidate_minus_installed_horizontal_m"]["DS30-0173"]["fitted_c"] == 5.
    timing = result["timing"]["elapsed_s"]
    assert timing["worker"]["summed_speedup"] == pytest.approx(30 / 24)
    assert timing["worker"]["reciprocal_median_ratio"] == pytest.approx(1 / .8)
    assert timing["admission_charged"]["summed_speedup"] == pytest.approx(33 / 27)
