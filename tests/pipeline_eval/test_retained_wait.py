from itertools import product
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from retained_wait import gates, projected, threshold


def test_wait_allocations_match_enumeration():
    stages = (3, 4, 2)
    for a, s in ((.25, .5), (.75, .25), (0., 0.), (1., 1.)):
        totals = [sum(w) + sum((n - i) * f for n, i, f in zip(stages, w, (a, s, 1.)))
                  for w in product(*(range(n+1) for n in stages)) if sum(w) == 4]
        assert projected(stages, 5, a, s, "best") == min(totals)
        assert projected(stages, 5, a, s, "worst") == max(totals)


def test_unsplit_failures_are_charged_and_gates_include_every_case():
    rows = [dict(stages=[100, 0, 0], cpu_s=100)] * 2 + [dict(stages=[0, 0, 50], cpu_s=30)]
    assert gates(rows, .25, 0, "worst") == (.25, .4)
    limit = threshold(rows, 0., "worst")
    assert abs(limit - .375) < 1e-10
    assert threshold(rows[2:], 0., "best") is None
