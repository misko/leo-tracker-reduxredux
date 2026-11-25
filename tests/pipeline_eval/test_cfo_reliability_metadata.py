from fractions import Fraction

import pytest

from reports.ALGO08.v3.cfo_reliability_metadata import anchor_disagreement, concordance, gate, two_full_forecast


def test_disagreement_count_keeps_values_on_both_sides_of_fixed_limit():
    ledger = dict(
        counts=dict(rank_zero_with_forecast=3, rank_zero_full_positives=4, full_positives=5, full_lanes=10,
                    eligible_full_anchors=2, short_positives=15),
        anchor_innovations_hz={"a": -250., "b": 249., "c": 251.},
        candidate_result_sha256="result", candidate_native_sha256="native",
    )
    assert anchor_disagreement(ledger)["rate"] == pytest.approx(1/3)
    ledger["anchor_innovations_hz"].pop("a")
    with pytest.raises(ValueError, match="denominator"):
        anchor_disagreement(ledger)


def test_full_only_support_precedes_final_target_edit_gate():
    forecast = dict(left_wait_samples=3_000_000, right_wait_samples=3_000_000)
    ledger = dict(native_sha256="native", held_lanes=8, held_candidate_positives=5, eligible={},
                  forecasts={"both": dict(forecast, donor_full=[True, True]),
                             "some": dict(forecast, donor_full=[False, True])})
    summary = two_full_forecast(ledger)
    assert summary["both_full_donors"] == 1 and summary["both_full_donors_eligible_to_edit"] == 0


def test_gate_and_exact_rank_do_not_classify_unscored_fixes_as_loss():
    def arm(error, fix=True):
        return dict(c0_error_km=error, c0_fix=fix)

    assert gate(arm(1.), arm(1.), "c0") == "kept"
    assert gate(arm(.2), arm(None, False), "c0") == "lost_withheld"
    assert gate(arm(.2), arm(None), "c0") == "candidate_unscored"
    assert gate(arm(1.2), arm(2.), "c0") == "installed_outside"
    assert concordance([("kept", Fraction(1, 2)), ("lost_withheld", Fraction(2, 3)),
                        ("candidate_unscored", Fraction(1, 1))]) == {
        "kept": 1, "lost": 1, "comparisons": 1, "ranks_loss_higher": 1, "ties": 0,
    }
