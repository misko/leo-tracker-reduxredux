import pytest

from reports.ALGO08.v3.field_first71_deficit import loss_class, minimum_scope, quartiles, stats


def arm(case, wall, cpu=None):
    return dict(case=case, elapsed_s=wall, cpu_s=wall if cpu is None else cpu)


def test_paid_clock_surplus_offsets_deficit_and_half_gates_are_independent():
    pairs = [(arm("a", 10), arm("a", 7, 4)), (arm("b", 10), arm("b", 4, 6)),
             (arm("c", 10), arm("c", 5, 5))]
    result = stats(pairs)
    assert result["wall"]["positive"] == 2
    assert result["wall"]["surplus"] == 1
    assert result["wall"]["net"] == 1
    assert result["wall"]["at_half"] == result["cpu"]["at_half"] == 2
    assert result["at_both_halves"] == 1


def test_quartile_strata_use_only_installed_wall_and_keep_all_pairs():
    pairs = [(arm(str(i), i+1), arm(str(i), 9-i)) for i in reversed(range(9))]
    assert [[a["case"] for a, _ in group] for group in quartiles(pairs)] == [
        ["0", "1"], ["2", "3"], ["4", "5"], ["6", "7", "8"]]


def test_geographic_strata_distinguish_crossing_from_missing_score():
    assert loss_class(1, 1.001) == "lost"
    assert loss_class(1.001, 1) == "gained"
    assert loss_class(1, 1) == "both_pass"
    assert loss_class(1.001, 1.001) == "neither_pass"
    assert loss_class(None, .8) == loss_class(.8, None) == "unscored"


def test_scope_charged_to_audited_arms_only_and_two_gates_cross_separately():
    pairs = [(arm("a", 20), arm("a", 9)), (arm("b", 20), arm("b", 12)),
             (arm("c", 20), arm("c", 13))]
    result = minimum_scope(pairs, {"b": 4})
    assert result["first_fraction_sum"] == pytest.approx(1.)
    assert result["first_fraction_median"] == pytest.approx(.5)
    assert result["at_half_if_free"] == 2
    assert minimum_scope(pairs, {"a": 2})["first_fraction_median"] is None
