import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from traced_search import hierarchical_search as traced

from leo.analysis.regional_position_search import hierarchical_search


@pytest.mark.parametrize("radius,budget", [(50, 20), (200, 400), (250, 400)])
@pytest.mark.parametrize("flat", [False, True])
def test_production_order_scores_and_deferred_parity(radius, budget, flat):
    def score(e, n):
        return 3.0 if flat else (e - 71) ** 2 + (n + 19) ** 2

    options = dict(
        radius_km=radius,
        budget_points=budget,
        levels_km=(40.0, 20.0, 10.0, 5.0),
        edge_priority="nearest",
    )
    events = []
    a = hierarchical_search(score, **options)
    b = traced(score, **options, observer=events.append)
    assert a == b
    assert len(events[-2]["cells"]) == a.deferred_cells
    assert len(events[-1]["rows"]) == len(a.evaluations)
    assert any(e["event"] == "child" for e in events)
