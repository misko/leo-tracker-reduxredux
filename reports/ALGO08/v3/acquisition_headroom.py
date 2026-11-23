"""Calculate single-core acquisition headroom using only archived clocks."""

import json
from pathlib import Path

from acquisition_throughput import minimum_rate
from regional_dense_budget import select

DATA = Path(__file__).resolve().parent / "measurements"


def wall_budget(megabytes, rate, cpu, wall):
    """An exposed wait is elapsed time outside the charged acquisition CPU."""
    if min(megabytes, rate, cpu) <= 0 or wall < cpu:
        raise ValueError("Expected positive inputs and one-core CPU no greater than elapsed time")
    target = megabytes / rate
    return dict(target_wall_s=target, wait_allowance_s=target - cpu,
                required_cpu_saving_at_observed_wait_s=max(0, wall - target),
                observed_non_cpu_s=wall - cpu)


def report():
    def read(name):
        return json.loads((DATA / name).read_bytes())

    dense = read("dense-measured-budget.json")
    model = read("regional-dense-budget.json")
    inventory = read("acquisition-throughput.json")["rows"]
    current = wall_budget(dense["dense_compressed_MB"], 250, dense["acquire_cpu_s"], dense["acquire_wall_s"])
    panels = {}
    for size in ("4", "16"):
        rows = select(inventory, model["panels"][size]["cases"])
        panel = []
        for solve in (12, 16, model["solve_cpu_s"]):
            for repair in (0, 2):
                rates = [minimum_rate(rows, solve / model["historical_installed_solve_cpu_s"], i,
                                      startup_s=model["common_charge_s"] + repair) for i in (0, 1)]
                rate = max(rates) if None not in rates else None
                panel.append(dict(dense_solve_s=solve, extra_per_instrumented_case_s=repair,
                                  rates_MB_s=rates, required_MB_s=rate))
        panels[size] = panel
    return dict(dense_at_250_MB_s=current, panels=panels)


if __name__ == "__main__":
    print(json.dumps(report(), indent=2, allow_nan=False))
