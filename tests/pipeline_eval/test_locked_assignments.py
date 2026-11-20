from types import SimpleNamespace

import pytest

from tools.pipeline_eval.qualification.locked_assignments import matching, point_map


def test_assignment_capture_retains_stock_group_alias_and_original_mask_order():
    rows = [
        dict(component="a", active_curvature=True, candidate_norad=42),
        dict(component="inactive", active_curvature=False, candidate_norad=99),
        dict(component="b", active_curvature=True, candidate_norad=17),
    ]
    scan = SimpleNamespace(
        tracks=[
            dict(key="a", observation_ids=["a0", "a1"], values=[1, 2]),
            dict(key="inactive", observation_ids=["excluded"], values=[4]),
            dict(key="b", observation_ids=["b0", "b1"], values=[9, 10]),
        ]
    )
    point = point_map(
        dict(scan=scan, keep=[False, True, True, False]),
        dict(seed={"rows": rows}, aliases=[-1, 2]),
        [dict(component="linear", norad=42, alias=-3, points=1, observation_ids=["x"])],
    )
    assert point["curved"] == {
        "a1": dict(group="a", norad=42, alias=-1, value=2.0, index=1),
        "b0": dict(group="b", norad=17, alias=2, value=9.0, index=2),
    }
    assert point["predictive"]["x"]["alias"] == -3


def row(group, satellite, *, alias=0, cfo=0.0):
    return dict(group=group, norad=satellite, alias=alias, value=cfo)


def test_matched_points_use_only_unambiguous_available_union_satellites():
    stock = {
        "a": row("a", 11),
        "b": row("a", 11),
        "c": row("b", 22),
        "d": row("b", 22),
        "e": row("c", 33),
        "f": row("d", 33),
    }
    union = {
        "a": row("A", 22, alias=1, cfo=-100.0),
        "b": row("B", 22),
        "c": row("C", 33),
        "d": row("D", 22),
        "e": row("E", 44),
        "g": row("G", 22),
    }
    keep, changed, counts = matching(stock, union, {11, 22, 33}, 100.0)
    assert keep == ["a", "b"]
    assert changed == {"a": {"stock": 11, "union": 22, "points": 2}}
    assert counts["stock_only"] == counts["union_only"] == 1
    assert counts["ambiguous_points"] == 2
    assert counts["unavailable_points"] == 1
    assert counts["common_unwrap_changed"] == 1 and counts["common_total_cfo_alias_changed"] == 0
    assert stock["a"] == row("a", 11)


def test_inconsistent_stock_group_cannot_be_frozen():
    with pytest.raises(ValueError, match="multiple stock NORADs"):
        matching(
            {"a": row("s", 11), "b": row("s", 22)},
            {"a": row("u", 33), "b": row("u", 33)},
            {11, 22, 33},
            100.0,
        )
