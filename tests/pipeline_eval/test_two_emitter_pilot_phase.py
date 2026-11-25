"""Check truth custody separately from the bounded native experiment."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest


SOURCE = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3/two_emitter_pilot_phase.py"
SPEC = spec_from_file_location("two_emitter_pilot_phase", SOURCE)
phase = module_from_spec(SPEC)
SPEC.loader.exec_module(phase)


def factor(hz, epoch, *, margin=.03, rank=0):
    i = round(epoch)
    return dict(fractional_tracking_cfo_hz=hz, integer_epoch_sample=i,
                fractional_epoch_offset_samples=epoch-i, fractional_margin=margin,
                candidate_rank=rank, passed_fractional_margin_gate=True)


def test_association_uses_signed_cfo_and_isolated_conflicts_without_the_epoch():
    truth = phase.planted(phase.SWAP, phase.ALIAS, 0)
    a, b = (m["cfo_hz"] for m in truth.values())
    isolated = {"A": [[factor(a, 4)], [factor(a, 4)]], "B": [[factor(b, 4)], [factor(b, 4)]]}
    assert phase.identity(factor(b, 9999), 0, truth, isolated) == "B"
    isolated["A"][0].append(factor(b, 15, rank=1))
    assert phase.identity(factor(b, 9999), 0, truth, isolated) == "ambiguous"
    assert phase.identity(factor(b, 9999), 1, truth, isolated) == "B"
    assert phase.identity(None, 1, truth, isolated) == "missing"
    assert phase.identity(factor(a + 1700, 4), 1, truth, isolated) == "unsupported"


def test_coincident_atoms_remain_ambiguous_despite_swapped_plant_strength():
    truth = phase.planted(phase.SWAP, 0, None)
    assert truth["A"]["epochs"] == truth["B"]["epochs"]
    assert truth["A"]["gains"] == truth["B"]["gains"][::-1]
    for lane in (0, 1):
        assert phase.identity(factor(truth["A"]["cfo_hz"], 4), lane, truth, {}) == "ambiguous"


def test_two_sample_rule_uses_physical_period_and_keeps_empty_pairs():
    a = factor(123, phase.PERIOD - 1.5)
    b = factor(900_000, .25)
    assert phase.signed_phase_pair([a, b]) == pytest.approx(1.75)
    assert phase.signed_phase_pair([None, b]) is None
    assert phase.matched_winner([factor(123, 2, rank=1), factor(124, 3, rank=0)])["candidate_rank"] == 0
