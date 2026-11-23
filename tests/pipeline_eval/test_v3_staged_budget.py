from math import isclose

import pytest

from reports.ALGO08.v3.staged_budget import acquisition_allowance, gates, observed, stage_rows


def test_binding_timing_gate_depends_on_duration_mix():
    stages = [(90, 10, 0), (90, 10, 0), (100, 900, 0)]
    # The two short recordings set the median, the long one sets the summed gate.
    assert acquisition_allowance(stages, 1) is None
    assert acquisition_allowance(stages, 0) == pytest.approx(50/90)
    both = gates(stages, acquisition_allowance(stages, .4), .4)
    assert max(both) == pytest.approx(.5)
    assert min(both) < .5


def test_incomplete_clock_and_duplicate_input_fail():
    case = dict(rank=1, case="A", raw_authority="one")
    clock = dict(launch_to_detections_s=1, detections_to_terminal_s=2, terminal_to_exit_s=3, elapsed_s=6)
    with pytest.raises(ValueError, match="Incomplete"):
        stage_rows([case], {})
    with pytest.raises(ValueError, match="Repeated"):
        stage_rows([case, dict(case, rank=2)], {"A": clock})
    with pytest.raises(ValueError, match="disagree"):
        stage_rows([case], {"A": dict(clock, elapsed_s=7)})


def test_both_physical_pairs_are_individually_scored_against_site_reference():
    rows = observed()
    assert len(rows) == 4
    for stock, candidate in (rows[:2], rows[2:]):
        assert stock["case"] == candidate["case"]
        assert stock["baseline"] and not candidate["baseline"]
        assert stock["errors_km"] == candidate["errors_km"]
        assert candidate["elapsed_s"] > stock["elapsed_s"]
    assert isclose(rows[0]["errors_km"]["fitted_c"], 1.93537, abs_tol=1.e-5)
