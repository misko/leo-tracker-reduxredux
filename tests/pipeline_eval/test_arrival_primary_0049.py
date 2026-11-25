from copy import deepcopy

import arrival_primary_0049 as primary
import pytest
from test_matched_donor_0049 import factor, native_pair


def test_requires_frequency_and_timing_on_the_same_original_winner():
    arrival = primary.arrival
    actual = factor(-10_000.)
    samples = 13_332
    phase = arrival.arrival_phase(samples, actual)
    query = dict(centers_hz=[-10_250.], phase=dict(
        interpolated=(phase + 1.5) % arrival.PERIOD, left_only=phase, quarter_period_control=phase))
    stock = dict(hit=dict(counter=samples, factor=actual),
                 wrong_frequency=dict(counter=samples, factor=factor(-10_501.)),
                 wrong_phase=dict(counter=samples, factor=dict(actual, integer_epoch_sample=1245)),
                 empty=dict(counter=samples, factor=None))
    found = primary.primary_hits(dict.fromkeys(stock, query), stock)
    assert found == {"hit": dict(installed_minus_query_cfo_hz=250., installed_minus_query_arrival_samples=-1.5)}


def test_only_enrolled_empties_get_the_complete_winner_in_original_order():
    stock, sparse = native_pair()
    before = deepcopy((stock, sparse))
    original = primary.signed.opportunities(sparse)
    oid = list(original)[8]
    proof = {oid: {"installed_minus_query_cfo_hz": 12.}}
    packet, audit = primary.splice(stock, sparse, proof, "sealed-projection")
    result = primary.signed.opportunities(packet)
    assert list(result) == list(original)
    assert (stock, sparse) == before
    assert audit["inserted_count"] == 1 and audit["all_empty_insertions"] == 2
    assert audit["original_winners"] == 8 and audit["derived_winners"] == 9
    assert result[oid]["row"] == dict(original[oid]["row"], candidates=[stock["source"]["probes"][8]["candidates"][0]])
    assert all(result[key] == row for key, row in original.items() if key != oid)
    assert audit["recipe"]["insertion_sha256"] == primary.signed.canonical(audit["inserted"])
    assert audit["derived_native_sha256"] == primary.signed.canonical(packet)


def test_fails_closed_if_a_hit_would_replace_an_existing_winner():
    stock, sparse = native_pair()
    existing = list(primary.signed.opportunities(sparse))[4]
    with pytest.raises(ValueError, match="sparse-empty short"):
        primary.splice(stock, sparse, {existing: {}}, "sealed-projection")
