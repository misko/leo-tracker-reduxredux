"""Price changes to the complete evidence grid against the paired DS30 timing gates."""

import argparse
import json
from math import fsum, isfinite
from pathlib import Path
from statistics import median

from .field_speed_reachability import BUILD, PLAN, STOCK, checked, reconcile
from .receiver_solver_targets import targets


DONOR = Path(__file__).with_name("measurements") / "profiled-grid-export-0008.json"
DONOR_PIN = "20bcf8679a1c68e9eebd55c31fcc3c81b95e7250fc4c153a4de80e2449d2b017"


def grid_seconds(grid, outcome, measured_cpu_s):
    if not grid and outcome != "complete" and measured_cpu_s == 0:
        return 0.
    if not grid or not grid["complete"] or grid["points"] != 179 or outcome != "complete":
        raise ValueError("Expected the completed field map or a terminal without a map")
    clock = grid["clock"]
    if clock["elapsed_ns"] <= 0 or clock["cpu_ns"] / 1e9 != measured_cpu_s:
        raise ValueError("Standard grid clocks disagree")
    return clock["elapsed_ns"] / 1e9


def field_records(campaign, count):
    plan = json.loads(checked(campaign / "plan.json", PLAN))
    cases = {c["case"]: c for c in plan["cases"]}
    order = list(dict.fromkeys([*plan["smoke"], *cases]))
    seal = json.loads((campaign / "rows-with-relocations-seal.json").read_bytes())
    if not 1 <= count <= len(order) or seal["plan_sha256"] != "sha256:" + PLAN:
        raise ValueError("Expected the frozen field plan and an enrolled prefix")
    export = checked(campaign / "rows-with-relocations.jsonl", seal["combined_sha256"])
    rows = [json.loads(line) for line in export.splitlines()]
    lookup = {(r["case"], r["algorithm"]): r for r in rows}
    expected = {(case, role) for case in cases for role in ("installed", "successor")}
    if lookup.keys() != expected or len(rows) != len(lookup):
        raise ValueError("Expected both roles exactly once for every enrolled case")
    result = []
    for case in order[:count]:
        a, b = (lookup[case, role] for role in ("installed", "successor"))
        for row, build in ((a, STOCK), (b, BUILD)):
            if (not row["verified_pair"] or row["build_sha256"] != "sha256:" + build
                    or row["case_id"] != cases[case]["case_id"]
                    or row.get("relocation_proof_sha256") != seal["proofs"].get(case)):
                raise ValueError(f"Unverified field case or build for {case}")
            path = (campaign / row["attempt"]).resolve(strict=True)
            if not path.is_relative_to(campaign):
                raise ValueError("Result outside the paired campaign")
            actual = json.loads(checked(path, row["attempt_result_sha256"]))
            if any(actual[k] != row[k] for k in ("elapsed_s", "cpu_s", "algorithm", "outcome")):
                raise ValueError("Selected attempt clocks or outcome differ")
        d = reconcile(campaign, a, b)
        source = (campaign / b["attempt"]).parent / "publication/legacy-original-acquisition.json"
        ledger = json.loads(checked(source, d["pins"]["legacy"]))
        solver = d["work"]["solver"]
        grid = ledger.get("acceleration", {}).get("solver", {}).get("grid")
        seconds = grid_seconds(grid, b["outcome"], solver["grid_cpu_s"])
        result.append(dict(case=case, baseline=a["elapsed_s"], candidate=b["elapsed_s"],
                           native=d["native_detector_s"], solver=solver["wall_s"], grid=seconds,
                           stock_result=a["attempt_result_sha256"], candidate_result=b["attempt_result_sha256"],
                           stage_ledger=d["pins"]["legacy"]))
    return result


def price(rows, native_rate, grid_fraction):
    if not rows or not isfinite(native_rate) or native_rate < 1 or not 0 <= grid_fraction <= 1:
        raise ValueError("Expected observations and a finite timing scenario")
    adjusted = []
    for r in rows:
        a, b, native, solver, grid = (r[k] for k in ("baseline", "candidate", "native", "solver", "grid"))
        if not (a > 0 and 0 <= grid <= solver and 0 <= native and native + solver <= b):
            raise ValueError("Clocks must describe disjoint receiver and solver intervals with a nested grid")
        t = b - native * (1 - 1 / native_rate) - grid * (1 - grid_fraction)
        if t <= 0:
            raise ValueError("No remaining end-to-end clock")
        adjusted.append((a, t, 0., solver - grid))
    stock = fsum(a for a, *_ in adjusted)
    remaining = fsum(t for _, t, *_ in adjusted)
    return dict(summed_speedup=stock / remaining,
                paired_median_speedup=1 / median(t/a for a, t, *_ in adjusted),
                seconds_above_half=remaining - stock/2,
                additional_non_grid_solver_fraction=targets(adjusted, 1.)["both"])


def summarize(rows, donor_fraction):
    clocks = {k: fsum(r[k] for r in rows) for k in ("baseline", "candidate", "native", "solver", "grid")}
    return dict(pairs=len(rows), seconds=clocks, measured=price(rows, 1., 1.),
                free_grid=price(rows, 1., 0.), native_1p5_free_grid=price(rows, 1.5, 0.),
                native_1p5_donor_rate_entire_grid=price(rows, 1.5, donor_fraction))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    args = parser.parse_args()
    times = json.loads(checked(DONOR, DONOR_PIN))["verified_timing"]["times"]["fitted_c"]
    if [v["mode"] for v in times] != ["stock", "proof", "proof", "stock"]:
        raise ValueError("Expected the matched physical DS30-0008 timing")
    rate = median(v["call_wall_ns"] for v in times if v["mode"] == "proof") / median(
        v["call_wall_ns"] for v in times if v["mode"] == "stock")
    records = field_records(args.campaign.resolve(strict=True), 62)
    groups = {"first_30": records[:30], "next_24": records[30:54], "next_8": records[54:], "all_62": records}
    print(json.dumps(dict(plan=PLAN, callback_receipt=DONOR_PIN, callback_wall_fraction=rate,
                          groups={k: summarize(v, rate) for k, v in groups.items()}, records=records),
                     indent=2, allow_nan=False))
