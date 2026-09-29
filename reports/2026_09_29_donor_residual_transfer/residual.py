"""Training-centered residual shapes and matched causal donor slopes."""

import numpy as np


def shape(times, residual, mask):
    t, e, m = np.asarray(times), np.asarray(residual), np.asarray(mask, bool)
    if m.sum() < 5 or np.ptp(t[m]) < 5:
        return None
    tc = t[m].mean()
    ec = e[m].mean()
    z = t[m] - tc
    return dict(
        time_center=float(tc), residual_center=float(ec), slope=float(z @ (e[m] - ec) / (z @ z))
    )


def transfer(target, donors):
    grouped = {}
    for d in donors:
        if d["available_utc_ns"] >= target["start_utc_ns"]:
            continue
        if (d["receiver_id"], d["rf_hz"]) != (target["receiver_id"], target["rf_hz"]):
            continue
        grouped.setdefault(d["unit_id"], [[], []])[d["number"] != target["number"]].append(
            d["shape"]["slope"]
        )
    usable = {k: v for k, v in grouped.items() if v[0] and v[1]}
    if len(usable) < 2:
        return None
    candidate = [float(np.median(v[0])) for v in usable.values()]
    control = [float(np.median(v[1])) for v in usable.values()]
    return dict(
        groups=list(usable),
        candidate_group_slopes=candidate,
        control_group_slopes=control,
        candidate_slope=float(np.median(candidate)),
        control_slope=float(np.median(control)),
    )


def errors(target, slope):
    t = np.asarray(target["times"])
    e = np.asarray(target["residual"])
    m = np.asarray(target["mask"], bool)
    predicted = target["shape"]["residual_center"] + slope * (t - target["shape"]["time_center"])
    return dict(
        training_median_abs=float(np.median(abs((e - predicted)[m]))),
        held_median_abs=float(np.median(abs((e - predicted)[~m]))),
    )
