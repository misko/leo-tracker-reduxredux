from copy import deepcopy

import pytest

import guarded_full_anchor as guard
from full_short_run import SPARSE_EIGHT_MS_SHA, checked_recipe, verify_recipe, SPARSE_EIGHT_MS_RECIPE_SHA
from guarded_full_anchor_trial import compare_probes
from leo.contracts.digests import canonical_digest


def test_registration_keeps_legacy_parent_and_rejects_changes_to_guard():
    original = checked_recipe(eight_ms=True, short_pin=SPARSE_EIGHT_MS_SHA)
    guarded = dict(original, **{guard.FIELD: guard.definition()})
    assert guard.unguarded(original) is original
    assert guard.unguarded(guarded) == original
    assert canonical_digest(guarded) != canonical_digest(original)
    verify_recipe(guard.unguarded(guarded), SPARSE_EIGHT_MS_RECIPE_SHA)
    change = deepcopy(guarded)
    change[guard.FIELD]["anchor_stride"] = 16
    with pytest.raises(ValueError, match="Unknown guarded full anchor"):
        guard.unguarded(change)


def test_only_the_pinned_full_option_and_sparse_short_can_bind(monkeypatch, tmp_path):
    original = checked_recipe(eight_ms=True, short_pin=SPARSE_EIGHT_MS_SHA)
    asset = tmp_path / "native.so"
    asset.write_bytes(b"different native receiver")
    with pytest.raises(ValueError, match="differs"):
        guard.configure(asset, SPARSE_EIGHT_MS_SHA, original, asset)
    with pytest.raises(ValueError, match="registered sparse 8 ms"):
        guard.configure(asset, "different-short", original, asset)

    monkeypatch.setattr(guard, "checked_library", lambda library: library)
    registered, guarded = guard.configure(asset, SPARSE_EIGHT_MS_SHA, original, asset)
    assert registered.full == asset
    assert registered.schedule.rule == ("full",) + ("short_primary",)*7
    assert guarded[guard.FIELD]["full_scans"] == 2


def test_preserve_full_discrete_values_and_exact_short_scores():
    probe = {"visit_index": 0, "candidates": [{"candidate_rank": 1, "integer_epoch_sample": 222,
             "fractional_tracking_cfo_hz": -37500.0, "fractional_exact_score": .123,
             "fractional_control_score": .039, "fractional_margin": .084}]}
    changed = deepcopy(probe)
    changed["candidates"][0]["fractional_margin"] += 5e-13
    result = compare_probes([probe], [changed], ["full"])
    assert result["changed_continuous_lanes"] == 1
    with pytest.raises(ValueError, match="Short bytes"):
        compare_probes([probe], [changed], ["short_primary"])
    changed["candidates"][0]["fractional_tracking_cfo_hz"] += .0000000001
    with pytest.raises(ValueError, match="signed rank"):
        compare_probes([probe], [changed], ["full"])
