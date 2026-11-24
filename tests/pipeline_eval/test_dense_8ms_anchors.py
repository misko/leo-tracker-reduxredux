import importlib
from pathlib import Path

import pytest


@pytest.fixture
def trial(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))
    return importlib.import_module("dense_8ms_anchors")


def test_three_recipes_preserve_schedule_and_bind_independent_apertures(trial):
    recipes = [trial.receiver(mode)[0] for mode in trial.ORDERS[0]]
    assert [row["aperture_samples"] for row in recipes] == [[200_000, 120_000], [200_000, 80_000], [200_000, 80_000]]
    assert recipes[0]["rule"] == recipes[1]["rule"] == recipes[2]["rule"]
    assert recipes[2]["full_anchor_primary_only"]["symbol"] == "primary_factors"
    assert all("fixed_epoch_cfo_refinement" not in row and "held_native_8ms" not in row for row in recipes)
    assert len({trial.canonical_digest(row) for row in recipes}) == 3
    assert trial.ORDERS[0] == trial.ORDERS[1][::-1]


def test_factor_comparison_uses_wrapped_timing_and_signed_frequency(trial):
    row = dict(visit_index=0, receiver_id=0, candidates=[])
    left = dict(integer_epoch_sample=13_332, fractional_epoch_offset_samples=.3, fractional_tracking_cfo_hz=-2_000.)
    right = dict(integer_epoch_sample=0, fractional_epoch_offset_samples=.3, fractional_tracking_cfo_hz=-1_900.)
    result = trial.change([dict(row, candidates=[left])], [dict(row, candidates=[right])], ["full"])
    assert result["counts"]["signed_matches"] == 1
    assert result["changed"][0]["wrapped_timing_samples"] == pytest.approx(1.)
    assert result["changed"][0]["signed_cfo_hz"] == 100.
    with pytest.raises(ValueError, match="Signed probes differ"):
        trial.change([row], [dict(row, visit_index=1)], ["full"])
