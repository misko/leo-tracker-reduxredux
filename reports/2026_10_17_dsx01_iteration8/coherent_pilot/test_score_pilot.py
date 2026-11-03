"""Denominator, held gate and durable-seal regression tests; no corpus reads."""

import numpy as np
import pytest
import score_pilot as evaluation


def test_metrics_keep_losses_and_exact_residual_intersection():
    baseline = dict(
        associated=np.array([1, 1, 0, 0], bool),
        residual_hz=np.array([3.0, 4.0, 100.0, 100.0]),
        row_nll=np.ones(4),
    )
    new = dict(
        associated=np.array([1, 0, 1, 0], bool),
        residual_hz=np.array([2.0, 100.0, 5.0, 100.0]),
        row_nll=np.full(4, 2.0),
    )
    m = evaluation.metrics(np.ones(4, bool), new, baseline)
    assert (m["observations"], m["associated"], m["new"], m["lost"], m["retained"]) == (
        4,
        2,
        1,
        1,
        1,
    )
    assert m["intersection_baseline_rms_hz"] == 3
    assert m["intersection_current_rms_hz"] == 2
    assert m["nll"] == 8


def test_gate_requires_strict_both_counts_and_four_of_exact_seven():
    def row(nll, count):
        return dict(
            audit=dict(accepted=True),
            new_singleton=dict(held=dict(nll=nll)),
            original_shared=dict(
                held=dict(associated=count), requested_held=dict(associated=count)
            ),
        )

    old, new = row(100, 10), row(99, 10)
    results = {"independent_fitted-c": old, "automatic_fitted-c": new}
    blocks = [dict(arm="fitted-c", delta_new_singleton_nll=-1 if i < 4 else 0.2) for i in range(7)]
    assert evaluation.broadening_gate(results, blocks)["passed"]
    new["audit"]["accepted"] = False
    assert not evaluation.broadening_gate(results, blocks)["passed"]
    new["audit"]["accepted"] = True
    new["original_shared"]["requested_held"]["associated"] = 9
    assert not evaluation.broadening_gate(results, blocks)["passed"]


def test_missing_seal_stops_before_measurement_read(tmp_path):
    with pytest.raises(FileNotFoundError):
        list(evaluation.sealed_rows(tmp_path, "predictions_seal.json", "predictions"))


def test_seal_requires_complete_inventory_and_unchanged_file_bytes(tmp_path):
    source = evaluation.source
    rows = []
    for case in evaluation.CASES:
        path = tmp_path / (case + ".json")
        source.save(path, dict(case=case))
        rows.append(dict(case=case, path=path.name, sha256=source.digest(path)))
    source.save(tmp_path / "good.json", dict(all_four_sealed=True, predictions=rows))
    assert len(list(evaluation.sealed_rows(tmp_path, "good.json", "predictions"))) == 4
    source.save(tmp_path / "missing.json", dict(all_four_sealed=True, predictions=rows[:-1]))
    with pytest.raises(ValueError, match="four-case"):
        list(evaluation.sealed_rows(tmp_path, "missing.json", "predictions"))
    (tmp_path / rows[0]["path"]).write_text("changed bytes")
    with pytest.raises(ValueError, match="changed"):
        list(evaluation.sealed_rows(tmp_path, "good.json", "predictions"))
