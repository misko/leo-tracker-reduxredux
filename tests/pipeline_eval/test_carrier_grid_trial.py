from copy import deepcopy
from importlib import import_module
from pathlib import Path

import pytest

from leo.contracts.digests import canonical_digest


@pytest.fixture
def trial(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("carrier_grid_trial")


@pytest.mark.parametrize("mode, spacing", [("bin", 610.3515625), ("quarter", 152.587890625)])
def test_signed_nearest_grid_ties_and_limits(trial, mode, spacing):
    assert trial.GRID_HZ[mode] == spacing
    for sign in (1, -1):
        assert trial.placed_hz(sign * spacing / 2, spacing) == 0
        assert trial.placed_hz(sign * 1.5 * spacing, spacing) == sign * 2 * spacing
        assert trial.placed_hz(sign * 2.5 * spacing, spacing) == sign * 2 * spacing
        for value in (sign * 500_123.456, sign * 56.3, sign * 0.1):
            placed = trial.placed_hz(value, spacing)
            assert abs(placed - value) <= spacing / 2
            assert placed / spacing == round(placed / spacing)
    with pytest.raises(ValueError, match="finite signed"):
        trial.placed_hz(float("nan"), spacing)


def test_only_cfo_and_derived_binding_change(trial):
    rows = [
        dict(receiver_id="a", valid_start_counter=50, actual_rf_hz=11e9, candidates=[
            dict(candidate_rank=1, fractional_tracking_cfo_hz=-430.2, fractional_margin=1.23,
                 passed_fractional_margin_gate=True, fractional_offset_samples=-0.25)]),
        dict(receiver_id="b", valid_start_counter=51, actual_rf_hz=12e9, candidates=[]),
    ]
    native = dict(source=dict(sample_rate_hz=10_000_000, probes=rows, session_id="original",
                              raw_recording_authority_digest="archive", analysis_manifest_sha256="old"),
                  provenance=dict(detector_sha256="sha256:compiled", run_id="old"),
                  sample_clock=dict(sample_counter=0))
    original = deepcopy(native)
    for mode, placed in (("bin", -610.3515625), ("quarter", -457.763671875)):
        changed, audit = trial.quantize(native, mode)
        expected = deepcopy(original)
        expected["source"]["probes"][0]["candidates"][0]["fractional_tracking_cfo_hz"] = placed
        manifest = canonical_digest(["cancellation", "archive", "compiled", expected["source"]["probes"]])
        expected["source"]["analysis_manifest_sha256"] = manifest
        expected["provenance"]["run_id"] = "blind-compact-" + manifest[7:39]
        assert changed == expected
        assert native == original
        assert audit["candidate_ranks"] == {"1": 1}
        assert audit["admitted"] == audit["changed"] == 1 and audit["windows"] == 2
        assert audit["max_abs_hz"] == pytest.approx(abs(placed + 430.2))


def test_owner_overlap_uses_signed_observation_identity(trial):
    from carrier_grid_score import changes

    old = {"keep": 10, "relabel": 20, "lost": 30}
    new = {"keep": 10, "relabel": 21, "added": 40}
    assert changes(old, new) == {"kept": 1, "relabeled": 1, "lost": 1, "added": 1}
    assert changes(old, None) is None
