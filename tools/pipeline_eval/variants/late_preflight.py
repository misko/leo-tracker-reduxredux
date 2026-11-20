"""Fast RF preflight before late orbit-family influence and reassociation."""

from math import isfinite, sqrt
from statistics import mean, stdev

ARMS = ("c0", "fitted_c")
MIN_POINTS = 30
MIN_TRACKS = 2
MIN_T = 3.0
MIN_RELATIVE_BIAS = 0.75


def rf_rows(arms):
    """Project causal cavity gates to paired per-track sufficient statistics."""
    return {
        arm: [
            (
                row["norad"],
                row["component"],
                row["points"],
                row["profile_bias_hz"],
                row["conditional_residual_gate"]["rms_hz"],
            )
            for row in arms[arm]["gates"]["tracks"]
            if row["compatible"]
        ]
        for arm in ARMS
    }


def coherent_bias(rows):
    bias = mean(b for _, b, _ in rows)
    rms = sqrt(mean(r * r for _, _, r in rows))
    scatter = stdev(b for _, b, _ in rows)
    # The equivalent t inequality avoids division by zero when tracks agree exactly.
    return bias, abs(bias) >= max(MIN_T * scatter / sqrt(len(rows)), MIN_RELATIVE_BIAS * rms)


def preflight(rows):
    """Keep the original search when any repeated family has a paired coherent RF offset.

    Each track is one sample so a long track cannot turn an offset into independent
    evidence. This is a prioritization heuristic, with fail-open malformed inputs.
    """
    grouped = {arm: {} for arm in ARMS}
    if rows.keys() != grouped.keys() or not all(rows.values()):
        return True, "unavailable_evidence", ()
    for arm, entries in rows.items():
        for family, track, count, bias, rms in entries:
            if count <= 0 or not isfinite(bias) or not isfinite(rms) or rms < 0:
                return True, "unavailable_evidence", ()
            family_tracks = grouped[arm].setdefault(family, {})
            if track in family_tracks:
                return True, "unavailable_evidence", ()
            family_tracks[track] = (count, bias, rms)
    first, second = (grouped[arm] for arm in ARMS)
    plausible = []
    for family in first.keys() & second.keys():
        a, b = first[family], second[family]
        shared = sorted(a.keys() & b.keys())
        if len(shared) < MIN_TRACKS or any(
            sum(side[k][0] for k in shared) < MIN_POINTS for side in (a, b)
        ):
            continue
        (az, ag), (bz, bg) = (coherent_bias([side[k] for k in shared]) for side in (a, b))
        if ag and bg and az * bz > 0:
            plausible.append(family)
    return (
        bool(plausible),
        "paired_profile_bias" if plausible else "no_coherent_family",
        tuple(sorted(plausible)),
    )
