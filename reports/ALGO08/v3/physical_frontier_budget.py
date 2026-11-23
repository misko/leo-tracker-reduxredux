"""Translate measured two-member CPU/elapsed into conditional panel budgets."""

import gzip
import json

from full_short_live_budget import maximum_fraction
from regional_dense_budget import DATA, gates, minimum_rate, select


def acquisition_budget(size_mb, cpu_s, elapsed_s, rate):
    if min(size_mb, cpu_s, rate) <= 0 or elapsed_s < cpu_s:
        raise ValueError("Positive bytes, rate and a single-core process clock are required")
    target = size_mb / rate
    return dict(target_elapsed_s=target, permitted_elapsed_outside_cpu_s=target-cpu_s,
                required_elapsed_saving_s=max(0., elapsed_s-target))


def report():
    envelope = json.loads(gzip.decompress((DATA / "physical-stage-envelope.json.gz").read_bytes()))
    prefetch = json.loads(gzip.decompress((DATA / "physical-short-prefetch.json.gz").read_bytes()))
    model = json.loads((DATA / "regional-dense-budget.json").read_bytes())
    original = json.loads((DATA / "acquisition-throughput.json").read_bytes())["rows"]
    size = envelope["nominal_compressed_bytes_per_arm"] / 1e6
    rows = [arm for arm in envelope["arms"] if arm["arm"] == "dsp"]
    if len(rows) != 2 or any(any(arm["before_payload_pages"]) for arm in rows):
        raise ValueError("Expected two page-cold signed-DSP measurements")
    prefetched = [a for a in prefetch["arms"] if a["ingress"] == "prefetch"]
    if (len(prefetched) != 2 or prefetch["compressed_bytes"] != envelope["nominal_compressed_bytes_per_arm"]
            or prefetch["member_pins"] != envelope["chunks"] or any(any(a["start_payload_pages"]) for a in prefetched)):
        raise ValueError("Expected two cold prefetch runs on the same physical members")
    measurements = [("serial", a["order"], a["elapsed_ns"], a["cpu_ns"]) for a in rows]
    measurements.extend(("prefetch", a["pair"], a["acquire_wall_ns"], a["acquire_cpu_ns"]) for a in prefetched)
    solve = model["historical_installed_solve_cpu_s"]
    fixed = model["common_charge_s"]
    panels = {}
    for n in ("4", "16"):
        roster = select(original, model["panels"][n]["cases"])
        required = max(minimum_rate(roster, 14/solve, i, startup_s=fixed) for i in (0, 1))
        samples = []
        for mode, order, wall_ns, cpu_ns in measurements:
            wall, cpu = wall_ns / 1e9, cpu_ns / 1e9
            rate = size / wall
            allowed = maximum_fraction(roster, rate, fixed)
            samples.append(dict(mode=mode, measured_prefix_rate_MB_s=rate, original_order=order,
                                maximum_dense_solve_s=None if allowed is None else allowed*solve,
                                gates_at_14_s=gates(roster, rate, 14/solve, startup_s=fixed),
                                prefix_budget_at_required_rate=acquisition_budget(size, cpu, wall, required),
                                prefix_budget_at_250_MB_s=acquisition_budget(size, cpu, wall, 250)))
        panels[n] = dict(required_MB_s_at_14_s=required, conditional_on_constant_rate=samples)
    return panels


if __name__ == "__main__":
    print(json.dumps(report(), indent=2, allow_nan=False))
