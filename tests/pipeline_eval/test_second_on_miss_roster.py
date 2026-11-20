import copy

import pytest

from tools.pipeline_eval.qualification.second_on_miss_roster import audit
from tools.pipeline_eval.variants.second_on_miss import project

RF = {(1, "upper"): 100, (2, "upper"): 200}


def complete_stock():
    visits = (
        (0, 1, (True, True)),
        (2, 2, (False, True)),
        (3, 1, (False, False)),
        (4, 2, (False, True)),
    )
    probes = [
        dict(
            visit_index=i,
            receiver_id=rx,
            channel=ch,
            edge="upper",
            valid_start_counter=i * 20,
            candidates=[
                dict(passed_fractional_margin_gate=flags[rx], bias=3 * rx + i),
                dict(passed_fractional_margin_gate=False, bias=i + 2),
            ],
        )
        for i, ch, flags in visits
        for rx in (0, 1)
    ]
    return dict(
        delivery_clocks=list(range(5)),
        last_sample_counter=100,
        source=dict(input_manifest_sha256="input", probes=probes),
        provenance=dict(
            window_count=5,
            processed_windows=4,
            invalid_capture=1,
            excluded_windows=[dict(visit=1)],
            detector_sha256="stock",
        ),
    )


def test_positive_visits_survive_with_full_failed_arrays_and_exact_slots():
    stock = complete_stock()
    result, dispatch = project(stock, RF)
    assert [(r["visit"], r["primary_receiver"], r["partner_required"]) for r in dispatch] == [
        (0, 0, False),
        (2, 0, True),
        (3, 1, True),
        (4, 1, False),
    ]
    receipt = audit(stock, result, dispatch, RF)
    assert receipt == dict(
        valid_visits=4,
        invalid_visits=1,
        primary_only_visits=2,
        partner_calls=2,
        positive_visits=3,
        partner_rescued_visits=1,
        stock_positive_probes=4,
        positive_probes=3,
        stock_candidates=16,
        retained_candidates=12,
        stock_non_gated_candidates=12,
        retained_non_gated_candidates=9,
        receiver_calls=6,
    )
    assert not result["source"]["probes"][1]["candidates"]
    assert result["source"]["probes"][2:6] == stock["source"]["probes"][2:6]


def test_strict_gate_does_not_treat_truthy_integer_as_a_pass():
    stock = complete_stock()
    stock["source"]["probes"][0]["candidates"][0]["passed_fractional_margin_gate"] = 1
    result, dispatch = project(stock, RF)
    assert dispatch[0]["partner_required"] is True
    assert audit(stock, result, dispatch, RF)["positive_visits"] == 3


def test_audit_rejects_changed_recovery_array_even_when_preserving_positive_visit():
    stock = complete_stock()
    result, dispatch = project(stock, RF)
    altered = copy.deepcopy(result)
    altered["source"]["probes"][2]["candidates"].pop()
    with pytest.raises(ValueError, match="strict per-lane dispatch"):
        audit(stock, altered, dispatch, RF)
