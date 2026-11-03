"""Training-count composite weights for a declared DS11 wave-two family."""
from __future__ import annotations

import importlib.util
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
SOURCE_BALANCE = HERE.parent / "source_balance" / "model.py"
_spec = importlib.util.spec_from_file_location("ds11_frozen_source_balance", SOURCE_BALANCE)
source_balance = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = source_balance
_spec.loader.exec_module(source_balance)


VARIANTS = ("count_sqrt", "count_equal", "source_count_equal")


def derive_weights(assignments, documents, variant):
    """Compute train-count-only weights and normalize their arithmetic mean to one."""
    if variant not in VARIANTS:
        raise ValueError(f"unknown source-count variant: {variant}")
    counts = np.asarray([
        int(np.asarray(documents[row["document_index"]]["tracks"][row["track_index"]]["mask"]).sum())
        for row in assignments
    ], dtype=float)
    if np.any(counts < 1):
        raise ValueError("source-count weighting requires positive training counts")
    if variant == "count_sqrt":
        raw = counts ** -0.5
    elif variant == "count_equal":
        raw = counts ** -1.0
    else:
        source_totals = defaultdict(float)
        for row, count in zip(assignments, counts, strict=True):
            source_totals[row["source"]] += count
        raw = np.asarray([1.0 / source_totals[row["source"]] for row in assignments])
    # A common positive multiplier preserves the optimizer and keeps scores and
    # gradients near the original IID numerical scale.
    return raw / raw.mean()


def build_model(documents, config, variant, index=None):
    candidate_norad, original_x, sidecar_path, incumbent_path = source_balance._resources(
        index, documents
    )
    assignments = source_balance.freeze_assignments(
        documents, config, original_x, candidate_norad
    )
    weights = derive_weights(assignments, documents, variant)
    model = source_balance.SourceBalancedIID(documents, config, weights, assignments)
    counts = np.asarray([
        int(documents[row["document_index"]]["tracks"][row["track_index"]]["mask"].sum())
        for row in assignments
    ])
    model.metadata = {
        "objective": "mean-one weighted original IID Student-t4 track-mixture composite likelihood",
        "normalized_posterior": False,
        "variant": variant,
        "count_scope": "training observations only",
        "freeze": "original same-scan IID training endpoint only",
        "source_key": "physical NORAD and exact RF Hz; ambiguous tracks are singleton sources",
        "confidence_threshold": source_balance.CONFIDENCE_THRESHOLD,
        "physical_identity_mapping": "digest-bound bank candidate_ids row to archived-roster NORAD",
        "identity_sidecar_sha256": source_balance._digest(sidecar_path),
        "incumbent_iid_sha256": source_balance._digest(incumbent_path),
        "tracks": len(assignments),
        "training_observations": int(counts.sum()),
        "unambiguous_tracks": sum(row["unambiguous"] for row in assignments),
        "ambiguous_singletons": sum(not row["unambiguous"] for row in assignments),
        "weight_normalization": "arithmetic mean equals one",
        "weight_sum": float(weights.sum()),
        "weight_min": float(weights.min()),
        "weight_max": float(weights.max()),
    }
    return model
