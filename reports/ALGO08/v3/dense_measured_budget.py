"""Use the genuine dense receiver costs to distinguish one-recording results from transfers."""

import argparse
import gzip
import json
from pathlib import Path

from acquisition_throughput import gates, minimum_rate
from full_short_live_budget import maximum_fraction


DATA = Path(__file__).resolve().parent / "measurements"


def read(name):
    return json.loads((DATA / name).read_bytes())


def cost_partition(total, acquisition, native, solve):
    costs = dict(receiver=native, other_acquisition=acquisition-native, solver=solve,
                 remaining=total-acquisition-solve)
    if any(value < 0 for value in costs.values()):
        raise ValueError("Overlapping or negative stage costs")
    return costs


def evaluate():
    raw = json.loads(gzip.decompress((DATA / "dense-full-short-raw.json.gz").read_bytes()))
    crossed = read("dense-full-short-crossover-summary.json")
    controls = read("dense-control-clocks.json")
    original = read("full-short-live-budget.json")["dense_solve_cpu_s"]["installed"]
    inventory = read("acquisition-throughput.json")["rows"]
    dense, = [row for row in inventory if row["case"] == "DS30-0008"]
    calibration = read("full-short-seal-scaling.json")
    best = max((r["measurements"] for r in calibration["projections"]["receiver"] if r["arm"] == "full-short"),
               key=lambda r: r["reader_MB_s"])
    overhead = best["worker_overhead_s"] + calibration["shared_once_per_recording_tails_s"]["optimistic"]
    candidate = raw["candidate"]
    if (candidate["native_sha256"] != crossed["runs"]["short_installed"]["native_sha256"]
            or raw["binding"]["authority"] != controls["common"]["raw_authority"]):
        raise ValueError("Raw and saved experiments must refer to the same recording")
    receiver = candidate["recipe"]["receiver_audit"]
    acquired = receiver["acquire"]
    process = raw["process"]
    solve = candidate["result"]["solve"]
    cpu = cost_partition(process["cpu_s"], acquired["cpu_ns"]/1e9,
                         sum(receiver["native"]["native_cpu_ns"].values())/1e9, solve["cpu_s"])
    raw_rate = dense["compressed_MB"] / (acquired["wall_ns"]/1e9)
    gates_by_graph = {}
    for graph in ("short_installed", "short_quadratic"):
        solver = crossed["runs"][graph]["solve"]["cpu_s"]
        fraction = solver / original
        scenarios = {}
        for name, rate in (("observed_dense", raw_rate), ("fastest_prefix", best["reader_MB_s"])):
            feasible = maximum_fraction(inventory, rate, overhead)
            scenarios[name] = dict(reader_MB_s=rate, ratios=gates(inventory, rate, fraction, startup_s=overhead),
                                   dense_solve_budget_s=None if feasible is None else feasible*original)
        gates_by_graph[graph] = dict(solve_cpu_s=solver, ratio=fraction, scenarios=scenarios,
            required_reader_MB_s=[minimum_rate(inventory, fraction, i, startup_s=overhead) for i in (0,1)])
    comparison = {name: dict(wall_ratio=process["elapsed_s"]/r["elapsed_s"], cpu_ratio=process["cpu_s"]/r["cpu_s"],
                             elapsed_above_half_s=process["elapsed_s"]-r["half_elapsed_s"])
                  for name,r in controls["controls"].items()}
    return dict(cpu_s=cpu, elapsed_s=process["elapsed_s"], whole_cpu_s=process["cpu_s"], common_charge_s=overhead,
                dense_compressed_MB=dense["compressed_MB"], acquire_wall_s=acquired["wall_ns"]/1e9,
                acquire_cpu_s=acquired["cpu_ns"]/1e9, controls=comparison, modeled=gates_by_graph)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    out = parser.parse_args().output
    result = evaluate()
    with out.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
