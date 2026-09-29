"""Training-only cross-RX pairing and conditional frequency-difference diagnostics."""

import math

import numpy as np

SIGMA = 100 * math.sqrt(2)


def log_density(residual, scale=SIGMA):
    r = np.asarray(residual, dtype=float)
    return (
        math.lgamma(2.5)
        - math.lgamma(2)
        - 0.5 * math.log(4 * math.pi)
        - math.log(scale)
        - 2.5 * np.log1p((r / scale) ** 2 / 4)
    )


def match(a, b, tolerance=0.001):
    """Retain only isolated timestamp/visit edges; never use frequency to match."""
    ta, tb = np.asarray(a["times_s"]), np.asarray(b["times_s"])
    va, vb = np.asarray(a["visits"]), np.asarray(b["visits"])
    edges = (va[:, None] == vb[None, :]) & (abs(ta[:, None] - tb[None, :]) <= tolerance)
    unique = edges & (edges.sum(axis=1)[:, None] == 1) & (edges.sum(axis=0)[None, :] == 1)
    i, j = np.nonzero(unique)
    return i, j, int(edges.sum() - unique.sum())


def describe(a, b):
    i, j, ambiguous = match(a, b)
    ma, mb = np.asarray(a["training_mask"], bool), np.asarray(b["training_mask"], bool)
    training = ma[i] & mb[j]
    held = ~ma[i] & ~mb[j]
    t = np.asarray(a["times_s"])[i]
    y0, y1 = np.asarray(a["measured_hz"])[i], np.asarray(b["measured_hz"])[j]
    difference = y0 - y1
    n = int(training.sum())
    span = float(np.ptp(t[training])) if n else 0.0
    eligible = n >= 5 and span >= 5
    offset = float(np.median(difference[training])) if eligible else None
    residual = difference[training] - offset if eligible else np.array([])
    median = float(np.median(abs(residual))) if eligible else None
    p90 = float(np.quantile(abs(residual), 0.9)) if eligible else None
    return {
        "rx0": a["track_id"],
        "rx1": b["track_id"],
        "channel": a["channel"],
        "rf_hz": a["rf_hz"],
        "rx0_indices": i.tolist(),
        "rx1_indices": j.tolist(),
        "training": training.tolist(),
        "held": held.tolist(),
        "times_s": t.tolist(),
        "difference_hz": difference.tolist(),
        "rx0_hz": y0.tolist(),
        "rx1_hz": y1.tolist(),
        "ambiguous_edges": ambiguous,
        "mixed_matches": int((~training & ~held).sum()),
        "rx0_unmatched": len(a["times_s"]) - len(i),
        "rx1_unmatched": len(b["times_s"]) - len(j),
        "training_count": n,
        "training_span_s": span,
        "eligible": eligible,
        "offset_hz": offset,
        "training_median_abs_hz": median,
        "training_p90_abs_hz": p90,
        "training_mean_log_density": float(log_density(residual).mean()) if eligible else None,
        "passes_shape": bool(eligible and median <= 100 and p90 <= 300),
    }


def select(pairs):
    """Reciprocal best eligible edges, with a .1-nat/observation ambiguity margin."""
    eligible = [p for p in pairs if p["eligible"]]
    for p in pairs:
        p["selected"] = False
        p["margins_nats_per_observation"] = {}
        if not p["eligible"]:
            continue
        best = True
        for side in ("rx0", "rx1"):
            others = [q for q in eligible if q is not p and q[side] == p[side]]
            margin = (
                p["training_mean_log_density"] - max(q["training_mean_log_density"] for q in others)
                if others
                else None
            )
            p["margins_nats_per_observation"][side] = margin
            best &= margin is None or margin >= 0.1
        p["selected"] = bool(best and p["passes_shape"])
    chosen = [p for p in pairs if p["selected"]]
    assert len({p["rx0"] for p in chosen}) == len({p["rx1"] for p in chosen}) == len(chosen)
    return chosen


def score(pair, donors):
    held = np.asarray(pair["held"], bool)
    training = np.asarray(pair["training"], bool)
    times = np.asarray(pair["times_s"])
    y0, y1 = np.asarray(pair["rx0_hz"]), np.asarray(pair["rx1_hz"])
    n = int(held.sum())
    span = float(np.ptp(times[held])) if n else 0.0
    available = n >= 3 and span >= 5
    result = {"held_count": n, "held_span_s": span, "held_available": available}
    if not available:
        return result
    delta = y0[held] - y1[held]
    residual = delta - pair["offset_hz"]
    actual = float(log_density(residual).sum())
    reverse_offset = float(np.median(y0[training] - y1[training][::-1]))
    reverse_residual = y0[held] - y1[held][::-1] - reverse_offset
    result.update(
        held_median_abs_hz=float(np.median(abs(residual))),
        held_p90_abs_hz=float(np.quantile(abs(residual), 0.9)),
        held_offset_shift_hz=float(np.median(delta) - pair["offset_hz"]),
        held_log_density=actual,
        narrow_minus_broad_nats=actual - float(log_density(residual, 2000).sum()),
        actual_minus_reversed_nats=actual - float(log_density(reverse_residual).sum()),
        held_shape_pass=bool(
            np.median(abs(residual)) <= 100 and np.quantile(abs(residual), 0.9) <= 300
        ),
        donor_count=len(donors),
    )
    if len(donors) >= 2:
        common = float(np.median([d["offset_hz"] for d in donors]))
        shared = delta - common
        result.update(
            donor_offset_hz=common,
            donor_held_median_abs_hz=float(np.median(abs(shared))),
            donor_held_p90_abs_hz=float(np.quantile(abs(shared), 0.9)),
            donor_held_shape_pass=bool(
                np.median(abs(shared)) <= 100 and np.quantile(abs(shared), 0.9) <= 300
            ),
            donor_minus_own_nats=float(log_density(shared).sum()) - actual,
        )
    return result


def analyze(document):
    tracks = document["tracks"]
    assert len({t["track_id"] for t in tracks}) == len(tracks)
    for t in tracks:
        assert t["receiver_id"] in (0, 1)
        assert len({len(t[k]) for k in ("times_s", "measured_hz", "training_mask", "visits")}) == 1
        assert np.isfinite(t["times_s"]).all() and np.isfinite(t["measured_hz"]).all()
        assert np.all(np.diff(t["times_s"]) >= 0)
    pairs = [
        describe(a, b)
        for a in tracks
        if a["receiver_id"] == 0
        for b in tracks
        if b["receiver_id"] == 1 and a["channel"] == b["channel"] and a["rf_hz"] == b["rf_hz"]
    ]
    chosen = select(pairs)
    for p in chosen:
        donors = [
            q
            for q in chosen
            if q is not p and q["channel"] == p["channel"] and q["rf_hz"] == p["rf_hz"]
        ]
        p["evaluation"] = score(p, donors)
    return {"session_id": document["session_id"], "tracks": len(tracks), "pairs": pairs}
