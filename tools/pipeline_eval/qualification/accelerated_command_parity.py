"""Compare original and accelerated native detector fields and candidate order."""

from collections import Counter

import numpy as np
from scipy.optimize import linear_sum_assignment

from ..__main__ import encoded

PROBE = ("visit_index", "receiver_id", "probe_index", "probe_start_ms")
PIECE = ("schema_version", "clock_anchor", "delivery_clocks", "last_sample_counter")
SUPPORT = (
    "excluded_windows",
    "invalid_capture",
    "processed_windows",
    "rf_mapping_authorities",
    "skipped_fast_score",
    "window_count",
)
ALIAS = 1 / 4.4e-6
CFO_TOLERANCE_HZ = 250
EPOCH_TOLERANCE_SAMPLES = 0.5


def key(row):
    return tuple(row[k] for k in PROBE)


def discrete_axis(candidate):
    integer = candidate["integer_epoch_sample"]
    offset = candidate["fractional_epoch_offset_samples"]
    cfo = candidate["fractional_tracking_cfo_hz"]
    return float(integer + offset) if offset is not None else float(integer), cfo


def correspondent(left, right):
    """Match physical peaks within fixed time and aliased-CFO tolerances."""
    if not left or not right:
        return []
    candidate_axes, original_axes = (list(map(discrete_axis, side)) for side in (left, right))
    cost = np.full((len(left), len(right)), 100.0)
    valid = np.zeros(cost.shape, dtype=bool)
    for i, (t, f) in enumerate(candidate_axes):
        for j, (u, g) in enumerate(original_axes):
            if f is None or g is None:
                if f != g:
                    continue
                df = 0
            else:
                df = abs((f - g + ALIAS / 2) % ALIAS - ALIAS / 2)
            dt = abs(t - u)
            if df <= CFO_TOLERANCE_HZ and dt <= EPOCH_TOLERANCE_SAMPLES:
                cost[i, j] = dt / EPOCH_TOLERANCE_SAMPLES + df / CFO_TOLERANCE_HZ
                cost[i, j] += 1e-9 * abs(i - j)
                valid[i, j] = True
    a, b = linear_sum_assignment(cost)
    return [(int(i), int(j)) for i, j in zip(a, b, strict=True) if valid[i, j]]


def differs(a, b):
    return [
        k
        for k in sorted(a.keys() | b.keys())
        if k not in a or k not in b or encoded(a[k]) != encoded(b[k])
    ]


