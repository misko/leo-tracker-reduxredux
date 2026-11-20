from copy import deepcopy

from tools.pipeline_eval.qualification import shared_winner_cross as swap
from tools.pipeline_eval.qualification.factor_cross import CFO, GATE, MARGIN, RANK, winner
from tools.pipeline_eval.qualification.full_v5_check import ALIAS_HZ


def candidate(epoch, cfo, margin, rank=0, gated=True):
    return {
        "integer_epoch_sample": epoch,
        "fractional_epoch_offset_samples": 0.25,
        "fractional_exact_score": margin + 0.03,
        CFO: cfo,
        MARGIN: margin,
        RANK: rank,
        GATE: gated,
    }


def document(*groups):
    return dict(
        source=dict(
            sample_rate_hz=10_000_000,
            probes=[dict(visit_index=i, candidates=group) for i, group in enumerate(groups)],
        )
    )


def test_strict_match_wraps_both_observables_and_classifies_export_failure():
    wide = document(
        [candidate(13343, ALIAS_HZ + 999, 0.9)],
        [candidate(40, 0, 0.9), candidate(10, 1, 0.3, 1), candidate(11, -2, 0.4, 2)],
        [candidate(40, 0, 0.9), candidate(10, 0, 0.015, 1, gated=False)],
        [candidate(10, 1001, 0.9)],
        [candidate(13, 0, 0.9)],
        [candidate(24, 0, 0.9)],
    )
    capture = document(*[[candidate(10, 0, 0.9)]] * 6)
    rows, counts = swap.assess(wide, capture, ["11"] * 5 + ["01"])
    assert counts == {
        "same_strict_family": 1,
        swap.AVAILABLE: 1,
        "matching_wide_ungated": 1,
        "epoch_nearby_wrong_cfo": 1,
        "no_nearby_wide_epoch": 1,
    }
    assert [r["index"] for r in rows] == [1, 2, 3, 4]
    assert rows[0]["wide_alternative"] == 2
    assert rows[0]["gated_alternatives"] == 2


def test_only_discordant_targets_change_and_donor_fields_stay_exact():
    wide = document(
        [candidate(40, 1, 0.9), candidate(10, 1, 0.3, 1), candidate(55, 0, 0.2, 2)],
        [candidate(55, 31, 0.9), candidate(56, 32, 0.3, 1)],
        [candidate(10, 17, 0.8)],
    )
    capture = document(
        [candidate(29, 0, 0.01, gated=False), candidate(10, 41, 0.1, 1)],
        [candidate(27, 0, 0.01, gated=False), candidate(10, 42, 0.1, 1)],
        [candidate(10, 44, 0.7)],
    )
    before = deepcopy([wide, capture])
    choices, _ = swap.assess(wide, capture, ["11"] * 3)
    for mode, count in zip(swap.TREATMENTS, (1, 1, 2), strict=True):
        result, changed = swap.replace(wide, capture, choices, mode)
        batches = [p["candidates"] for p in result["source"]["probes"]]
        assert changed == count
        assert batches[2] == wide["source"]["probes"][2]["candidates"]
        if mode == "wide_alternative":
            assert winner(batches[0]) == 1
            assert batches[0][1:] == wide["source"]["probes"][0]["candidates"][1:]
            assert batches[0][0][GATE] is False
            assert batches[1] == wide["source"]["probes"][1]["candidates"]
        else:
            assert winner(batches[1]) == 0
            assert batches[1][0] == dict(
                capture["source"]["probes"][1]["candidates"][1], **{RANK: 0}
            )
            assert batches[1][1][GATE] is False
            assert winner(batches[0]) == 0
            assert batches[0][0][CFO] == (41 if mode == "all_discordant" else 1)
    assert [wide, capture] == before
