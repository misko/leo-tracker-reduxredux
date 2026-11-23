"""Derive disjoint solver ceilings and masked lane occupancy from signed receipts."""

import argparse
import gzip
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path

HERE = Path(__file__).resolve().parent
MEASURED = HERE / "measurements"
PINS = {
    "grid-cross-arm-posterior.json.gz": "1bd1efb1fecaac2018265bd3498b61d7f28282e15c6c4e418ae34fa23a6afa91",
    "grid-phase-state-reuse.json.gz": "4372e72b81462ed4c1f7d7e2fb296caf8004c775b90f9469ad6eaf31a20f7a43",
    "dense-protected-cost.json": "fa805e609662f8f0936e25f73f4f636e2684b8555e81ee25f6e9089b9cd8befb",
    "regional-dense-pair.json": "7ab29f3551ec8e237dd74d38fdab05ad4cb4750d7ae6b67560cc206c99e94749",
    "regional-dense-budget.json": "20ca6db13e6294d34ae732635158aef332f622127d120d6f6ca1229082e78677",
    "weak-combined-raw.json": "a704861e37e40e7364fbf97bcb74e98bb9c701ca474c12821e8ed7df86cab233",
}
ARMS = ("c0", "fitted_c")


def checked(name):
    data = (MEASURED / name).read_bytes()
    if sha256(data).hexdigest() != PINS[name]:
        raise ValueError(f"Archived receipt changed {name}")
    return json.loads(gzip.decompress(data) if name.endswith(".gz") else data)


def occupancy(updates, width):
    if type(width) is not int or width < 1 or not updates or any(
            type(x) is not int or x < 0 for x in updates):
        raise ValueError("Expected bounded iteration counts and a positive batch width")
    passes = [x+1 for x in updates]
    groups = [passes[i:i+width] for i in range(0, len(passes), width)]
    scheduled = sum(max(g) for g in groups)
    slots = scheduled*width
    return dict(
        calls=len(passes), posterior_passes=sum(passes), vector_steps=scheduled, slots=slots,
        utilization=sum(passes)/slots, batches=len(groups),
        batches_with_unequal_stops=sum(len(set(g)) > 1 for g in groups),
        minimum_updates=min(updates), maximum_updates=max(updates),
    )


def floor(total, credit, target):
    if (not all(isfinite(x) and x >= 0 for x in (total, credit, target))
            or credit > total):
        raise ValueError("Expected an inclusive stage, full total and nonnegative target")
    remaining = total-credit
    return dict(total_s=total, credited_stage_s=credit, zero_cost_floor_s=remaining,
                target_s=target, residual_gap_s=remaining-target)


def report():
    posterior = checked("grid-cross-arm-posterior.json.gz")
    phases = checked("grid-phase-state-reuse.json.gz")
    dense = checked("regional-dense-pair.json")
    protected = checked("dense-protected-cost.json")
    weak = checked("weak-combined-raw.json")
    frontier = checked("regional-dense-budget.json")
    if (posterior["native_sha256"] != phases["input_sha256"]
            or posterior["native_sha256"] != dense["binding"]["packet_sha256"]
            or posterior["scientific_digests"] != phases["science_sha256"]
            or not dense["same_complete_science"]
            or not all(posterior["checks"].values())):
        raise ValueError("Dense sources must share the observed grid and original packet")
    calls = {}
    for row in posterior["unmatched_endpoints"]:
        calls[row["arm"], tuple(row["point"])] = row["clock"], row["precision_iterations"]
    for row in posterior["pairs"]:
        for arm in ARMS:
            calls[arm, tuple(row["point"])] = row["clocks"][arm], row["updates"][arm]
    order = [(x["arm"], tuple(x["point"])) for x in phases["calls"]]
    if len(order) != len(calls) or len(calls) != 356 or set(order) != calls.keys():
        raise ValueError("Expected 356 unique original arm/position evaluations")
    # Each stage is inclusive. The differences give disjoint costs.
    costs = {name: sum(calls[key][0][name] for key in order)/1e9
             for name in ("native", "validation", "bound", "curved")}
    stage = dict(
        native=costs["native"], validation=costs["validation"],
        other_adapter=costs["bound"]-costs["native"]-costs["validation"],
        other_curved=costs["curved"]-costs["bound"],
    )
    if any(value < 0 for value in stage.values()):
        raise ValueError("Native clocks were not nested as expected")
    dense = dense["runs"]["native"]
    if dense["solve_cpu_s"] != frontier["solve_cpu_s"]:
        raise ValueError("Frontier budgets use a different dense solve")
    targets = {panel: max(r["dense_solve_budget_s"] for r in frontier["panels"][panel]["scenarios"].values()
                          if r["dense_solve_budget_s"] is not None)
               for panel in ("4", "16")}
    return dict(
        archive_sha256=PINS, native_callback_s=costs, disjoint_curved_s=stage,
        occupancy={arm: {str(w): occupancy([calls[key][1] for key in order if key[0] == arm], w)
                         for w in (4, 8)} for arm in ARMS},
        complete_export_share_required=.5/costs["native"],
        dense={
            panel: floor(dense["solve_cpu_s"], dense["grid_cpu_s"], target)
            for panel, target in targets.items()
        },
        protected=floor(protected["solve"]["cpu_s"],
                        protected["charged_solver_cpu_s"]["standard_evidence"], 16),
        weak=floor(weak["runs"]["candidate"]["process"]["elapsed_s"],
                   weak["candidate_solve"]["elapsed_s"], weak["runs"]["stock"]["process"]["elapsed_s"]/2),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    with parser.parse_args().output.open("x") as output:
        json.dump(report(), output, indent=2, sort_keys=True, allow_nan=False)
        output.write("\n")
