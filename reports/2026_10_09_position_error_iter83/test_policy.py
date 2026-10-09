from policy import endpoint_sources, needs_extra_search, retry_inventory, winner


def row(index, arm, objective, converged=True):
    return dict(index=index, order=0, arm=arm,
                fit=dict(objective=objective, converged=converged))


def test_timing_trigger_ignores_error_and_flags_either_arm():
    fit = dict(vector=[0] * 8 + [1, -1], converged=True, error_km=999)
    fits = {arm: dict(fit) for arm in ("fitted-c", "zero-c")}
    assert not needs_extra_search(fits)
    fits["zero-c"]["vector"] = [0] * 8 + [7, -7]
    assert needs_extra_search(fits)
    assert needs_extra_search({})


def test_retry_preserves_gate_and_supports_no_qualified_arm():
    rows = [row(0, "fitted-c", 10), row(1, "fitted-c", 9, False),
            row(2, "zero-c", 8, False), row(3, "zero-c", 7, False)]
    assert winner(rows, "fitted-c")["index"] == 0
    assert winner(rows, "zero-c") is None
    assert [r["index"] for r in retry_inventory(rows)] == [0, 1, 3]


def test_nonfinite_scores_never_win_or_seed_retry():
    rows = [row(0, "fitted-c", float("nan")), row(1, "zero-c", float("inf"), False)]
    assert retry_inventory(rows) == []


def test_preserve_regions_and_source_types_without_score_pruning():
    rows = [dict(region=0, start="association", status="infeasible"),
            dict(region=0, start="association", status="feasible", error_km=999),
            dict(region=0, start="association", status="feasible", error_km=0),
            dict(region=1, start="zero-timing", status="feasible", error_km=999),
            dict(region=1, start="own-continuation", status="feasible", error_km=0)]
    assert endpoint_sources(rows) == [1, 3]
