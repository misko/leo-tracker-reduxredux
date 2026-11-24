from pathlib import Path

import pytest

from reports.ALGO08.v3 import integrated_original_entry as entry
from reports.ALGO08.v3 import integrated_original_trial as trial


def test_sparse_recipe_requires_checked_new_identity():
    from full_short_run import (EIGHT_MS_RECIPE_SHA, SPARSE_EIGHT_MS_RECIPE_SHA, SPARSE_EIGHT_MS_SHA,
                                checked_recipe, verify_recipe)

    regular = checked_recipe(True)
    sparse = checked_recipe(True, short_pin=SPARSE_EIGHT_MS_SHA)
    assert sparse == dict(regular, shortened_sha256=SPARSE_EIGHT_MS_SHA)
    verify_recipe(sparse, SPARSE_EIGHT_MS_RECIPE_SHA)
    with pytest.raises(ValueError, match="changed"):
        verify_recipe(sparse, EIGHT_MS_RECIPE_SHA)
    with pytest.raises(ValueError, match="Unregistered"):
        checked_recipe(True, short_pin="0"*64)
    with pytest.raises(ValueError, match="requires"):
        checked_recipe(short_pin=SPARSE_EIGHT_MS_SHA)


def test_native_factory_preserves_restrictive_pillow_limit(monkeypatch):
    from PIL import Image

    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 10)
    audit = {}
    args = Path("/candidate"), object(), {}
    factory = entry.verification_factory(lambda *args: args, audit)
    result = factory(*args)
    assert result == args
    assert audit == {"unavailable": "stricter Pillow pixel limit"}


def test_proof_rebinding_requires_old_packet_identity():
    original = {"native_sha256": "old", "curvature_extent": {"native_sha256": "old", "proven": True}}
    assert trial.rekey_proof(original, "old", "new") == {
        "native_sha256": "new", "curvature_extent": {"native_sha256": "new", "proven": True},
    }
    assert original["curvature_extent"]["native_sha256"] == "old"
    with pytest.raises(ValueError, match="Unbound"):
        trial.rekey_proof(original, "unrelated", "new")


def test_tiny_admission_uses_frozen_near_target_cutoff():
    process = {"exit_code": 0}
    def positive(speedup, qualified=True):
        return {"qualified": qualified, "modeled_cohort_gates": {"elapsed_s": {"summed_speedup": speedup}}}

    assert trial.allowed_tiny(positive(1.568), process)
    assert not trial.allowed_tiny(positive(1.5679), process)
    assert not trial.allowed_tiny(positive(1.600, qualified=False), process)
    assert not trial.allowed_tiny(positive(1.600), {"exit_code": 1})
