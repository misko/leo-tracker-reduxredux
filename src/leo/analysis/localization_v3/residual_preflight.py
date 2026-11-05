"""Prepare unclaimed native evidence under the frozen selected receiver model."""

import numpy as np

from leo.analysis.localization_v3.residual_fragments import fragment_rows

ARMS = ("c0", "fitted_c")


def _plain_native(value):
    """Keep the original scalar arithmetic without a persisted JSON roundtrip."""
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {k: _plain_native(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain_native(v) for v in value]
    return value


def rank_targets(tracks, observations, owners, identities, *, case="SCAN"):
    """Preserve the original top-three duration ranking and both-arm exclusion."""
    if set(owners) != set(ARMS):
        raise ValueError("Both selected ownership maps required")
    universe = {o["observation_id"] for o in observations}
    if any(not set(owner) <= universe for owner in owners.values()):
        raise ValueError("Unknown selected observation")
    fragments, summary = fragment_rows(
        case, _plain_native(tracks), _plain_native(observations), owners["fitted_c"], identities
    )
    occupied = set(owners["c0"]) | set(owners["fitted_c"])
    eligible = [
        r
        for r in fragments
        if r["points"] >= 20 and r["duration_s"] >= 15 and not set(r["observation_ids"]) & occupied
    ]
    eligible.sort(key=lambda r: (-r["duration_s"], -r["points"], r["fragment_id"]))
    return dict(
        fragments=fragments, summary=summary, targets=eligible[:3], eligible_targets=len(eligible)
    )


def preflight(context, targets, scan_receipt, *, case="SCAN"):
    """Subtract already fitted hardware and drift without refitting target points.

    This packet is for causal candidate nomination, not permission to associate
    any point. Position fitting and held-out identity gates follow separately.
    """
    if set(context["problems"]) != set(ARMS):
        raise ValueError("Both selected calibration arms required")
    scan = context["scan"]
    if scan_receipt["origin_utc_ns"] != scan.origin_utc_ns:
        raise ValueError("Scan metadata origin differs from selected likelihood")
    rows = []
    for source in targets:
        track = scan.tracks[source["track_index"]]
        ix = np.asarray(source["source_local_indices"])
        if [track["observation_ids"][k] for k in ix] != source["observation_ids"]:
            raise ValueError("Native source index mismatch")
        corrected = {}
        for arm, (problem, x) in context["problems"].items():
            state = problem.state(x)
            whole = (
                track["values"]
                - scan.hardware(track, state["beta"])
                - track["rf_hz"]
                / 11.5e9
                * scan.rx_basis[source["track_index"]]
                @ state["smooth"][track["receiver"] - 1]
            )
            corrected[arm] = whole[ix]
        rows.append(
            dict(
                source=source,
                times_s=track["times"][ix],
                values_hz=track["values"][ix],
                corrected_hz=corrected,
            )
        )
    return dict(
        case=case,
        checks=context["replay_checks"],
        targets=rows,
        positions={a: x for a, (_, x) in context["problems"].items()},
        scan_receipt=scan_receipt,
        bank_domain_s=[float(min(scan.sky["time_s"])), float(max(scan.sky["time_s"]))],
    )
