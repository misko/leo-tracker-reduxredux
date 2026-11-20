import json

import pytest

from tools.pipeline_eval.qualification import (
    clock_transfer_inputs,
    compact_transfer,
    screening_figures,
)
from tools.pipeline_eval.scoring import ARMS


def test_portable_supplement_preserves_sealed_factor_values_and_timing():
    cold = clock_transfer_inputs.cold
    anchor = 1_794_932_375_000_000_000
    first = 81_001_231
    row = cold._probe_row(0, 0, 1, first, [cold._peak(1, 2000.0, 6.6, 0.4)])
    native = clock_transfer_inputs._native("opaque", anchor, first, [row])
    completed = compact_transfer.complete_native(native)
    assert completed["source"]["probes"] == [row]
    assert completed["source"]["qualified"] is True
    assert completed["last_sample_counter"] == native["last_sample_counter"]
    bracket = dict(realtime_ns=anchor, monotonic_ns=10_000_000_000)
    assert completed["clock_anchor"] == dict(sample_counter=first, before=bracket, after=bracket)
    end_of_probe_ns = cold.PROBE_MS * 1_000_000
    assert completed["delivery_clocks"] == [
        dict(realtime_ns=anchor + end_of_probe_ns, monotonic_ns=10_000_000_000 + end_of_probe_ns)
    ]


def test_portable_supplement_rejects_unrelated_sample_duration():
    probe = clock_transfer_inputs.cold._probe_row(0, 0, 1, 0, [])
    raw = clock_transfer_inputs._native("opaque", 100, 0, [probe])
    raw["last_sample_counter"] -= 1
    with pytest.raises(ValueError, match="sample bound"):
        compact_transfer.complete_native(raw)


def test_worker_packet_contains_offer_and_causal_bindings_with_no_scoring_authority():
    cold = clock_transfer_inputs.cold
    row = cold._probe_row(0, 1, 3, 101, [])
    native = clock_transfer_inputs._native("opaque", 1000, 101, [row])
    completed = compact_transfer.complete_native(native)
    completed["truth"] = [12, 34]
    completed["source"]["owner"] = "latent id"
    completed["provenance"]["location"] = [12, 34]
    offer = dict(id="opaque", center=[-20, 30], width_km=25, truth=[12, 34])
    history = [dict(collected_utc_ns=10, sha256="c" * 64, later_trajectory="forbidden")]
    request = json.loads(compact_transfer.request_data(completed, offer, history))
    assert set(request) == {"document", "tile", "history"}
    assert request["history"] == [dict(collected_utc_ns=10, sha256="c" * 64)]
    assert request["tile"] == dict(id="opaque", center=[-20, 30], width_km=25)
    assert "truth" not in request["document"]
    assert "owner" not in request["document"]["source"]
    assert "location" not in request["document"]["provenance"]


def test_sealed_compact_cards_preserve_deadlines_and_measured_scope():
    cards = {card.id: card for card in screening_figures.charts(evidence=compact_transfer.REPORT)}
    synthetic = cards["compact-secant-paired-transfer"]
    measured = cards["compact-secant-measured-shift"]
    assert synthetic.cases != measured.cases
    assert len(synthetic.cases) == 4
    assert measured.cases == (compact_transfer.ROOF,)
    for arm in ARMS:
        marks = [mark for mark in synthetic.page(arm).rows if mark.series == "candidate"]
        assert len(marks) == 4
        omitted = [mark for mark in marks if mark.dataset == "Correct region omitted"]
        assert len(omitted) == 2
        assert all(mark.decision == "timed_out" and mark.error_km is None for mark in omitted)
