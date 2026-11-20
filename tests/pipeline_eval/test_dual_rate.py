import pytest

from tools.pipeline_eval.variants.dual_rate import available, select_probes


def pair(visit, flags):
    return tuple(
        dict(
            visit_index=visit,
            receiver_id=rx,
            actual_rf_hz=100,
            candidates=[dict(passed_fractional_margin_gate=flag, candidate_rank=1)],
        )
        for rx, flag in enumerate(flags)
    )


def test_whole_replacement_can_remove_a_detection_while_fill_only_adds_a_missing_lane():
    fast = pair(8, (True, False))
    original = pair(8, (False, True))
    assert select_probes(fast, original, "wide") is fast
    assert select_probes(fast, original, "original") is original
    assert select_probes(fast, original, "replace") is original
    kept = select_probes(fast, original, "fill")
    assert kept[0] is fast[0] and kept[1] is original[1]
    assert select_probes(None, original, "fill") is original
    assert select_probes(fast, None, "fill") is fast
    assert select_probes(None, original, "wide") is None
    assert select_probes(None, None, "replace") is None


def test_incomplete_or_unrelated_physical_inputs_cannot_be_combined():
    first = pair(12, (True, True))
    for second in (pair(13, (True, False)), first[:1], first[::-1]):
        with pytest.raises(ValueError):
            select_probes(first, second, "replace")
    with pytest.raises(ValueError, match="physical probe"):
        select_probes(first, (first[0], dict(first[1], actual_rf_hz=101)), "fill")
    with pytest.raises(ValueError, match="policy"):
        select_probes(first, None, "guess")


def test_final_clock_and_per_arrival_age_share_the_inclusive_boundary():
    assert available(140, 120, 140, 20)
    assert not available(141, 120, 140)
    assert not available(141, 120, 150, 20)
    assert not available(None, 120, 150)
    with pytest.raises(ValueError, match="preceded"):
        available(119, 120, 150)
