"""Position-conditioned joins that retain the original discovery alternatives.

Orbit-blind continuity proposes a union; a local orbital-shape match must also
agree with every selected parent before that union can replace those parents.
This is candidate agreement, not a claim of satellite identity.
"""

import time
from dataclasses import asdict, dataclass

import numpy as np

from leo.analysis.regional_position_bootstrap import bootstrap_position
from leo.analysis.regional_position_score import predict_orbits


@dataclass(frozen=True)
class ContinuousBootstrapPolicy:
    mode: str = "consistent"
    rms_floor_hz: float = 200.0
    rms_ratio: float = 1.25

    def __post_init__(self):
        if self.mode not in ("baseline", "shape", "consistent"):
            raise ValueError("unknown continuous bootstrap mode")
        if not np.isfinite((self.rms_floor_hz, self.rms_ratio)).all():
            raise ValueError("nonfinite continuous bootstrap limits")
        if self.rms_floor_hz <= 0 or self.rms_ratio < 1:
            raise ValueError("invalid continuous bootstrap limits")


def choose_proposals(original_tracks, merged_tracks, matches, times_s, policy=None):
    """Replace only complete selected parents; unrelated originals always survive."""
    policy = policy or ContinuousBootstrapPolicy()
    original = tuple(tuple(t) for t in original_tracks)
    if len(set(original)) != len(original):
        raise ValueError("duplicate original proposals")
    by_rows = {tuple(m.rows): m for m in matches}
    parents = [set(t) for t in original]
    selected = list(original)
    consumed = set()
    decisions = []
    for joined in sorted(
        set(tuple(t) for t in merged_tracks) - set(original),
        key=lambda t: (-np.ptp(times_s[list(t)]), t),
    ):
        rows = set(joined)
        overlap = [i for i, parent in enumerate(parents) if parent & rows]
        receipt = {"joined_rows": joined, "parent_indices": overlap, "accepted": False}
        decisions.append(receipt)
        if not overlap:
            receipt["reason"] = "no-selected-parent"
            continue
        if any(not parents[i] <= rows for i in overlap):
            receipt["reason"] = "partial-parent"
            continue
        if consumed.intersection(overlap):
            receipt["reason"] = "parent-already-replaced"
            continue
        if joined not in by_rows or any(original[i] not in by_rows for i in overlap):
            receipt["reason"] = "unqualified-orbital-shape"
            continue
        union = by_rows[joined]
        members = [by_rows[original[i]] for i in overlap]
        limit = max(policy.rms_floor_hz, policy.rms_ratio * max(m.shape_rms_hz for m in members))
        agreement = all(m.satellite_index == union.satellite_index for m in members)
        receipt.update(
            joined_satellite_index=union.satellite_index,
            parent_satellite_indices=[m.satellite_index for m in members],
            joined_shape_rms_hz=union.shape_rms_hz,
            parent_shape_rms_hz=[m.shape_rms_hz for m in members],
            shape_rms_limit_hz=limit,
            candidate_agreement=agreement,
        )
        if policy.mode == "baseline":
            receipt["reason"] = "control-original-proposals"
            continue
        if union.shape_rms_hz > limit:
            receipt["reason"] = "joined-shape-residual"
            continue
        if policy.mode == "consistent" and not agreement:
            receipt["reason"] = "different-orbital-candidate"
            continue
        selected[min(overlap)] = joined
        for i in overlap[1:]:
            selected[i] = None
        consumed.update(overlap)
        receipt.update(accepted=True, reason=None)
    selected = tuple(t for t in selected if t is not None)
    if policy.mode == "consistent":
        before = {by_rows[t].satellite_index for t in original if t in by_rows}
        after = {by_rows[t].satellite_index for t in selected if t in by_rows}
        if before != after:
            raise ValueError("consistent joins changed the original discovery bank")
    return selected, {"policy": asdict(policy), "decisions": decisions}


def bootstrap_with_continuity(
    observations,
    bank,
    prior,
    point,
    tracks,
    *,
    merged_tracks,
    policy=None,
    audit=None,
    maximum_seconds=5.0,
    samples_per_track=12,
    orbit_predictor=predict_orbits,
):
    """All controls profile the same proposal pool under the same total budget."""
    if not np.isfinite(maximum_seconds) or not 0 < maximum_seconds <= 1800:
        raise ValueError("invalid continuous bootstrap work budget")
    begun = time.monotonic()
    pool = tuple(dict.fromkeys(tuple(t) for t in (*tracks, *merged_tracks)))
    proposal_fit = bootstrap_position(
        observations,
        bank,
        prior,
        point,
        pool,
        maximum_seconds=maximum_seconds,
        samples_per_track=samples_per_track,
        orbit_predictor=orbit_predictor,
    )
    selected, receipt = choose_proposals(
        tracks,
        merged_tracks,
        proposal_fit.matches,
        observations.times_s,
        policy,
    )
    remaining = maximum_seconds - (time.monotonic() - begun)
    if remaining <= 0:
        raise TimeoutError("continuous bootstrap total time budget")
    result = bootstrap_position(
        observations,
        bank,
        prior,
        point,
        selected,
        maximum_seconds=remaining,
        samples_per_track=samples_per_track,
        orbit_predictor=orbit_predictor,
    )
    receipt.update(
        point=list(point),
        pool_tracks=len(pool),
        selected_tracks=len(selected),
        selected_joins=sum(d["accepted"] for d in receipt["decisions"]),
        seconds=time.monotonic() - begun,
    )
    if (policy or ContinuousBootstrapPolicy()).mode == "consistent":
        originals = {tuple(t) for t in tracks}
        before = {m.satellite_index for m in proposal_fit.matches if tuple(m.rows) in originals}
        if before != set(result.satellite_indices):
            raise ValueError("recomputed continuous bootstrap changed the original bank")
    if audit is not None:
        audit(receipt)
    return result
