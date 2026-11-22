from copy import deepcopy

import numpy as np
import pytest

from tools.pipeline_eval.variants.algo08_recovery_reuse import scope


def fixture():
    mask = np.array([True, False, True])
    node = {"aliases": np.array([1., -1.]), "seed": {"labels": [4, 2]}}
    calls = []
    def operation(scan, node, keep, stage, max_rounds, **options):
        calls.append(stage)
        history = [dict(epoch=i, active_points=2, rejected_components=[]) for i in range(2)]
        return object(), mask, {"c0": "fixed", "fitted_c": "fitted"}, history, True
    counts = dict(executed_gates=0, reused_pairs=0)
    return scope(operation, counts), counts, calls, mask, node


def test_unchanged_salvage_reuses_complete_stable_pair_once():
    gate, counts, calls, mask, node = fixture()
    scan = object()
    first = gate(scan, node, np.ones(3, bool), "exclude_refit")
    second = gate(scan, deepcopy(node), mask.copy(), "salvage_refit")
    assert first[0] is second[0] and first[2] == second[2]
    assert second[3] == [dict(epoch=0, active_points=2, rejected_components=[])]
    assert first[3][-1]["epoch"] == 1
    gate(scan, node, mask, "salvage_refit")
    assert calls == ["exclude_refit", "salvage_refit"] and counts["reused_pairs"] == 1


@pytest.mark.parametrize("changed", ["region_scan", "alias", "label", "mask", "iterations", "callback"])
def test_changed_scientific_inputs_or_callbacks_repeat_both_fits(changed):
    gate, counts, calls, mask, node = fixture()
    scan = object()
    gate(scan, node, mask, "exclude_refit")
    node, mask = deepcopy(node), mask.copy()
    if changed == "region_scan":
        scan = object()
    elif changed == "alias":
        node["aliases"][0] += 1
    elif changed == "label":
        node["seed"]["labels"].reverse()
    elif changed == "mask":
        mask[1] = True
    options = {"iterations": 12} if changed == "iterations" else {}
    if changed == "callback":
        options["on_round"] = lambda *args: None
    gate(scan, node, mask, "salvage_refit", **options)
    assert calls == ["exclude_refit", "salvage_refit"] and counts["reused_pairs"] == 0
