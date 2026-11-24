import json
from itertools import product

import pytest

from reports.ALGO08.v3 import regional_carrier_scout as audit


def test_signed_input_allows_one_quarter_rate_lift_for_every_eligible_bin():
    bank = audit.full_bank()
    assert bank == tuple(range(1311)) + tuple(range(2786, 4096))
    assert audit.full_bank(120_000) == bank
    assert audit.full_bank(-190_000) == bank
    assert audit.RATE > 2*audit.WIDTH_HZ
    assert audit.seed_index(-audit.STEP, 0) == 4095
    with pytest.raises(ValueError, match="off the exact signed scout grid"):
        audit.seed_index(0.1, 0)


def test_alias_filling_bounds_and_missing_region_keep_the_signed_bank():
    bank = audit.full_bank()
    assert audit.lifted_envelope(None) == bank
    assert audit.lifted_envelope([(0, float("inf"))]) == bank
    for center in (0, audit.STEP, -300_000):
        assert audit.lifted_envelope([(center, center+audit.FINAL_ALIAS+1)], audit.FINAL_ALIAS) == bank
    assert audit.lifted_envelope([(-audit.STEP, audit.STEP)]) == (0, 1, 4095)


def top_four(rows, allowed):
    """Toy evaluator with the original row, gap and strict-tie order."""
    proposed = []
    count = len(rows[0])
    for i, scores in enumerate(rows):
        best = max(allowed, key=lambda bin_: scores[bin_])
        proposed.append((scores[best], i, best))
        second = [b for b in allowed if min(abs(b-best), count-abs(b-best)) >= 2]
        if second:
            pick = max(second, key=lambda bin_: scores[bin_])
            proposed.append((scores[pick], i, pick))
    return sorted(proposed, key=lambda seed: -seed[0])[:4]


def test_retained_original_global_seeds_keep_ties_and_circular_second_peak_order():
    eligible = list(range(4))
    for values in product((0, 1), repeat=12):
        rows = [values[i:i+4] for i in (0, 4, 8)]
        original = top_four(rows, eligible)
        exact_answer_key = sorted({seed[2] for seed in original})
        assert top_four(rows, exact_answer_key) == original


def test_signed_20ms_trace_preserves_all_requests_under_the_full_bank():
    archived = json.loads((audit.MEASUREMENTS / "regional-carrier-scout.json").read_text())
    reference = audit.summarize()
    assert json.loads(json.dumps(reference["sites"])) == archived["sites"]
    for case, (scouts, requests) in {"dense": (148, 592), "weak": (72, 288)}.items():
        source = reference["sites"][case]["both"]
        assert source["carrier_fft_invocations"] == scouts*24
        assert source["retained_requests_at_full_fallback"] == requests
        assert source["certified_regional_rank_indices_omitted"] == 0
