"""Separate measured native receiver wall time from the rest of three complete runs."""

import argparse
import gzip
import json
from pathlib import Path
from statistics import median

from reports.ALGO08.v3.release_stage_budget import checked


M = Path(__file__).resolve().parent / "measurements"
PANEL = "edbaa35c4b18e9f593d1d7f7ac7928a1d6e65bc259d8e46a385c645fdb3f684d"
NORTH = "bfe8b77a2ca078a4187396f6d5d1848e8c5f81f285f4959f8a9d77f5a04fc646"


def partition(stock, wall, phases, native):
    acquisition = phases["authenticated_raw_acquisition"]["elapsed_s"]
    publication = phases["decision_and_publication"]["elapsed_s"]
    full = native["native_wall_ns"]["full"] / 1e9
    short = native["native_wall_ns"]["short_primary"] / 1e9
    other_input = acquisition - full - short
    remainder = wall - acquisition - publication
    if min(stock, wall) <= 0 or min(full, short, other_input, publication, remainder) < 0:
        raise ValueError("Native calls must nest inside acquisition and both stages inside the child")
    return dict(stock_s=stock, wall_s=wall, full_s=full, short_s=short, other_input_s=other_input,
                decision_publication_s=publication, outside_s=remainder,
                native_calls=native["native_calls"])


def scenario(rows, *, short_fraction=1., full_fraction=1., input_fraction=1., publication_fraction=1.):
    times = [r["outside_s"] + r["full_s"]*full_fraction + r["short_s"]*short_fraction
             + r["other_input_s"]*input_fraction + r["decision_publication_s"]*publication_fraction for r in rows]
    stock = [r["stock_s"] for r in rows]
    return dict(total_s=sum(times), sum_speedup=sum(stock)/sum(times),
                median_speedup=1/median(t/b for t, b in zip(times, stock, strict=True)))


def budget(rows):
    joint = dict(short_fraction=.5, publication_fraction=2/3)
    def meets(fraction):
        result = scenario(rows, input_fraction=fraction, **joint)
        return min(result["sum_speedup"], result["median_speedup"]) >= 2
    if meets(1.):
        requirement = 1.
    elif not meets(0.):
        requirement = None
    else:
        low, high = 0., 1.
        for _ in range(55):
            mid = (low+high)/2
            if meets(mid):
                low = mid
            else:
                high = mid
        requirement = 1/low if low else None
    return dict(measured=scenario(rows), half_short=scenario(rows, short_fraction=.5),
                free_native=scenario(rows, full_fraction=0., short_fraction=0.),
                half_short_and_faster_publication=scenario(rows, **joint),
                joint_required_other_input_speedup=requirement)


def read(folder):
    physical = json.loads(gzip.decompress(checked(M/"legacy-first-use-original-panel.json.gz", PANEL)))
    north = json.loads(gzip.decompress(checked(M/"legacy-first-map-north.json.gz", NORTH)))
    if not (physical["qualified"] and north["qualified"]):
        raise ValueError("Require qualified complete processes")
    seal = json.loads(checked(folder/"prediction-seal.json", physical["prediction_seal_sha256"].removeprefix("sha256:")))
    rows = {}
    rel = "fused/unified-short-bootstrap.json"
    for name, run in physical["cases"].items():
        data = json.loads(checked(folder/name/rel, seal["cases"][name][rel].removeprefix("sha256:")))
        rows[name] = partition(run["original"]["elapsed_s"], run["clock"]["clock"]["elapsed_s"],
                               run["science"]["phases"], data["receiver_audit"]["native"])
    sim = partition(north["controls"]["installed_readback"]["elapsed_s"], north["clock"]["elapsed_s"],
                    north["phases"], north["native"]["audit"])
    return dict(cases={**rows, "North": sim}, physical=budget(list(rows.values())), north=budget([sim]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sealed_panel", type=Path)
    args = parser.parse_args()
    print(json.dumps(read(args.sealed_panel), indent=2, allow_nan=False))
