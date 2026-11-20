import pytest

from tools.pipeline_eval.qualification import screening_figures, transfer_budget
from tools.pipeline_eval.scoring import ARMS
from tools.pipeline_eval.variants.transfer_budget import admits_recovery


@pytest.mark.parametrize(
    ("accepted", "total", "admitted"),
    [
        (0, 0, False),
        (49, 100, False),
        (50, 100, False),
        (51, 100, True),
        (51, 101, True),
        (100, 100, True),
    ],
)
def test_recovery_needs_strict_majority_of_original_nominated_support(accepted, total, admitted):
    assert admits_recovery(dict(accepted_points=accepted, tracked_points=total)) is admitted


def test_transfer_figure_scopes_and_paired_roster_are_kept():
    studies = {
        chart.id: chart for chart in screening_figures.charts(evidence=transfer_budget.REPORT)
    }
    for name, count in (("fresh", 3), ("development", 4), ("measured", 1)):
        chart = studies[f"compact-recovery-budget-{name}"]
        assert len(chart.cases) == count
        for arm in ARMS:
            for key in ("candidate", "stock"):
                rows = [row for row in chart.page(arm).rows if row.series == key]
                assert len(rows) == count
                assert all(r.error_km is None for r in rows if r.decision != "published")
