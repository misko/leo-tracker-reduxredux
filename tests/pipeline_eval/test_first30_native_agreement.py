from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from first30_native_agreement import CFO, FRACTION, INTEGER, RATE, losses, match, prediction, signed_score


def peak(cfo, epoch=0, fractional=0.):
    return {CFO: cfo, INTEGER: epoch, FRACTION: fractional}


def test_reciprocal_peak_match_separates_ambiguity_and_unmatched_rows():
    old = [peak(0), peak(50), peak(1000), peak(3000)]
    new = [peak(25), peak(1020, 1, -.2), peak(2000), peak(3000 + 1/4.4e-6)]
    matches, counts = match(old, new)
    assert len(matches) == 1
    assert matches[0][2:] == (20, .8)
    assert counts == dict(matched=1, installed_only_peaks=1, mixed_only_peaks=2,
                          ambiguous_installed_peaks=2, ambiguous_mixed_peaks=1)


def test_physics_uses_earlier_support_without_a_stock_factor():
    current = peak(30300.)
    previous = [(0, .003, 30000.), (RATE, .003, 30100.)]
    frequency, timing, _ = prediction(current, 2*RATE, True, 10e9, previous)
    assert frequency < 0 and timing < 0
    assert timing / frequency == pytest.approx(RATE * (30300. / 10e9) / 100.)
    assert prediction(current, 9*RATE, True, 10e9, previous)[0] is None
    assert prediction(current, 2*RATE, False, 10e9, previous)[:2] == (0., 0.)


def test_radio_nuisance_uses_same_exposure_and_scores_both_signs():
    y = {(0, "a"): [(110., 0., 60., 0.), (90., 0., 40., 0.), (1e8, 0., None, 0.)]}
    scope = losses(y, 0, 2, "radio")
    assert scope == dict(n=2, groups=1, baseline_loss=200., cross=200., predictor_energy=200.)
    assert signed_score(scope, 1)["rms_after"] == 0.
    assert signed_score(scope, -1)["rms_after"] == 20.
