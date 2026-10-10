"""Pure zero-correlation score and acquisition-only pairing; no fitted rho."""

from collections import Counter, defaultdict

import numpy as np


def pair_rows(rows, maximum_gap_ns=2_000_000_000):
    """Return disjoint indices; retain every unsupported/overlapping row unpaired.

    Caller supplies exact public support UTC, actual RF Hz, edge and a canonical
    acquisition identity of capture/stream/RX/start/end sample counters. Visit ID
    alone is not an acquisition identity; disjoint windows in one visit differ.
    """
    if maximum_gap_ns <= 0:
        raise ValueError("Positive gap required")
    ids = [r["window_id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate observation window IDs")
    reasons, receivers = {}, defaultdict(list)
    acquisitions = defaultdict(list)
    for index, row in enumerate(rows):
        if (
            not isinstance(row.get("edge"), str)
            or not row["edge"]
            or not np.isfinite(row.get("actual_rf_hz", np.nan))
            or row["actual_rf_hz"] <= 0
        ):
            raise ValueError("Exact RF and edge identity required")
        fields = ("support_start_ns", "support_center_ns", "support_end_ns", "acquisition_id")
        if any(row.get(name) is None for name in fields):
            reasons[index] = "missing-support"
            continue
        start, center, end = [row[name] for name in fields[:3]]
        if not all(isinstance(v, int) for v in (start, center, end)) or not start <= center < end:
            raise ValueError("Invalid acquisition support")
        if not row["acquisition_id"]:
            raise ValueError("Empty acquisition identity")
        acquisitions[row["receiver"], row["acquisition_id"]].append(index)
        receivers[row["receiver"]].append(index)
    for matches in acquisitions.values():
        if len(matches) > 1:
            for index in matches:
                reasons[index] = "repeated-acquisition"
    # Any interval overlap on a receiver flags both rows, even across channels.
    for indices in receivers.values():
        ordered = sorted(indices, key=lambda i: (rows[i]["support_start_ns"], ids[i]))
        furthest = None
        for index in ordered:
            if (
                furthest is not None
                and rows[index]["support_start_ns"] < rows[furthest]["support_end_ns"]
            ):
                for i in (index, furthest):
                    reasons.setdefault(i, "overlapping-support")
            if furthest is None or rows[index]["support_end_ns"] > rows[furthest]["support_end_ns"]:
                furthest = index
    groups = defaultdict(list)
    for index, row in enumerate(rows):
        if index not in reasons:
            groups[row["receiver"], row["channel"], row["actual_rf_hz"], row["edge"]].append(index)
    pairs = []
    for group in sorted(groups):
        ordered = sorted(groups[group], key=lambda i: (rows[i]["support_center_ns"], ids[i]))
        cursor = 0
        while cursor < len(ordered):
            first = ordered[cursor]
            if cursor + 1 < len(ordered):
                second = ordered[cursor + 1]
                gap = rows[second]["support_center_ns"] - rows[first]["support_center_ns"]
                if 0 < gap <= maximum_gap_ns:
                    pairs.append((first, second))
                    cursor += 2
                    continue
            reasons[first] = "no-close-neighbour"
            cursor += 1
    paired = {i for pair in pairs for i in pair}
    if len(paired) != 2 * len(pairs) or paired | set(reasons) != set(range(len(rows))):
        raise AssertionError("Pairing lost or reused observations")
    return dict(
        pairs=pairs,
        unpaired=[dict(index=i, reason=reasons[i]) for i in sorted(reasons)],
        reason_counts=dict(Counter(reasons.values())),
        observations=len(rows),
    )


def zero_score(responsibilities, standardized_winding_means, pairs):
    """Exact derivative at independence for supplied wrapped component moments.

    Narrow-density nearest residual/sigma is an approximation the caller must
    qualify. Responsibilities exclude clutter and sum to at most1 per row.
    """
    weights, z = np.asarray(responsibilities, float), np.asarray(standardized_winding_means, float)
    if (
        weights.ndim != 2
        or not weights.shape[1]
        or z.shape != weights.shape
        or not np.isfinite(weights).all()
        or not np.isfinite(z).all()
        or np.any(weights < 0)
        or np.any(weights > 1)
        or np.any(weights.sum(axis=1) > 1 + 1e-12)
    ):
        raise ValueError("Invalid soft responsibilities or standardized moments")
    raw_indices = np.asarray(pairs)
    if raw_indices.size and raw_indices.dtype.kind not in "iu":
        raise ValueError("Pair indices must be integers")
    indices = raw_indices.astype(int)
    if not len(indices):
        return dict(
            pair_scores=[],
            shared_label_mass=[],
            score_sum=0.0,
            pair_count=0,
            unpaired_count=len(weights),
        )
    if (
        indices.shape != (len(indices), 2)
        or np.any(indices < 0)
        or np.any(indices >= len(weights))
        or len(set(indices.ravel())) != indices.size
    ):
        raise ValueError("Pair indices must be disjoint valid observations")
    joint = weights[indices[:, 0]] * weights[indices[:, 1]]
    scores = np.sum(joint * z[indices[:, 0]] * z[indices[:, 1]], axis=1)
    if not np.isfinite(scores).all():
        raise ValueError("Nonfinite zero-correlation score")
    return dict(
        pair_scores=scores.tolist(),
        shared_label_mass=joint.sum(axis=1).tolist(),
        score_sum=float(scores.sum()),
        pair_count=len(indices),
        unpaired_count=len(weights) - indices.size,
    )
