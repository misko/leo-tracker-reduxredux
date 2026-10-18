"""Consolidate supported identity proposals without discarding rejected joins.

One native-Hz constant bias is shared after a join. Its Gaussian integrated
score charges the extra independent biases before the join. Calibration and
identities are frozen inputs; this component does not learn either from lines.
"""

import numpy as np


def consolidate(
    segments,
    accept_residual,
    *,
    noise_hz=150.0,
    bias_sigma_hz=1000.0,
    max_gap_s=10.0,
    accept_joined_residual=None,
):
    """Join fixed identity proposals if all member residual checks pass.

    An optional additional check sees every member's residual, ordered in time,
    under the same constant. This can detect structure spanning short fragments.
    The callback is also applied to singletons for consistent diagnostics; no
    singleton is discarded if it fails. The default preserves historical fits.
    """
    if noise_hz <= 0 or bias_sigma_hz <= 0 or max_gap_s < 0:
        raise ValueError("positive noise/bias and nonnegative gap required")
    original_ids = [oid for s in segments for oid in s["observation_ids"]]
    if len(set(original_ids)) != len(original_ids):
        raise ValueError("duplicate observation ownership")
    bykey = {s["key"]: s for s in segments}
    if len(bykey) != len(segments):
        raise ValueError("duplicate segment keys")

    def fit(members):
        r = np.concatenate([bykey[k]["native_residual_hz"] for k in members])
        n = len(r)
        bias = float(r.sum() / (n + noise_hz**2 / bias_sigma_hz**2))
        cost = float(
            np.sum((r - bias) ** 2) / noise_hz**2
            + bias * bias / bias_sigma_hz**2
            + np.log1p(n * bias_sigma_hz**2 / noise_hz**2)
        )
        okay = all(
            accept_residual(
                np.asarray(bykey[k]["native_residual_hz"]) - bias, np.asarray(bykey[k]["time_s"])
            )
            for k in members
        )
        if okay and accept_joined_residual is not None:
            times = np.concatenate([bykey[k]["time_s"] for k in members])
            order = np.argsort(times, kind="stable")
            okay = bool(accept_joined_residual(r[order] - bias, times[order]))
        return dict(
            members=list(members),
            bias_hz=bias,
            cost=cost,
            points=n,
            candidate_norad=bykey[members[0]]["candidate_norad"],
            residual_check=okay,
        )

    groups = {key: fit([key]) for key in bykey}
    joins = []
    while True:
        best = None
        keys = list(groups)
        for i, a in enumerate(keys):
            left = groups[a]
            for b in keys[i + 1 :]:
                right = groups[b]
                if left["candidate_norad"] != right["candidate_norad"]:
                    continue
                ta = np.concatenate([bykey[k]["time_s"] for k in left["members"]])
                tb = np.concatenate([bykey[k]["time_s"] for k in right["members"]])
                gap = max(0.0, float(max(ta.min(), tb.min()) - min(ta.max(), tb.max())))
                if gap > max_gap_s:
                    continue
                joint = fit(left["members"] + right["members"])
                gain = left["cost"] + right["cost"] - joint["cost"]
                if joint["residual_check"] and gain > 0 and (best is None or gain > best[0]):
                    best = (gain, a, b, joint)
        if best is None:
            break
        gain, a, b, joint = best
        groups[a] = joint
        del groups[b]
        joins.append(dict(left=a, right=b, gain=gain, points=joint["points"]))
    retained = [
        oid
        for group in groups.values()
        for key in group["members"]
        for oid in bykey[key]["observation_ids"]
    ]
    if sorted(retained) != sorted(original_ids):
        raise RuntimeError("consolidation changed the associated observation population")
    return dict(
        input_tracks=len(segments),
        output_tracks=len(groups),
        points=len(original_ids),
        groups=list(groups.values()),
        joins=joins,
        identities_changed=False,
        points_dropped=0,
    )
