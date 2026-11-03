"""CFO-blind metadata and exact role/group checks, independent of new math."""

from types import SimpleNamespace

import numpy as np


def metadata_only(rows, *, dummy_cfo=0.0):
    """Only known prediction metadata is consumed, never measured CFO/labels."""
    return SimpleNamespace(
        window_ids=tuple(r["observation_id"] for r in rows),
        times_s=np.array([r["time_s"] for r in rows]),
        measured_hz=np.full(len(rows), dummy_cfo),
        rf_hz=np.array([r["actual_rf_hz"] for r in rows]),
        receiver=np.array([r["receiver"] - 1 for r in rows]),
        channel=np.array([r["channel"] for r in rows]),
        margin=np.ones(len(rows)),
    )


def role_masks(ids, membership):
    roles = {r["global_group_id"]: r["role"] for r in membership}
    if len(roles) != len(membership):
        raise ValueError("Unique role authority required")
    masks = {
        role: np.array([roles[key] == role for key in ids])
        for role in ("train", "held", "boundary")
    }
    if not np.all(sum(m.astype(int) for m in masks.values()) == 1):
        raise ValueError("Every original row requires exactly one declared role")
    return masks


def partition(labels, observations):
    labels = np.asarray(labels)
    if labels.shape != (len(observations.times_s),) or not np.issubdtype(labels.dtype, np.integer):
        raise ValueError("One integer TRAIN label per row required")
    unique, counts = np.unique(labels, return_counts=True)
    if not np.array_equal(unique, np.arange(len(unique))):
        raise ValueError("Contiguous complete partition required")
    lanes = []
    for label in unique:
        use = labels == label
        lane = {
            (int(r), int(c), float(f))
            for r, c, f in zip(
                observations.receiver[use],
                observations.channel[use],
                observations.rf_hz[use],
                strict=True,
            )
        }
        if len(lane) != 1:
            raise ValueError("Group crosses receiver/channel/RF lane")
        lanes.append(next(iter(lane)))
    return dict(
        groups=len(unique),
        rows=len(labels),
        lengths=counts,
        lanes=lanes,
        maximum_length=int(counts.max(initial=0)),
        all_rows_once=int(counts.sum()) == len(labels),
    )


def same_predictions(a, b):
    if set(a) != set(b):
        raise ValueError("Prediction inventory changed")
    for key in a:
        np.testing.assert_array_equal(a[key], b[key])
