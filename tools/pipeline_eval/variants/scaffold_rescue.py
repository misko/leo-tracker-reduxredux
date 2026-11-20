"""Attach measured observations to a frozen stock Graph scaffold."""

from bisect import bisect_left
from collections import Counter, defaultdict
from math import isfinite, sqrt

import numpy as np
from numpy.polynomial.legendre import legval

BRACKET_S = 0.8
GATE_HZ = 450.0


def extend_noise(stock, attached):
    """Evaluate the existing margin law for new IDs and preserve every old weight."""
    observed = dict(stock["per_observation_noise_sigma_hz"])
    for point in attached:
        oid, margin = point["observation_id"], point["fractional_margin"]
        if oid in observed or not isfinite(margin) or margin <= 0:
            raise ValueError("only authentic positive new observations may extend fixed noise")
        sigma = stock["constant_radio_sigma_hz"]
        if "floor_sigma_hz" in stock:
            variance = stock["floor_sigma_hz"] ** 2 + stock["strength_hz2"] / margin
            sigma = sqrt(max(40**2, min(600**2, variance)))
        observed[oid] = sigma
    return dict(stock, per_observation_noise_sigma_hz=observed)


def candidate(track, t, measured, alias):
    times = track["times"]
    i = bisect_left(times, t)
    if (
        i == 0
        or i == len(times)
        or not (0 < t - times[i - 1] <= BRACKET_S and 0 < times[i] - t <= BRACKET_S)
    ):
        return None, "no_close_bracket"
    parts = [p for p in track["pieces"] if p["start_s"] <= t <= p["end_s"]]
    if len(parts) != 1:
        return None, "missing_single_piece"
    (piece,) = parts
    expected = legval(
        (t - piece["reference_time_s"]) / piece["time_scale_s"], piece["coefficients_hz"]
    )
    lift = round((expected - measured) / alias)
    value = measured + lift * alias
    residual = value - expected
    if abs(residual) > GATE_HZ:
        return None, "cfo_outside_gate"
    return dict(
        value_hz=value,
        lift=lift,
        residual_hz=float(residual),
        left_s=float(times[i - 1]),
        right_s=float(times[i]),
    ), "eligible"


def original_members(tracks):
    return {
        track["key"]: list(
            zip(
                track["observation_ids"],
                map(float, track["times"]),
                map(float, track["values"]),
                strict=True,
            )
        )
        for track in tracks
    }


def attach(prepared_tracks, lanes, donors, alias):
    """Change only member arrays of existing tracks, with each donor considered once."""
    tracks = prepared_tracks["tracks"]
    lookup = defaultdict(list)
    old = original_members(tracks)
    for track in tracks:
        (lane,) = {tuple(lanes[oid]) for oid in track["observation_ids"]}
        lookup[lane].append(track)
    observations = {x["observation_id"]: x for x in prepared_tracks["observations"]}
    if len(observations) != len(prepared_tracks["observations"]):
        raise ValueError("stock observation IDs are not unique")
    addition, decisions, census = defaultdict(list), [], Counter()
    seen = set(observations)
    for lane, observed in donors:
        oid, t, y = (observed[k] for k in ("observation_id", "time_s", "measured_cfo_hz"))
        if oid in seen or not (isfinite(t) and isfinite(y)) or not alias > 2 * GATE_HZ:
            raise ValueError("donor cannot be a stock member, duplicate, or ambiguous alias model")
        seen.add(oid)
        candidates = [
            (track["key"], *candidate(track, t, y, alias)) for track in lookup[tuple(lane)]
        ]
        matches = [(key, detail) for key, detail, _ in candidates if detail is not None]
        if len(matches) != 1:
            reason = (
                "ambiguous_tracks"
                if matches
                else next(
                    (
                        name
                        for name in ("cfo_outside_gate", "missing_single_piece")
                        if any(label == name for _, _, label in candidates)
                    ),
                    "no_close_bracket",
                )
            )
            census[reason] += 1
            continue
        key, detail = matches[0]
        observations[oid] = observed
        addition[key].append((oid, t, detail["value_hz"]))
        decisions.append(dict(id=oid, track=key, time_s=t, raw_cfo_hz=y, **detail))
        census["attached"] += 1

    augmented = []
    for track in tracks:
        key = track["key"]
        if key not in addition:
            augmented.append(track)
            continue
        joined = sorted(old[key] + addition[key], key=lambda row: row[1])
        ids, time, values = zip(*joined, strict=True)
        if any(b <= a for a, b in zip(time, time[1:], strict=False)):
            raise ValueError("duplicate timestamp in fixed track")
        augmented.append(
            dict(track, observation_ids=list(ids), times=np.array(time), values=np.array(values))
        )
    evidence = original_members(augmented)
    added_ids = {d["id"] for d in decisions}
    if {
        key: [x for x in members if x[0] not in added_ids] for key, members in evidence.items()
    } != old:
        raise ValueError("stock track ownership, timestamp, or lifted branch changed")
    if any(observations[x["observation_id"]] != x for x in prepared_tracks["observations"]):
        raise ValueError("original raw CFO or other observation field changed")
    new = dict(
        prepared_tracks,
        tracks=augmented,
        graph_points=prepared_tracks["graph_points"] + len(decisions),
        observations=sorted(
            observations.values(),
            key=lambda r: (r["receiver"], r["channel"], r["time_s"], r["observation_id"]),
        ),
    )
    return new, dict(
        census=dict(census),
        attachments=decisions,
        stock_members=sum(map(len, old.values())),
        stock_observations=len(prepared_tracks["observations"]),
        stock_groups=len(tracks),
        stock_curvature_keys=[tracks[i]["key"] for i in prepared_tracks["curved_indices"]],
    )
