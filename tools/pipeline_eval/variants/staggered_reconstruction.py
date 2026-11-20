"""Reconstruct one fifth-region physical lane from two complete detector parents."""

from collections import Counter
from hashlib import sha256

from .selective_capture import same_support, visit_pairs
from .staggered_native import RfStagger

POLICY = "one-fifth-lane-valid-order-per-recorded-rf-v1"


def winner(probe):
    return max(
        (c for c in probe["candidates"] if c["passed_fractional_margin_gate"] is True),
        key=lambda c: (c["fractional_margin"], -c["candidate_rank"]),
        default=None,
    )


def assemble(stock, fifth, rf_centers, encode):
    """Copy an entire verified physical packet from the selected parent on each lane."""
    same_support(stock, fifth)
    left, right = (d["source"] for d in (stock, fifth))
    left_meta, right_meta = (
        {k: v for k, v in s.items() if k not in {"probes", "analysis_manifest_sha256"}}
        for s in (left, right)
    )
    if left_meta != right_meta or left_meta.get("qualified") is not True:
        raise ValueError("detector sources have different capture or sample metadata")
    old_stats, new_stats = (d["provenance"] for d in (stock, fifth))
    same_keys = ("window_count", "processed_windows", "invalid_capture", "rf_mapping_authorities")
    if any(old_stats[k] != new_stats[k] for k in same_keys):
        raise ValueError("parent arrays do not cover the same complete physical visits")
    both = list(zip(visit_pairs(left["probes"]), visit_pairs(right["probes"]), strict=True))
    valid = {p[0][0] for p in both}
    excluded = {p["visit"] for p in old_stats["excluded_windows"]}
    if (
        len(both) != old_stats["processed_windows"]
        or len(excluded) != old_stats["invalid_capture"]
        or len(excluded) != len(old_stats["excluded_windows"])
        or valid & excluded
        or valid | excluded != set(range(old_stats["window_count"]))
        or len(stock["delivery_clocks"]) != old_stats["window_count"]
    ):
        raise ValueError("each physical scheduled visit requires either both lanes or exclusion")
    state, runs, hybrid, counts = RfStagger(), [], [], Counter()
    lane_counts = {}
    for (visit, a), (other, b) in both:
        key = a[0]["channel"], a[0]["edge"]
        if other != visit or (a[1]["channel"], a[1]["edge"]) != key:
            raise ValueError("stereo packets need one common recorded RF tuning center")
        center = rf_centers[key]
        use = state.reserve(center)
        from_fifth = b[0] if use == 0 else b[1]
        chosen = (from_fifth, a[1]) if use == 0 else (a[0], from_fifth)
        hybrid.extend(chosen)
        tally = lane_counts.setdefault(str(center), [0, 0])
        tally[use] += 1
        hashes = [sha256(encode(p)).hexdigest() for p in chosen]
        runs.append(
            dict(visit=visit, rf_center_hz=center, fifth_lane=use, native_packet_sha256=hashes)
        )
        for rx, (s, f, h) in enumerate(zip(a, b, chosen, strict=True)):
            winners = list(map(winner, (s, f, h)))
            for name, probe, hit in zip(
                ("stock", "fifth", "staggered"), (s, f, h), winners, strict=True
            ):
                counts[f"{name}_positive"] += hit is not None
                counts[f"{name}_receiver{rx}_positive"] += hit is not None
                counts[f"{name}_candidate_rows"] += len(probe["candidates"])
                counts[f"{name}_gated_candidates"] += sum(
                    row["passed_fractional_margin_gate"] is True for row in probe["candidates"]
                )
            changed = winners[0] != winners[2]
            counts["changed_winners_vs_stock"] += changed
            counts["new_positive_vs_stock"] += winners[0] is None and winners[2] is not None
            counts["lost_positive_vs_stock"] += winners[0] is not None and winners[2] is None
    if any(not 0 <= pair[0] - pair[1] <= 1 for pair in lane_counts.values()):
        raise ValueError("every RF must start at lane zero and alternate")
    return (
        hybrid,
        runs,
        dict(
            dict(counts),
            fifth_by_rf=lane_counts,
            valid_visits=len(valid),
            invalid_visits=len(excluded),
            scheduled_visits=len(stock["delivery_clocks"]),
            raw_recording_authority_digest=left["raw_recording_authority_digest"],
            input_manifest_sha256=left["input_manifest_sha256"],
            clock_sha256=sha256(encode(stock["delivery_clocks"])).hexdigest(),
        ),
    )
