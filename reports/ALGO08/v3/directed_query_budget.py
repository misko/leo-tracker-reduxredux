"""Price an extra directed verification after the existing candidate receiver finishes."""

import json
from hashlib import sha256
from math import fsum, isclose
from statistics import median

from .receiver_solver_targets import RECEIPT, first30


def load_cases():
    scores = {}
    for name, digest in (
        ("development", "2950527d8034121ba87a7960dd42745f31d05a5d8a467369499d30e4638d3778"),
        ("held", "77ad07ee34fe5618af6c8293ea91d1ac11d3d20c46c4c55f0a4117e855b6d6d0"),
    ):
        data = RECEIPT.with_name(f"empty-graph-rescue-{name}-score.json").read_bytes()
        if sha256(data).hexdigest() != digest:
            raise ValueError("Unexpected signed-query scores")
        batch = json.loads(data)["cases"]
        if scores.keys() & batch.keys():
            raise ValueError("Repeated recording")
        scores.update(batch)
    rows = []
    for row in first30():
        score = scores.pop(row["case"])
        base, current = row["stock_wall_s"], row["actual_wall_s"]
        if not isclose(current - base / 2, score["current_half_time_wall_deficit_s"], rel_tol=0, abs_tol=1e-8):
            raise ValueError("Score belongs to a different timing pair")
        rows.append((base, current, row["native_detector_s"], row["phases"]["outer"]["elapsed_s"]["solve"],
                     score["native"]["counts"].get("selected", 0)))
    if scores:
        raise ValueError("Unmatched recordings")
    return rows


def budget(rows, native_rate, solver_rate):
    reduced = [(base, current - native * (1 - 1 / native_rate) - solver * (1 - 1 / solver_rate), count)
               for base, current, native, solver, count in rows]
    queries = sum(q for _, _, q in reduced)
    if queries <= 0:
        raise ValueError("No proposals to price")
    installed = fsum(base for base, _, _ in reduced)

    def speeds(fee_s):
        times = [(base, modeled + count * fee_s) for base, modeled, count in reduced]
        return (installed / fsum(t for _, t in times), 1 / median(t / base for base, t in times))

    slack = installed / 2 - fsum(t for _, t, _ in reduced)
    free = speeds(0)
    allowance = None
    if min(free) >= 2:
        lo, hi = 0., max(0., slack / queries)
        for _ in range(54):
            mid = (lo + hi) / 2
            if min(speeds(mid)) >= 2:
                lo = mid
            else:
                hi = mid
        allowance = lo * 1e6
    return dict(proposals=queries, aggregate_slack_s=slack, max_additional_us=allowance,
                free_speedups=free, speedups_at_840_us=speeds(.00084))


if __name__ == "__main__":
    cases = load_cases()
    for rates in [(1., 1.), (1.5, 1.4), (1.75, 1.4)]:
        print(rates, json.dumps(budget(cases, *rates)))
