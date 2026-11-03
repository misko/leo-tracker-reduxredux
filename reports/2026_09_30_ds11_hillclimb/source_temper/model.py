"""Predeclared tempering of the frozen receiver-balanced source weights."""
from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
FROZEN_MODEL = HERE.parent / "source_balance" / "model.py"
FROZEN_MODEL_SHA256 = "23d806106b7d144d93ee34440e4dbf3d276bfcf71a0a64e882168175b42f7cca"
if hashlib.sha256(FROZEN_MODEL.read_bytes()).hexdigest() != FROZEN_MODEL_SHA256:
    raise RuntimeError("screen-frozen source-balance model changed")
_spec = importlib.util.spec_from_file_location("ds11_source_balance_for_tempering", FROZEN_MODEL)
source_balance = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = source_balance
_spec.loader.exec_module(source_balance)


VARIANTS = {"source_alpha050": 0.50, "source_alpha075": 0.75}
SCREEN_INDICES = tuple(range(0, 32, 4))


def tempered_weights(assignments, alpha):
    if alpha not in VARIANTS.values():
        raise ValueError("alpha was not predeclared")
    original = source_balance.derive_weights(assignments, "source_receiver_equal")
    weights = original**alpha
    # Ambiguous tracks are unique singleton sources under the frozen grouping.
    for row, weight in zip(assignments, weights, strict=True):
        if not row["unambiguous"] and weight != 1.0:
            raise AssertionError("ambiguous singleton weight changed")
    return weights


def build_model(documents, config, variant, index=None):
    if variant not in VARIANTS:
        raise ValueError(f"unknown source-tempering variant: {variant}")
    candidate_norad, original_x, sidecar_path, incumbent_path = source_balance._resources(
        index, documents
    )
    assignments = source_balance.freeze_assignments(
        documents, config, original_x, candidate_norad
    )
    alpha = VARIANTS[variant]
    weights = tempered_weights(assignments, alpha)
    model = source_balance.SourceBalancedIID(documents, config, weights, assignments)
    model.metadata = {
        "objective": "tempered composite weighted original IID Student-t4 track-mixture likelihood",
        "normalized_posterior": False,
        "variant": variant,
        "alpha": alpha,
        "weight_rule": "screen-frozen source_receiver_equal weight raised to alpha",
        "ambiguous_weight": 1.0,
        "freeze": "original same-scan IID training endpoint only",
        "confidence_threshold": source_balance.CONFIDENCE_THRESHOLD,
        "screen_indices": list(SCREEN_INDICES),
        "screen_frozen_model_sha256": FROZEN_MODEL_SHA256,
        "identity_sidecar_sha256": source_balance._digest(sidecar_path),
        "incumbent_iid_sha256": source_balance._digest(incumbent_path),
        "tracks": len(assignments),
        "unambiguous_tracks": sum(row["unambiguous"] for row in assignments),
        "ambiguous_singletons": sum(not row["unambiguous"] for row in assignments),
        "weight_sum": float(np.sum(weights)),
        "weight_min": float(np.min(weights)),
        "weight_max": float(np.max(weights)),
    }
    return model
