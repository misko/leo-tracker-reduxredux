"""Pre-outcome sampling and conservative batch-control invariants."""

from types import SimpleNamespace

import numpy as np
import pytest
import run_algo01_ds23_sample as module


def test_sample_is_uniform_draw_without_replacement_and_order_invariant():
    rows = [dict(dataset_label=f"DS23-{i:04d}") for i in range(100)]
    selected = module.sample_members(rows)
    assert len(selected) == len({m["dataset_label"] for m in selected}) == 20
    assert selected == module.sample_members(rows[::-1])
    with pytest.raises(ValueError):
        module.sample_members(rows[:19])


def test_salvage_supports_never_admit_short_or_interior_only_children():
    assert module.selected_supports(11) == []
    assert module.selected_supports(12) == [(0, 12)]
    supports = module.selected_supports(48)
    assert (12, 48) in supports and (0, 48) in supports
    assert all(b - a >= 12 and (a == 0 or b == 48) for a, b in supports)


def test_either_c_arm_can_reject_but_both_are_refit_on_the_identical_mask(monkeypatch):
    import audit_ds23_algo01_coverage as audit

    calls = []
    scan = SimpleNamespace(case="synthetic")
    p = SimpleNamespace(
        rows=[dict(component="a"), dict(component="b")], slices=[slice(0, 4), slice(4, 8)]
    )

    def fitted(scan, node, keep, arm):
        calls.append((arm, keep.copy()))
        return p, dict(fit=dict(parameters=arm))

    def metrics(p, arm):
        first_round = len(calls) <= 2
        return dict(
            tracks=[
                dict(component="a", compatible=True),
                dict(component="b", compatible=not (first_round and arm == "fitted_c")),
            ]
        )

    monkeypatch.setattr(module, "causal_fit", fitted)
    monkeypatch.setattr(audit, "retained_metrics", metrics)
    _, keep, _, history, stable = module.fit_and_gate(scan, {}, np.ones(8, bool), "test")
    assert stable and len(history) == 2
    assert keep.tolist() == [True] * 4 + [False] * 4
    assert len(calls) == 4
    np.testing.assert_array_equal(calls[0][1], calls[1][1])
    np.testing.assert_array_equal(calls[2][1], calls[3][1])
