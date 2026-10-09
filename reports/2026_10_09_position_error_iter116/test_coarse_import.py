import copy
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from coarse_import import ImportedEvaluator, pre_recovery_trace, snapshot, validate_receipt
from test_adapter import fixture

from leo.analysis.regional_position_fit import PositionFit
from leo.application.regional_position_runner import json_value


def sample():
    obs, bank, model, vector = fixture()
    fit = PositionFit(vector.copy(), 7.0, 10.0, 4.0, 0.0001, True, False, "qualified", 3, 0.1)
    receipt = dict(
        reason=None,
        result=dict(
            bootstrap=dict(satellite_indices=[1, 3], vector=vector.tolist(), matches=[]),
            fits={"V16": dict(fit=json_value(fit), reason=None)},
        ),
    )
    doc = dict(
        session_id="synthetic",
        configuration=dict(run={}),
        diagnostics=dict(bank=dict(retained_numbers=bank.numbers.tolist())),
        methods=[dict(points=[dict(east_km=0.0, north_km=0.0, spacing_km=40.0, score=7.0)])],
    )
    return obs, bank, model, vector, receipt, doc


def test_exact_imported_fit_and_seed_shared_with_zero_c():
    obs, bank, model, vector, receipt, doc = sample()
    imported = snapshot(doc, lambda key: receipt)
    calls = []

    def fit(model, seed, **options):
        calls.append(seed.copy())
        seed[6] = 0
        return PositionFit(seed, 7.0, 10.0, 4.0, 0.0, True, False, "qualified", 3, 0.1)

    def scorer(model, v, full, expected):
        assert expected == 7.0
        return {m: dict(objective=7.0) for m in ("native", "fixed")}

    evaluator = ImportedEvaluator(
        obs, bank, model.prior, [], imported=imported, fitter=fit, scorer=scorer
    )
    a = evaluator(0, 0, "fitted-c")
    assert a["fit"] == receipt["result"]["fits"]["V16"]["fit"]
    assert not calls
    evaluator(0, 0, "zero-c")
    np.testing.assert_array_equal(calls[0], vector)


def test_changed_vector_bank_clock_block_and_trace_rejected():
    obs, bank, model, _, receipt, doc = sample()
    imported = snapshot(doc, lambda key: receipt)
    bad = copy.deepcopy(imported)
    bad["records"][0]["receipt"]["result"]["fits"]["V16"]["fit"]["vector"][2] += 1
    with pytest.raises(ValueError, match="changed imported"):
        ImportedEvaluator(obs, bank, model.prior, [], imported=bad)
    bad = copy.deepcopy(imported)
    bad["bank_numbers"].reverse()
    with pytest.raises(ValueError, match="mapping"):
        ImportedEvaluator(obs, bank, model.prior, [], imported=bad)
    bad = copy.deepcopy(receipt)
    bad["result"]["fits"]["V16"]["fit"]["clock_coefficients"] = [0]
    with pytest.raises(ValueError, match="clock"):
        validate_receipt(bad, [0, 0], 4)
    doc["methods"][0]["points"][0]["score"] = 8
    with pytest.raises(ValueError, match="native score"):
        snapshot(doc, lambda key: receipt)


def test_original_failed_receipt_preserved_without_replacement():
    obs, bank, model, _, _, doc = sample()
    imported = snapshot(doc, lambda key: dict(reason="timeout", result=None))
    assert len(imported["records"]) == 1
    evaluator = ImportedEvaluator(
        obs,
        bank,
        model.prior,
        [],
        imported=imported,
        bootstrap=lambda *a, **k: pytest.fail("replacement seed"),
        fitter=lambda *a, **k: pytest.fail("replacement fit"),
    )
    assert evaluator.original_failure((0.0, 0.0))
    with pytest.raises(ValueError, match="failure preserved"):
        evaluator(0, 0, "fitted-c")


def test_postsearch_scores_restored_and_original_fit_digest_bound():
    _, _, _, _, receipt, doc = sample()
    original = receipt["result"]["fits"]["V16"]["fit"]
    shown = copy.deepcopy(receipt)
    shown["result"]["fits"]["V16"]["fit"]["objective"] = 6
    regional = dict(
        searches={"V16": dict(evaluations=[dict(east_km=0, north_km=0, spacing_km=40, score=6)])},
        points={"point:0:0": shown},
        recovery=dict(coarse=[dict(point="point:0:0", original=original)]),
    )
    trace, fits, changes = pre_recovery_trace(regional)
    assert trace[0]["score"] == 7 and changes[0]["delta_displayed_minus_original"] == -1
    assert regional["searches"]["V16"]["evaluations"][0]["score"] == 6
    imported = snapshot(doc, lambda key: receipt, baseline_trace=trace, original_fits=fits)
    assert imported["native_baseline"][0]["score"] == 7
    bad = copy.deepcopy(receipt)
    bad["result"]["fits"]["V16"]["fit"]["vector"][2] += 1
    with pytest.raises(ValueError, match="original recovery fit"):
        snapshot(doc, lambda key: bad, baseline_trace=trace, original_fits=fits)


@pytest.mark.parametrize("coordinate,value", [(3, 61), (7, 11), (8, 100)])
def test_infeasible_imported_physical_state_rejected(coordinate, value):
    *_, receipt, _ = sample()
    receipt["result"]["fits"]["V16"]["fit"]["vector"][coordinate] = value
    with pytest.raises(ValueError, match="physical constraints"):
        validate_receipt(receipt, [0, 0], 4)
