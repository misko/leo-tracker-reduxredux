from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from satellite_set_transfer import canonical, crossing, kendall, roster, set_evidence


def test_different_assignment_keys_can_preserve_the_exact_satellite_set():
    exact = set_evidence(2, 2, "old", "new", {1: 30, 2: 10}, {1: 20, 2: 25})
    assert exact["relation"] == "same"
    assert exact["gap"] == 0.
    assert set_evidence(2, 2, "old", "new")["relation"] == "unresolved"


def test_count_change_only_proves_a_lower_bound():
    partial = set_evidence(3, 2, "old", "new")
    exact = set_evidence(3, 2, "old", "new", {1, 2, 3}, {1, 4})
    assert partial["relation"] == exact["relation"] == "changed"
    assert partial["jaccard_lower_bound"] == pytest.approx(1/3)
    assert exact["gap"] == .75
    assert exact["dropped"] == [2, 3]
    assert exact["added"] == [4]


def test_owner_mapping_is_bound_before_using_norad_set():
    rows = [("a", 1, "curved"), ("b", 2, "linear")]
    detail = dict(associated_points=2, satellites=2, owner_sha256=canonical({"a": 1, "b": 2}))
    assert roster(rows, detail) == {1: 1, 2: 1}
    with pytest.raises(ValueError, match="official owner"):
        roster([("a", 2, "curved"), ("b", 1, "linear")], detail)


def test_coverage_requires_a_real_fix_and_ranking_retains_ties():
    assert crossing(None, 950, 1000) == "gain"
    assert crossing(950, None, 1000) == "loss"
    assert crossing(1500, 999, 2000) == "stable"
    assert kendall([(0, 0), (0, 1), (1, 2)])["tau_b"] == pytest.approx(2/(6**.5))