def compare(measured, archive):
    a, b = (doc["source"]["probes"] for doc in (measured, archive))
    lhs, rhs = ({key(r): r for r in z} for z in (a, b))
    if len(lhs) != len(a) or len(rhs) != len(b):
        raise ValueError("duplicated physical probe identity")
    physical, source, scope = (
        [k for k in keys if encoded(x.get(k)) != encoded(y.get(k))]
        for x, y, keys in (
            (measured, archive, PIECE),
            (
                measured["source"],
                archive["source"],
                measured["source"].keys() | archive["source"].keys(),
            ),
            (measured["provenance"], archive["provenance"], SUPPORT),
        )
    )
    source = sorted(set(source) - {"probes", "analysis_manifest_sha256"})
    changes, field_count, paired_count = [], Counter(), Counter()
    gates = Counter(
        matched_gate_changed=0, unmatched_measured_passing=0, unmatched_archived_passing=0
    )
    ranks = Counter(
        matched_rank_changed=0,
        probes_with_rank_changes=0,
        probes_with_reordered_matches=0,
        unmatched_measured=0,
        unmatched_archived=0,
        top_peak_changed=0,
    )
    positional_max, matched_max, numeric_values = {}, {}, {}
    shared = lhs.keys() & rhs.keys()
    for name in sorted(shared):
        left, right = lhs[name], rhs[name]
        exact = encoded(left) == encoded(right)
        x, y = left["candidates"], right["candidates"]
        mask = [tuple(c["passed_fractional_margin_gate"] for c in group) for group in (x, y)]
        gates.update(
            dict(
                measured=sum(mask[0]),
                archived=sum(mask[1]),
                measured_probes=bool(any(mask[0])),
                archived_probes=bool(any(mask[1])),
                probe_decision_changed=any(mask[0]) != any(mask[1]),
                gate_sequence_changed=mask[0] != mask[1],
            )
        )
        physical_fields = sorted(set(differs(left, right)) - {"candidates"})
        order = [tuple(c["candidate_rank"] for c in group) for group in (x, y)]
        ranks["rank_id_sequence_changed"] += order[0] != order[1]
        ranks["candidate_count_changed"] += len(x) != len(y)
        if exact:
            ranks["matched_candidates"] += len(x)
            paired_count["exact_probes"] += 1
            continue
        paired_count["different_probes"] += 1
        rows = correspondent(x, y)
        ix, iy = ({p[i] for p in rows} for i in (0, 1))
        moved = sum(x[i]["candidate_rank"] != y[j]["candidate_rank"] for i, j in rows)
        reordered = sum(i > k and j < m for i, j in rows for k, m in rows)
        first = (0, 0) not in rows and bool(x or y)
        ranks.update(
            dict(
                matched_candidates=len(rows),
                matched_rank_changed=moved,
                probes_with_rank_changes=bool(moved),
                probes_with_reordered_matches=bool(reordered),
                unmatched_measured=len(x) - len(rows),
                unmatched_archived=len(y) - len(rows),
                top_peak_changed=first,
            )
        )
        gates["matched_gate_changed"] += sum(mask[0][i] != mask[1][j] for i, j in rows)
        gates["unmatched_measured_passing"] += sum(v and i not in ix for i, v in enumerate(mask[0]))
        gates["unmatched_archived_passing"] += sum(v and i not in iy for i, v in enumerate(mask[1]))
        fields = set()
        for f, g in zip(x, y, strict=False):
            seen = differs(f, g)
            fields.update(seen)
            field_count.update(seen)
            metrics(f, g, seen, positional_max)
        for i, j in rows:
            fields_matched = differs(x[i], y[j])
            metrics(x[i], y[j], fields_matched, matched_max, numeric_values)
        if len(x) != len(y):
            field_count["candidate_count"] += 1
        changes.append(
            dict(
                probe=name,
                physical_fields=physical_fields,
                candidate_fields=sorted(fields),
                candidate_counts=[len(x), len(y)],
                positional_rank_sequence=order,
                matched_physical_indices=rows,
                moved_rank_count=moved,
                reordered_pairs=reordered,
                top_peak_unmatched_or_replaced=first,
            )
        )
    pair = dict(
        schema_and_clock_fields_changed=physical,
        source_physical_fields_changed=source,
        exclusion_and_authority_fields_changed=scope,
        probe_order_exact=list(lhs) == list(rhs),
        unmatched_measured_probes=sorted(lhs.keys() - rhs.keys()),
        unmatched_archived_probes=sorted(rhs.keys() - lhs.keys()),
        physical_probe_metadata_changes=sum(bool(p["physical_fields"]) for p in changes),
        measured_probes=len(a),
        archived_probes=len(b),
        measured_candidates=sum(len(p["candidates"]) for p in a),
        archived_candidates=sum(len(p["candidates"]) for p in b),
        exact_probes=paired_count["exact_probes"],
        different_probes=paired_count["different_probes"],
        field_differences=dict(field_count),
        maximum_rank_position_delta=positional_max,
        maximum_matched_peak_delta=matched_max,
        matched_nonidentical_delta_p95={
            k: float(np.percentile(v, 95)) for k, v in numeric_values.items()
        },
        gate_counts=dict(gates),
        rank_counts=dict(ranks),
        physical_match_tolerances=dict(
            cfo_hz=CFO_TOLERANCE_HZ, epoch_samples=EPOCH_TOLERANCE_SAMPLES, alias_hz=ALIAS
        ),
    )
    return pair, changes


def metrics(a, b, fields, maximum, distribution=None):
    for k in fields:
        left, right = a.get(k), b.get(k)
        if type(left) not in (float, int) or type(right) not in (float, int):
            continue
        value = abs(left - right)
        maximum[k] = max(maximum.get(k, 0), value)
        if distribution is not None:
            distribution.setdefault(k, []).append(value)
