"""Price perfect withdrawal and post-terminal shortcuts on enrolled v3 clocks."""

import csv
import json
from statistics import median

from regional_dense_budget import DATA, select
from retained_wait import read_rows
from staged_budget import ROOT, TIMES_SHA, checked


def price(rows, decisions, projected=None, *, free_tail=False, free_withdrawal=False):
    reference = []
    candidate = []
    for row in rows:
        case = row["case"]
        acquisition, solve, tail = row["stages"]
        original = acquisition + solve + tail
        elapsed = original
        if decisions[case] == "complete":
            if acquisition <= 0:
                raise ValueError("Completed fix requires split clocks")
            if projected is not None:
                rate, solve_fraction, startup = projected
                elapsed = row["compressed_MB"] / rate + solve * solve_fraction + startup + tail
            if free_tail:
                elapsed -= tail
        elif free_withdrawal and decisions[case] == "withheld":
            elapsed = 0.
        reference.append(original)
        candidate.append(elapsed)
    return median(t / r for t, r in zip(candidate, reference, strict=True)), sum(candidate) / sum(reference)


def report():
    model = json.loads((DATA / "regional-dense-budget.json").read_bytes())
    frontier = json.loads((DATA / "physical-frontier-budget.json").read_bytes())
    inventory = json.loads((DATA / "acquisition-throughput.json").read_bytes())["rows"]
    timings = {r["case"]: r["stages"] for r in read_rows()}
    decisions = {r["case"]: r["decision"] for r in csv.DictReader(
        checked(ROOT / "first-55/recordings.csv", TIMES_SHA).decode().splitlines()) if r["build"] == "candidate"}
    if any(r["stages"] != timings[r["case"]] for r in inventory):
        raise ValueError("Throughput inputs differ from enrolled stage clocks")
    rates = [arm["measured_prefix_rate_MB_s"] for arm in frontier["4"]["conditional_on_constant_rate"]
             if arm["mode"] == "prefetch"]
    panels = {}
    for size in ("4", "16", "55"):
        rows = select(inventory, model["panels"][size]["cases"])
        counts = {decision: sum(decisions[r["case"]] == decision for r in rows)
                  for decision in ("complete", "withheld", "solver_failed")}
        if sum(counts.values()) != int(size):
            raise ValueError("Unrecognized enrolled outcome")
        options = dict(free_tail=True, free_withdrawal=True)
        projections = []
        for rate in rates:
            inputs = (rate, model["solve_cpu_s"] / model["historical_installed_solve_cpu_s"], model["common_charge_s"])
            projections.append(dict(rate_MB_s=rate, ordinary_gates=price(rows, decisions, inputs),
                                    optimistic_gates=price(rows, decisions, inputs, **options)))
        panels[size] = dict(counts=counts, original_s=sum(sum(r["stages"]) for r in rows),
                            complete_tail_s=sum(r["stages"][2] for r in rows if decisions[r["case"]] == "complete"),
                            withheld_s=sum(sum(r["stages"]) for r in rows if decisions[r["case"]] == "withheld"),
                            historical_oracle_gates=price(rows, decisions, **options), projections=projections)
    return panels


if __name__ == "__main__":
    print(json.dumps(report(), indent=2, allow_nan=False))
