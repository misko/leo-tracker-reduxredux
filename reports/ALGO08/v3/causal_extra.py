"""Use short paid peak histories to select a limited number of extra receiver searches."""

import argparse
from collections import defaultdict, deque
from pathlib import Path

from interlaced_lanes import quadratic_run
from sparse_consensus import paid_visits
from sparse_consensus_trial import CASES


def choose(rows, clocks):
    from leo.contracts.digests import canonical_digest

    base = paid_visits(rows)
    credits = defaultdict(int)
    previous = defaultdict(lambda: deque(maxlen=2))
    selected, added, history = [], [], []
    factors = baseline_count = 0
    picks = [[] for _ in rows]
    for i, r in enumerate(rows):
        stream = tuple(r[k] for k in ("receiver_id", "channel", "actual_rf_hz", "edge"))
        now = r["valid_start_counter"]
        anchors = previous[stream]
        credits[stream] = min(6, credits[stream] + 1)
        if r["visit_index"] not in base:
            if len(anchors) < 2 or credits[stream] < 6:
                continue
            (t1, f1), (t2, f2) = anchors
            if not (0 < now - t1 <= 80_000_000 and t1 < t2 < now):
                continue
            if abs(f2 - f1) > 8000 * ((t2-t1) / 10_000_000):
                continue
            credits[stream] = 0
            added.append(i)
            history.append((r["visit_index"], r["receiver_id"], t1, t2))
        else:
            baseline_count += 1
        selected.append(i)
        candidates = [c for c in r["candidates"] if c["passed_fractional_margin_gate"] is True]
        factors += len(candidates)
        if candidates:
            winner = max(candidates, key=lambda c: (c["fractional_margin"], -c["candidate_rank"]))
            picks[i] = [winner]
            if r["visit_index"] in base:
                anchors.append((now, winner["fractional_tracking_cfo_hz"]))
    keys = [(rows[i]["visit_index"], rows[i]["receiver_id"]) for i in selected]
    return picks, dict(paid_lanes=len(selected), base_lanes=baseline_count, extra_lanes=len(added),
                       paid_visits=len({v for v, _ in keys}), paid_factors=factors, mask_sha256=canonical_digest(keys),
                       anchor_sha256=canonical_digest(history), extra_peak_returns=sum(bool(picks[i]) for i in added),
                       extra_native_cpu_s=sum(clocks[i] for i in added)/1e9,
                       paid_native_cpu_s=sum(clocks[i] for i in selected)/1e9)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("case", choices=CASES)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    quadratic_run(a.case, "causal_extra", choose, a.output)
