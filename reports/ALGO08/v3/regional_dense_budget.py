"""Apply the newly measured dense solve to the enrolled 4/16 and historical 55 clocks."""

import argparse
import json
from pathlib import Path

from acquisition_throughput import gates, minimum_rate
from full_short_live_budget import maximum_fraction

HERE = Path(__file__).resolve().parent
DATA = HERE / "measurements"


def select(rows, assigned):
    by_case = {r["case"]: r for r in rows}
    if len(by_case) != len(rows) or len(set(assigned)) != len(assigned) or not set(assigned) <= by_case.keys():
        raise ValueError("Panel must map to unique recorded clocks")
    return [by_case[case] for case in assigned]


def model(result):
    def read(path):
        return json.loads(path.read_bytes())

    inputs = read(DATA / "acquisition-throughput.json")["rows"]
    sizes = read(HERE / "development/stages.json")["stages"]
    full = read(DATA / "dense-measured-budget.json")
    released = read(DATA / "full-short-live-budget.json")["dense_solve_cpu_s"]["installed"]
    if not result["same_complete_science"] or result["binding"]["packet_sha256"] != read(DATA / "regional-track-dense.json")["native_pin"]:
        raise ValueError("Dense solve must bind the actual short detector and the complete matched publication")
    solve = result["runs"]["native"]["solve_cpu_s"]
    price = full["common_charge_s"]
    reader = full["modeled"]["short_installed"]["scenarios"]
    cases = {n: [row["case"] for row in sizes[n]["cases"]] for n in ("4", "16")}
    if cases["16"][:4] != cases["4"] or any(len(ids) != int(n) for n, ids in cases.items()):
        raise ValueError("Stage rosters changed")
    cases["55"] = [r["case"] for r in inputs]
    panels = {}
    for name, ids in cases.items():
        rows = select(inputs, ids)
        scenarios = {}
        for source, assumption in reader.items():
            rate = assumption["reader_MB_s"]
            allowed = maximum_fraction(rows, rate, price)
            median, summed = gates(rows, rate, solve / released, startup_s=price)
            scenarios[source] = dict(reader_MB_s=rate, median_ratio=median, summed_ratio=summed,
                                     dense_solve_budget_s=None if allowed is None else allowed * released)
        panels[name] = dict(cases=ids, unchanged_outcomes=sum(r["stages"][0] == 0 for r in rows),
                            scenarios=scenarios, required_MB_s_by_gate=[minimum_rate(rows, solve / released, i,
                                startup_s=price) for i in (0, 1)])
    return dict(panels=panels, solve_cpu_s=solve, historical_installed_solve_cpu_s=released, common_charge_s=price)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("scored", type=Path)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    with args.output.open("x") as stream:
        json.dump(model(json.loads(args.scored.read_bytes())), stream, indent=2, allow_nan=False)
        stream.write("\n")
