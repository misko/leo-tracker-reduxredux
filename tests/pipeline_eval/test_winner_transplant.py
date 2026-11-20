from copy import deepcopy

import pytest

from tools.pipeline_eval.qualification.factor_cross import CFO, GATE, MARGIN, RANK, winner
from tools.pipeline_eval.qualification.full_v5_check import ALIAS_HZ
from tools.pipeline_eval.qualification.winner_transplant_intervention import (
    matched,
    select,
    transplant,
)
from tools.pipeline_eval.qualification.winner_transplant_results import audit_packet


def candidate(epoch, cfo, rank=0, margin=0.05, gated=True):
    return {
        RANK: rank,
        GATE: gated,
        MARGIN: margin,
        CFO: cfo,
        "integer_epoch_sample": int(epoch),
        "fractional_epoch_offset_samples": epoch - int(epoch),
        "measurement_field": (epoch, cfo),
    }


def document(by_visit):
    probes = [
        dict(
            visit_index=visit,
            receiver_id=lane,
            channel=1,
            edge="lower",
            actual_rf_hz=100_000,
            candidates=by_visit[visit] if lane == 0 else [],
        )
        for visit in range(len(by_visit))
        for lane in (0, 1)
    ]
    return dict(
        schema_version=1,
        clock_anchor=0,
        delivery_clocks=list(range(len(by_visit))),
        last_sample_counter=1,
        provenance=dict(excluded_windows=[]),
        source=dict(
            session_id="fixture",
            input_manifest_sha256="manifest",
            raw_recording_authority_digest="iq",
            sample_rate_hz=10_000_000,
            probe_ms=20,
            radio_id="radio",
            stream_generation="one",
            capture_mode="fixture",
            probes=probes,
        ),
    )


def test_exact_winner_signed_alias_gate_and_availability_are_separate():
    more = candidate(0.25, 10_000, rank=1)
    capture = document([[more], [more], [more], [more], [more]])
    stock = document(
        [
            [candidate(13_332.75, 10_000 + ALIAS_HZ, margin=0.09)],
            [candidate(13_332.75, 10_000, rank=1, gated=False)],
            [],
            [candidate(800, -20_000), candidate(13_332.75, 10_000, rank=1)],
            [],
        ]
    )
    fifth = document(
        [[candidate(0, 10_000, gated=False)], [], [candidate(13_332.75, 10_999)], [], []]
    )
    roster, pairs, placebo_eligible = select("case", dict(capture=capture, four=stock, five=fifth))
    assert [r["visit"] for r in roster["availability"]] == [1, 4]
    assert [r["visit"] for r in roster["matched_availability"]] == [1]
    assert [r["visit"] for r in roster["placebo"]] == [2]
    assert [r["visit"] for r in roster["conflicts"]] == [0]
    assert pairs == [[2, 4]] and placebo_eligible == 1
    original = deepcopy(stock)
    added = transplant(stock, capture, roster["availability"], "availability")
    swapped = transplant(stock, capture, roster["conflicts"], "conflicts")
    audit_packet(stock, capture, swapped, roster["conflicts"], "conflicts")
    assert stock == original
    assert added["source"]["probes"][2]["candidates"] == [more]
    assert added["source"]["probes"][0] == original["source"]["probes"][0]
    swapped_rows = swapped["source"]["probes"][0]["candidates"]
    assert swapped_rows[winner(swapped_rows)] is more
    old = stock["source"]["probes"][0]["candidates"][0]
    assert swapped_rows[0] == dict(old, **{GATE: False})
    assert swapped["source"]["probes"][4:] == stock["source"]["probes"][4:]
    changed = deepcopy(swapped)
    changed["source"]["probes"][1]["candidates"] = [more]
    with pytest.raises(ValueError, match="unselected packet"):
        audit_packet(stock, capture, changed, roster["conflicts"], "conflicts")
    with pytest.raises(ValueError, match="added|addition"):
        transplant(stock, capture, roster["conflicts"], "availability")


def test_matching_never_reuses_and_does_not_relax_a_stratum():
    def probe(index, visit, *, lane=0, channel=1, negative=False):
        return dict(
            index=index,
            visit=visit,
            lane=lane,
            channel=channel,
            edge="upper",
            negative_cfo=negative,
        )

    available = [probe(10, 1), probe(11, 15), probe(12, 22), probe(13, 21, negative=True)]
    placebo = [probe(20, 3), probe(21, 21), probe(22, 15, lane=1), probe(23, 21, channel=2)]
    pairs = matched("case", available, placebo)
    assert [(a["index"], b["index"]) for a, b in pairs] == [(12, 21), (10, 20)]
    assert matched("case", available[::-1], placebo[::-1]) == pairs
