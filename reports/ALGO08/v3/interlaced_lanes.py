"""Separate antenna times at equal per-channel detector call count."""

import argparse
from collections import defaultdict
from contextlib import ExitStack
from functools import partial
from pathlib import Path
from unittest.mock import patch

from paid_graph_trial import run
from paid_quadratic import quadratic
from sparse_consensus import paid_visits
from sparse_consensus_trial import CASES


def slots(rows, swap):
    nominal = paid_visits(rows)
    streams = defaultdict(list)
    for i, row in enumerate(rows[::2]):
        streams[(row["channel"], row["actual_rf_hz"], row["edge"])].append(i)
    admitted = set()
    for rank, (_, stream) in enumerate(sorted(streams.items())):
        moving = (rank + int(swap)) % 2
        for start in range(0, len(stream), 3):
            triple = stream[start:start+3]
            offset = rank % 3
            if offset >= len(triple):
                continue
            home = triple[offset]
            other = triple[(offset + 1) % 3] if len(triple) == 3 else home
            admitted.update((2 * home + 1 - moving, 2 * other + moving))
    if len(admitted) != 2 * len(nominal):
        raise ValueError("Schedule changed total lane cost")
    return admitted


def choose(rows, clocks, *, swap):
    from leo.contracts.digests import canonical_digest

    paid = slots(rows, swap)
    result = [[] for _ in rows]
    count = 0
    for i in sorted(paid):
        candidates = [c for c in rows[i]["candidates"] if c["passed_fractional_margin_gate"] is True]
        count += len(candidates)
        if candidates:
            result[i] = [max(candidates, key=lambda c: (c["fractional_margin"], -c["candidate_rank"]))]
    keys = sorted((rows[i]["visit_index"], rows[i]["receiver_id"]) for i in paid)
    return result, dict(paid_lanes=len(paid), paid_visits=len({v for v, _ in keys}), paid_factors=count,
                        mask_sha256=canonical_digest(keys), paid_native_cpu_s=sum(clocks[i] for i in paid)/1e9)


def quadratic_run(case, mode, selector, out, *, inspect_region=None):
    with ExitStack() as stack:
        def observe(native, identity, config):
            from tools import algo08_position

            factory = algo08_position.TrackConfig
            stack.enter_context(patch.object(algo08_position, "TrackConfig", lambda **cfg: quadratic(factory(**cfg))))
            if inspect_region is not None:
                from tools.pipeline_eval.variants.experimental import regional_bound_guard

                stack.enter_context(patch.object(regional_bound_guard, "inspect_boundary", inspect_region))
            identity["graph_parameters"] = {"max_degree": 2, "min_points": 6, "points_per_coefficient": 2}
        run(case, mode, out, observe=observe, select_paid=selector)


def measure(case, swap, out):
    quadratic_run(case, "swapped" if swap else "interlaced", partial(choose, swap=swap), out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    parser.add_argument("mode", choices=("interlaced", "swapped"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    measure(args.case, args.mode == "swapped", args.output)
