import importlib

import numpy as np

audit = importlib.import_module("reports.ALGO08.single-core-2x.solver_bound_repeat_audit")


def test_complete_numeric_signature_distinguishes_options_layout_and_mutation():
    matrix = np.arange(12., dtype=np.float64).reshape(4, 3)
    ordinary = audit.full_key([matrix, np.float64(1e-12), "ordinary"])[0]
    assert ordinary == audit.full_key([matrix.copy(), np.float64(1e-12), "ordinary"])[0]
    assert ordinary != audit.full_key([matrix.copy(order="F"), 1e-12, "ordinary"])[0]
    assert ordinary != audit.full_key([matrix.copy(), 1e-10, "ordinary"])[0]
    assert ordinary != audit.full_key([matrix.copy(), 1e-12, "posterior"])[0]
    matrix[0, 0] = -0.0
    assert ordinary != audit.full_key([matrix, 1e-12, "ordinary"])[0]


def test_reuse_bound_keeps_grid_export_out_of_ordinary_lru():
    base = dict(cpu_ns=50, witness_bytes=20, raw_fingerprint_ns=3, normalized_fingerprint_ns=4,
                hint_ns=1, hint="cheap", result_key="unchanged", caller="normal.py", model=0)
    rows = [
        dict(base, raw_key="a", normalized_key="a", mode="ordinary", stage="initial"),
        dict(base, raw_key="b", normalized_key="b", mode="ordinary", stage="conservative"),
        dict(base, raw_key="grid", normalized_key="grid", mode="grid-export", stage="grid"),
        dict(base, raw_key="a", normalized_key="a", mode="ordinary", stage="family", model=1),
    ]
    assert audit.simulate(rows, 20)["hits"] == 0
    assert audit.simulate(rows, 40)["hits"] == 1
    assert audit.simulate(rows, 40)["gross_avoided_cpu_ns"] == 50
    summary = audit.summarize(rows)
    assert summary["boundaries"]["ordinary"]["raw_key_repeats"] == 1
    assert summary["repeats_by_stage"]["initial → family"]["different_model"] == 1
