"""Keep released phase-transition arithmetic with a scan-local Julian split."""

from functools import lru_cache
from hashlib import sha256
from math import isfinite
from pathlib import Path
from unittest.mock import patch

import numpy as np


PHASE_SHA = "4659c0f6a49dbc3ae8e7f65272d2db9567dd67e6908fcb10c36bf0324decd6dd"


def causal_sigma(alignment, age, gap):
    if not (isfinite(alignment) and isfinite(age) and isfinite(gap)) or age < 0 or gap <= 0:
        raise ValueError("finite causal ages and strictly ordered epochs required")
    return float(min(15., max(1., np.hypot(1., alignment * age / gap))))


def transition_port(module):
    @lru_cache(maxsize=256)
    def split(target):
        day, fraction = module.julian_day_from_utc_ns(np.array([target]))
        return float(day[0]), float(fraction[0])

    def transition(a, b, c):
        target = c["collected_utc_ns"]
        if not (
            a["collected_utc_ns"] <= b["collected_utc_ns"] <= target
            and a["epoch"] < b["epoch"] < c["epoch"] <= target
        ):
            return None
        gap = (b["epoch"] - a["epoch"]) / 1e9
        if gap < 1:
            return None
        day, fraction = split(target)
        # Preserve the original fresh scalar Satrec state for each propagation.
        states = [module.Satrec.twoline2rv(*row["lines"]).sgp4(day, fraction)
                  for row in (a, b, c)]
        if states[0][0] or states[1][0] or states[2][0]:
            return None
        pa, pb, pc = [np.asarray(state[1]) for state in states]
        velocity = np.asarray(states[1][2])
        norm = float(velocity @ velocity)
        alignment = float((pa - pb) @ velocity / norm)
        innovation = float((pc - pb) @ velocity / norm)
        age = (target - b["epoch"]) / 1e9
        # The causal ordering above guarantees a positive age and gap.
        return dict(
            validation_time_ns=target,
            old_middle_alignment_s=alignment,
            next_innovation_s=innovation,
            unit_forecast_s=-min(age / gap, 2.) * alignment,
            age_s=age,
            epoch_gap_s=gap,
            predicted_sigma_s=causal_sigma(alignment, age, gap),
        )

    return transition, split


def forecast(original, history):
    from leo.analysis.localization_v3 import phase_prior

    path = Path(phase_prior.__file__)
    stock = phase_prior.transition
    if (sha256(path.read_bytes()).hexdigest() != PHASE_SHA
            or stock.__code__.co_filename != str(path) or stock.__name__ != "transition"):
        raise ValueError("Unreviewed released phase transition")
    operation, split = transition_port(phase_prior)
    with patch.object(phase_prior, "transition", operation):
        result = original(history)
    info = split.cache_info()
    return result, dict(julian_cache_hits=info.hits, julian_cache_misses=info.misses,
                        julian_cache_entries=info.currsize, capacity=info.maxsize)
