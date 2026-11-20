"""Create auditable diagnostic factor swaps from reciprocal native candidate matches."""

from collections import Counter
from math import isfinite

from .full_v5_check import ALIAS_HZ, CFO_TOLERANCE_HZ, EPOCH_TOLERANCE_SAMPLES, FRAME_HZ

SCORE = (
    "fractional_exact_score",
    "fractional_control_score",
    "fractional_margin",
    "passed_fractional_margin_gate",
)
CFO = "fractional_tracking_cfo_hz"
RANK = "candidate_rank"
MARGIN = "fractional_margin"
GATE = "passed_fractional_margin_gate"
TREATMENTS = ("score", "cfo", "both")


def wrapped(delta, period):
    return delta - round(delta / period) * period


def _coordinates(candidates):
    if len({row[RANK] for row in candidates}) != len(candidates):
        raise ValueError("duplicate native candidate rank")
    entries = [
        (r["integer_epoch_sample"] + r["fractional_epoch_offset_samples"], r[CFO])
        for r in candidates
    ]
    if any(not isfinite(v) for pair in entries for v in pair):
        raise ValueError("native candidate has a nonfinite epoch or CFO")
    return entries


def matches(left, right, frame_samples):
    """Return index pairs and complete graph degrees without reading marks or ranks for matching."""
    aa, bb = _coordinates(left), _coordinates(right)
    edges_a, edges_b = [[] for _ in aa], [[] for _ in bb]
    for i, (t_a, f_a) in enumerate(aa):
        for j, (t_b, f_b) in enumerate(bb):
            if abs(wrapped(t_b - t_a, frame_samples)) > EPOCH_TOLERANCE_SAMPLES:
                continue
            if abs(wrapped(f_b - f_a, ALIAS_HZ)) <= CFO_TOLERANCE_HZ:
                edges_a[i].append(j)
                edges_b[j].append(i)
    pairs = [
        (i, edges[0])
        for i, edges in enumerate(edges_a)
        if len(edges) == 1 and len(edges_b[edges[0]]) == 1
    ]
    return pairs, ([len(a) for a in edges_a], [len(b) for b in edges_b])


def winner(candidates):
    """Mirror native track preparation's one winning gate-passing candidate per probe."""
    return max(
        (i for i, c in enumerate(candidates) if c[GATE] is True),
        key=lambda i: (candidates[i][MARGIN], -candidates[i][RANK]),
        default=None,
    )


def assess(capture, ordinary):
    a, b = (d["source"]["probes"] for d in (capture, ordinary))
    rate = capture["source"]["sample_rate_hz"]
    if rate != ordinary["source"]["sample_rate_hz"]:
        raise ValueError("different detector sample rates")
    rows, counts = [], Counter()
    for i, (pa, pb) in enumerate(zip(a, b, strict=True)):
        if {k: v for k, v in pa.items() if k != "candidates"} != {
            k: v for k, v in pb.items() if k != "candidates"
        }:
            raise ValueError("crossing factors requires identical probe support")
        left, right = (p["candidates"] for p in (pa, pb))
        pairs, degrees = matches(left, right, round(rate / FRAME_HZ))
        if pairs:
            rows.append([i, pairs])
        for side, candidates, degree, indices in zip(
            ("capture_era", "ordinary"),
            (left, right),
            degrees,
            (dict(pairs), {j: i for i, j in pairs}),
            strict=True,
        ):
            best = winner(candidates)
            counts[f"{side}_total"] += len(degree)
            counts[f"{side}_no_edge"] += degree.count(0)
            counts[f"{side}_ambiguous_unmatched"] += sum(d > 0 for d in degree) - len(indices)
            counts[f"{side}_winning_probes"] += best is not None
            counts[f"{side}_matched_winners"] += best in indices
            counts[f"{side}_gate_passes"] += sum(c[GATE] for c in candidates)
            counts[f"{side}_matched_gate_passes"] += sum(candidates[j][GATE] for j in indices)
        counts["matched_pairs"] += len(pairs)
        counts["multi_edge_probes"] += any(d > 1 for side in degrees for d in side)
        for first_index, second_index in pairs:
            ca, cb = left[first_index], right[second_index]
            counts[f"gate_{int(ca[GATE])}{int(cb[GATE])}"] += 1
            counts["cross_alias_pairs"] += round((cb[CFO] - ca[CFO]) / ALIAS_HZ) != 0
            counts["same_rank_pairs"] += ca[RANK] == cb[RANK]
    return rows, dict(counts)


def interchange(recipient, donor, rows, treatment, *, reverse):
    """Preserve roster, epoch and rank. Only the documented matched fields change."""
    if treatment not in TREATMENTS:
        raise ValueError("unknown crossed field family")
    probes = recipient["source"]["probes"].copy()
    theirs = donor["source"]["probes"]
    stats = Counter()
    for index, pairs in rows:
        probe = probes[index]
        ours = probe["candidates"].copy()
        entering = winner(ours)
        for a, b in pairs:
            target, source = (b, a) if reverse else (a, b)
            base = ours[target]
            from_donor = theirs[index]["candidates"][source]
            updated = dict(base)
            if treatment in ("score", "both"):
                updated.update((k, from_donor[k]) for k in SCORE)
                stats["changed_gate_flags"] += updated[GATE] != base[GATE]
            if treatment in ("cfo", "both"):
                shift = round((from_donor[CFO] - base[CFO]) / ALIAS_HZ)
                updated[CFO] = from_donor[CFO] - shift * ALIAS_HZ
                stats["changed_cfo_measurements"] += updated[CFO] != base[CFO]
            ours[target] = updated
        after = winner(ours)
        stats["winner_added"] += entering is None and after is not None
        stats["winner_lost"] += entering is not None and after is None
        stats["winner_switched"] += entering is not None and after is not None and entering != after
        stats["changed_winning_measurement"] += (
            after is not None
            and entering is not None
            and ours[after][CFO] != probe["candidates"][entering][CFO]
        )
        probes[index] = dict(probe, candidates=ours)
    return dict(recipient, source=dict(recipient["source"], probes=probes)), dict(stats)
