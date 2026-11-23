from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from panel_tail_ceiling import price, report


def test_optimistic_clock_keeps_solver_failures_and_the_original_denominator():
    rows = [dict(case="fix", stages=[8., 4., 2.], compressed_MB=6.),
            dict(case="missing", stages=[0., 0., 5.]), dict(case="failure", stages=[0., 0., 7.])]
    decisions = dict(fix="complete", missing="withheld", failure="solver_failed")
    assert price(rows, decisions) == (1., 1.)
    assert price(rows, decisions, (3., .5, 1.), free_tail=True, free_withdrawal=True) == pytest.approx(
        (5. / 14., 12. / 26.))


def test_actual_rosters_and_faster_prefix_still_require_dense_solve_progress():
    panels = report()
    assert [panels[k]["counts"]["withheld"] for k in ("4", "16", "55")] == [0, 0, 1]
    assert [panels[k]["counts"]["solver_failed"] for k in ("4", "16", "55")] == [0, 1, 2]
    for size in ("4", "16"):
        assert min(panels[size]["historical_oracle_gates"]) > .96
        assert all(max(p["optimistic_gates"]) > .5 for p in panels[size]["projections"])
