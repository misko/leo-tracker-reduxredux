"""Audit the frozen five-dwell pilot cache without fitting a phase model."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from validate import support_partition, tone_partition

HERE = Path(__file__).resolve().parent
CACHE = HERE.parent / "pilot-cache.npz"
EXPECTED_VISITS = [259, 260, 261, 262, 263]
SAMPLE_PERIOD_S = 1 / 10_000_000
# fractional_take uses floor(position) + [-7..8].  Expand both reported
# endpoint coordinates by the conservative larger eight-sample reach.
INTERPOLATION_GUARD_S = 8 * SAMPLE_PERIOD_S


def main():
    digest = hashlib.sha256(CACHE.read_bytes()).hexdigest()
    cache = np.load(CACHE, allow_pickle=False)
    required = {"h0", "h1", "products", "weights", "valid",
                "frame_visit_index", "frame_time_s", "frame_time_in_dwell_s",
                "support_start_s", "support_end_s", "training", "held",
                "tone_frequency_hz", "shared_residual_hz"}
    missing = sorted(required - set(cache.files))
    if missing:
        raise ValueError(f"cache lacks required fields: {missing}")
    visits = cache["frame_visit_index"]
    if sorted(np.unique(visits).tolist()) != EXPECTED_VISITS:
        raise ValueError("cache is not exactly the frozen five visits")
    train, held = support_partition(cache["support_start_s"], cache["support_end_s"])
    expanded_train, expanded_held = support_partition(
        cache["support_start_s"] - INTERPOLATION_GUARD_S,
        cache["support_end_s"] + INTERPOLATION_GUARD_S,
    )
    if not np.array_equal(train, expanded_train) or not np.array_equal(held, expanded_held):
        raise ValueError("20 ms split changes after expanding 16-tap interpolation support")
    crossing = ~(train | held)
    if not np.array_equal(train, cache["training"]):
        raise ValueError("serialized training mask disagrees with interpolation support")
    if not np.array_equal(held, cache["held"]):
        raise ValueError("serialized held mask disagrees with interpolation support")
    even, odd = tone_partition(np.arange(cache["products"].shape[1]))
    rows = []
    for visit in EXPECTED_VISITS:
        use = visits == visit
        rows.append({"visit_index": visit, "frames": int(use.sum()),
                     "training": int((use & train).sum()),
                     "held": int((use & held).sum()),
                     "boundary_crossing": int((use & crossing).sum())})
    payload = {
        "cache_sha256": digest,
        "visits": EXPECTED_VISITS,
        "frame_count": int(len(visits)),
        "training_count": int(train.sum()),
        "held_count": int(held.sum()),
        "boundary_crossing_excluded_count": int(crossing.sum()),
        "interpolation_guard_each_side_us": INTERPOLATION_GUARD_S * 1e6,
        "minimum_safe_boundary_margin_us": float(min(
            .020 - np.max(cache["support_end_s"][train]),
            np.min(cache["support_start_s"][held]) - .020,
        ) * 1e6),
        "train_tone_indices": np.flatnonzero(even).tolist(),
        "held_tone_indices": np.flatnonzero(odd).tolist(),
        "per_visit": rows,
        "split_rule": "training support_end_s <= 0.020; held support_start_s >= 0.020",
        "tone_holdout_limit": (
            "Differential phase uses disjoint even/odd tones, but shared_residual_hz "
            "was estimated from RX0 using all eight tones; this is not a strict "
            "end-to-end frequency holdout."
        ),
    }
    (HERE / "cache-audit.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
