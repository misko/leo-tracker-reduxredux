import numpy as np

PERIOD = 1 / 4.4e-6


def wrap(values):
    return (np.asarray(values) + PERIOD / 2) % PERIOD - PERIOD / 2


def circular_median(values):
    values = np.sort(wrap(values))
    assert len(values) > 0 and np.isfinite(values).all()
    cost = np.sum(abs(wrap(values[:, None] - values[None, :])), axis=1)
    return float(values[np.argmin(cost)])


def predict(target, candidates, opposite=False):
    groups = {}
    for row in candidates:
        if row["session_id"] != target["session_id"] or row["rf_hz"] != target["rf_hz"]:
            continue
        if (row["receiver_id"] != target["receiver_id"]) != opposite:
            continue
        if row["track_id"] == target["track_id"] or row["number"] == target["number"]:
            continue
        groups.setdefault(row["number"], []).append(row["native_offset_hz"])
    if len(groups) < 3:
        return None
    values = [circular_median(v) for _, v in sorted(groups.items())]
    center = circular_median(values)
    return dict(
        offset_hz=center,
        donor_numbers=sorted(groups),
        donor_offsets_hz=values,
        donor_median_deviation_hz=float(np.median(abs(wrap(np.asarray(values) - center)))),
    )
