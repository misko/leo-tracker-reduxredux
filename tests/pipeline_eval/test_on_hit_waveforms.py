from copy import deepcopy
from hashlib import sha256

import pytest

from tools.pipeline_eval.__main__ import encoded
from tools.pipeline_eval.qualification import on_hit_waveforms as trial
from tools.pipeline_eval.qualification import on_hit_waveforms_raw as raw
from tools.pipeline_eval.qualification.on_hit_waveforms_results import audit
from tools.pipeline_eval.variants import partner_on_hit


def packet(visit, rx, positive):
    return dict(
        visit_index=visit,
        receiver_id=rx,
        candidates=[dict(passed_fractional_margin_gate=True)] if positive else [],
    )


def test_native_policy_uses_only_the_original_strict_fractional_boolean():
    found = {"candidates": [{"passed_fractional_margin_gate": True}]}
    below = {"candidates": [{"passed_fractional_margin_gate": False}]}
    fabricated = {"candidates": [{"passed_fractional_margin_gate": 1}]}
    assert raw.needs_partner(found)
    assert not raw.needs_partner(below)
    assert not raw.needs_partner(fabricated)


def test_direct_measurement_reproduces_standard_identity_without_stock_candidates():
    stock = dict(
        source=dict(
            analysis_manifest_sha256="stock-analysis",
            probes=[
                packet(1, 0, True),
                packet(1, 1, True),
                packet(3, 0, True),
                packet(3, 1, False),
            ],
        ),
        provenance=dict(excluded_windows=[]),
    )
    primary = [
        dict(visit=1, selected_receiver=0, rf_center_hz=1),
        dict(visit=3, selected_receiver=1, rf_center_hz=1),
    ]
    expected, _ = partner_on_hit.project(stock, primary)
    actual = deepcopy(expected)
    actual["source"]["analysis_manifest_sha256"] = "raw-measured"
    assert trial.mark(actual, actual["source"]["probes"], "stock-analysis", primary) == expected
    actual["source"]["probes"][2] = packet(3, 0, True)
    with pytest.raises(ValueError, match="actual raw detector rows"):
        trial.mark(actual, actual["source"]["probes"], "stock-analysis", primary)

    digest = sha256(encoded(expected) + b"\n").hexdigest()
    proof = audit(stock, expected, primary, [[1, 0, True], [3, 1, False]], digest)
    assert proof["exact_native_bytes"]
    assert proof["actual_calls_by_rf"] == {"1": [1, 2]}
    assert proof["receiver_calls"] == dict(four=4, one=2, miss=3, hit=3)
    assert proof["gate_positive_probes"] == dict(four=3, one=1, miss=2, hit=2)
    with pytest.raises(ValueError, match="actual partner decision"):
        audit(stock, expected, primary, [[1, 0, True], [3, 1, True]], digest)
    with pytest.raises(ValueError, match="independent exact dual-stock projection"):
        audit(stock, expected, primary, [[1, 0, True], [3, 1, False]], "wrong-digest")
