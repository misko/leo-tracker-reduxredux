import json

import pytest

from tools.pipeline_eval.qualification.peak_null_audit import (
    effective_exported_slots,
    synthetic_controls,
    synthetic_probe,
)
from tools.pipeline_eval.qualification.peak_null_recover import UNIT, timeout_receipt
from tools.pipeline_eval.qualification.peak_null_trial import exchanged_controls
from tools.pipeline_eval.variants.peak_null import MIN_VISITS, adjusted_document


def document(probes):
    return dict(source=dict(probes=probes))


def test_rolled_controls_rerank_without_editing_fields_or_dropping_support():
    prefix = [synthetic_probe(visit, [0.07], [0.04]) for visit in range(MIN_VISITS)]
    target = synthetic_probe(MIN_VISITS, [0.34, 0.25, 0.03, 0.21], [0.12, 0.04, 0.02, 0.04])
    transformed, counts, floors, changed = adjusted_document(document([*prefix, target]))
    assert floors == [0.04]
    assert transformed["source"]["probes"][:-1] == prefix
    assert transformed["source"]["probes"][-1]["candidates"] == target["candidates"][1:]
    assert counts["positive_probes"] == MIN_VISITS + 1
    assert counts["original_passing"] - counts["adjusted_passing"] == 1
    assert changed[0]["new_rank"] == 1


def test_prefix_calibration_uses_only_prior_distinct_visits_in_the_lane():
    early = [synthetic_probe(visit, [0.07], [0.04]) for visit in range(MIN_VISITS)]
    target = synthetic_probe(MIN_VISITS, [0.38, 0.30], [0.12, 0.05])
    injected = synthetic_probe(MIN_VISITS, [0.01], [0.6])
    new_lane = dict(target, receiver_id=1)
    prefix, _, _, _ = adjusted_document(document([*early, target]))
    after, _, floors, _ = adjusted_document(document([*early, target, injected, new_lane]))
    assert after["source"]["probes"][:-2] == prefix["source"]["probes"]
    assert after["source"]["probes"][-1] == new_lane
    assert floors == [0.04, 0.04]
    repeated = [synthetic_probe(0, [0.07], [0.04]) for _ in early]
    assert adjusted_document(document([*repeated, target]))[1]["changed_winner"] == 0


def test_zero_plant_and_score_exchange_do_not_create_positives():
    result = synthetic_controls([0.03, 0.04, 0.05, 0.1], n=64)
    assert result["zero"]["stock_gate_positive"] == result["zero"]["adjusted_gate_positive"] == 0
    assert (
        result["exchangeable"]["stock_gate_positive"]
        == result["exchangeable"]["adjusted_gate_positive"]
    )
    assert result["planted"]["planted_top1_stock"] == 64
    assert result["planted"]["planted_top1_adjusted"] == 58
    rows = [synthetic_probe(i, [0.09], [0.01 * i]) for i in range(4)]
    assert exchanged_controls(document(rows)) == [[0.02], [0.03], [0.0], [0.01]]


def test_quarantines_non_native_statistics():
    bad = synthetic_probe(0, [0.09], [0.01])
    bad["candidates"][0]["fractional_margin"] = 0.5
    with pytest.raises(ValueError, match="fractional pilot statistic"):
        adjusted_document(document([bad]))


def test_perfectly_dependent_exported_controls_count_as_one_at_the_tail():
    visits = [synthetic_probe(i, [i / 100] * 4, [i / 100] * 4)["candidates"] for i in range(100)]
    assert effective_exported_slots(visits)["effective_exported_slots_at_q95"] == 1.0


def test_timeout_recovery_requires_empty_stdout_and_a_supervisor_deadline():
    supervisor = dict(
        ActiveEnterTimestampMonotonic="2000000",
        ActiveExitTimestampMonotonic="167020000",
        Result="timeout",
    )
    transcript = "proof " + json.dumps(dict(cpu=11, cgroup=f"/scope/{UNIT}"))
    recovered = timeout_receipt({"id": "example"}, supervisor, transcript, 0, 165, 11)
    assert recovered["result"]["status"] == "timed_out"
    assert recovered["result"]["arms"] == {"c0": {"latlon": None}, "fitted_c": {"latlon": None}}
    with pytest.raises(ValueError, match="returned output"):
        timeout_receipt({"id": "example"}, supervisor, transcript, 1, 165, 11)
