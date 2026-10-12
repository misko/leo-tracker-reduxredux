"""Orbit-blind track proposals initialize shared receiver/band calibration.

The supplied tracks are frozen from measured GLRT timing/frequency evidence.
Their shape matches propose starts only; all original candidate-set factors enter
the later likelihood. No location reference errors or winning satellite labels
are accepted by this interface.
"""

import numpy as np

from leo.analysis.wrapped_glrt_likelihood import PILOT_ALIAS_HZ, circular


def shape_seeds(evidence, prediction, opportunity, tracks, *, maximum_satellites=40):
    groups = int(evidence.group.max()) + 1
    center = (evidence.time_s.min() + evidence.time_s.max()) / 2
    span = max(1.0, (evidence.time_s.max() - evidence.time_s.min()) / 2)
    strongest = evidence.frequency_hz[
        np.arange(len(evidence.ids)), evidence.candidate_weight.argmax(axis=1)
    ]
    proposals = []
    for track in tracks:
        rows = np.asarray(track, int)
        if (
            rows.ndim != 1
            or len(rows) < 6
            or len(np.unique(rows)) != len(rows)
            or rows.min() < 0
            or rows.max() >= len(evidence.ids)
            or len(np.unique(evidence.group[rows])) != 1
            or np.any(np.diff(evidence.time_s[rows]) <= 0)
        ):
            raise ValueError("time-ordered one-lane track rows required")
        take = np.unique(np.linspace(0, len(rows) - 1, min(18, len(rows))).astype(int))
        frequency = (
            np.unwrap(strongest[rows] * 2 * np.pi / PILOT_ALIAS_HZ) * PILOT_ALIAS_HZ / (2 * np.pi)
        )
        sampled = rows[take]
        times = evidence.time_s[sampled]
        dt = times - times.mean()
        residual = frequency[take, None] - prediction[sampled]
        slope = np.clip(dt @ residual / max(1.0, np.dot(dt, dt)), -5.0, 5.0)
        adjusted = residual - dt[:, None] * slope
        intercept = np.median(adjusted, axis=0)
        centered = residual - intercept - dt[:, None] * slope
        rms = np.sqrt(np.mean(centered**2, axis=0))
        cost = np.mean(2 * 200.0**2 * (np.sqrt(1 + (centered / 200.0) ** 2) - 1), axis=0)
        cost[np.mean(opportunity[sampled], axis=0) < 0.8] = np.inf
        for sat in np.argsort(cost)[:3]:
            if not np.isfinite(cost[sat]) or rms[sat] > 750:
                continue
            offset = circular(intercept[sat] - slope[sat] * (times.mean() - center))
            proposals.append(
                dict(
                    group=int(evidence.group[rows[0]]),
                    satellite=int(sat),
                    offset_hz=float(offset),
                    drift_hz_s=float(slope[sat]),
                    rms_hz=float(rms[sat]),
                    support=len(rows),
                    span_s=float(np.ptp(times)),
                    weight=float(min(len(rows), 100) / (50 + rms[sat]) ** 2),
                )
            )
    if not proposals:
        raise ValueError("no plausible orbit-shape bootstrap matches")
    bins = np.linspace(-PILOT_ALIAS_HZ / 2, PILOT_ALIAS_HZ / 2, 457)
    modes = []
    for group in range(groups):
        matches = [x for x in proposals if x["group"] == group]
        if not matches:
            raise ValueError(f"no bootstrap track matches for band group {group}")
        hist = np.histogram(
            [x["offset_hz"] for x in matches], bins, weights=[x["weight"] for x in matches]
        )[0]
        smooth = np.convolve(hist, [1, 2, 3, 2, 1], mode="same")
        chosen = []
        for i in np.argsort(smooth)[::-1]:
            if all(abs(i - j) > 8 for j in chosen):
                chosen.append(int(i))
            if len(chosen) == 2:
                break
        modes.append([(bins[i] + bins[i + 1]) / 2 for i in chosen])
    seeds = []
    for mode in (0, 1):
        offsets = [row[mode] for row in modes]
        relevant = [
            x for x in proposals if abs(circular(x["offset_hz"] - offsets[x["group"]])) < 2500
        ]
        slopes = []
        for rx in range(groups // 2):
            matches = [x for x in relevant if x["group"] // 2 == rx]
            slopes.append(
                float(
                    np.average(
                        [x["drift_hz_s"] for x in matches], weights=[x["weight"] for x in matches]
                    )
                )
                if matches
                else 0.0
            )
        mass = {}
        for match in relevant:
            mass[match["satellite"]] = mass.get(match["satellite"], 0) + match["weight"]
        active = sorted(mass, key=lambda s: (-mass[s], s))[:maximum_satellites]
        seeds.append(dict(beta=offsets + (np.array(slopes) * span).tolist(), active=active))
    return seeds, proposals
