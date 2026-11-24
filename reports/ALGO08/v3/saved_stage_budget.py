"""Price uniform stage improvements against both gates on the sealed six-case panel."""

import json
from statistics import median

from reports.ALGO08.v3.history_risk_route_panel import read_sealed_panel


def stage_rows(panel):
    rows = []
    for case in panel["case_order"]:
        entry = panel["enrolled"][case]
        run = entry["result"]
        trace = run.get("preparation", run.get("prep_timing"))
        if trace["solves"] != 1:
            raise ValueError(f"Expected one solve on {case}")
        times = {}
        for stage in ("prepare", "infer"):
            event, = trace[stage]
            if event["status"] != "returned" or event["elapsed_ns"] <= 0:
                raise ValueError(f"Incomplete {stage} on {case}")
            times[stage] = event["elapsed_ns"] / 1e9
        worker = run["clock"]["elapsed_s"]
        other = worker - sum(times.values())
        if other < 0:
            raise ValueError(f"Measured stages exceed the whole worker on {case}")
        admission = entry["source_stage"]["preflight"]["elapsed_ns"] / 1e9
        rows.append(dict(case=case, baseline=run["archive_stock_clock"]["elapsed_s"],
                         candidate=worker + admission, admission=admission, other=other, **times))
    return rows


def gate_ratios(rows, savings):
    """Each saving is a fraction of its own disjoint elapsed stage."""
    reduced = [r["candidate"] - sum(r[k] * f for k, f in savings.items()) for r in rows]
    return (median(t / r["baseline"] for t, r in zip(reduced, rows, strict=True)),
            sum(reduced) / sum(r["baseline"] for r in rows))


def required_reduction(rows, stage, speedup):
    target = 1 / speedup
    if max(gate_ratios(rows, {})) <= target:
        return 0.0
    if max(gate_ratios(rows, {stage: 1.0})) > target:
        return None
    lo, hi = 0.0, 1.0
    for _ in range(50):
        mid = (lo + hi) / 2
        if max(gate_ratios(rows, {stage: mid})) <= target:
            hi = mid
        else:
            lo = mid
    return hi


if __name__ == "__main__":
    rows = stage_rows(read_sealed_panel(6))
    thresholds = {stage: {speed: required_reduction(rows, stage, speed) for speed in (1.6, 2.0)}
                  for stage in ("prepare", "infer", "other", "admission")}
    print(json.dumps(dict(rows=rows, required_stage_reductions=thresholds), indent=2, allow_nan=False))
