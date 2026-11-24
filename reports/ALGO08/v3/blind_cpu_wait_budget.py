"""Price single-core work and off-CPU time separately on the three blind cases."""

import gzip
import hashlib
import json
from pathlib import Path
from statistics import median


ROOT = Path(__file__).resolve().parent / "measurements"
PINS = {
    "release-stage-budget.json": "bf5e6488d1b59ba49ca091b6707b6d3fed099664f528bc7540bcbbed7afbc4be",
    "receiver-mix-budget.json": "856694a1b8a26f74f172b58a9e3e5b1f1e1c5c1e10a8bc5b185c84456f1c2ffd",
    "ds30-0163-combined.json.gz": "9c28657f1dd8a8f31b2f564522d47b42e9b83347f9f816e75c435022f6398801",
    "ds30-0173-combined.json.gz": "9e68ac940d14ad404662a6460029dfe2b58a02e4e27e9137e5b32031687dd62a",
    "ds30-0359-combined.json.gz": "e6a627e9cb8c5b8200916e5031ce5b581ae971d274bf9d9eeffb215149a3df31",
}


def read(name):
    data = (ROOT / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != PINS[name]:
        raise ValueError(f"Unexpected source: {name}")
    return json.loads(gzip.decompress(data) if name.endswith(".gz") else data)


def compare(rows, fraction):
    """Give each case at least its already paid saved-worker off-CPU time."""
    priced = [row["modeled_cpu_s"] + max(row["saved_wait_s"], fraction * row["stock_wait_s"])
              for row in rows]
    ratios = [value / row["stock_elapsed_s"] for value, row in zip(priced, rows, strict=True)]
    return {
        "summed_speedup": sum(row["stock_elapsed_s"] for row in rows) / sum(priced),
        "paired_median_speedup": 1 / median(ratios),
    }


def wait_limit(rows):
    def passes(fraction):
        return min(compare(rows, fraction).values()) >= 2

    if not passes(0):
        return None
    if passes(1):
        return 1.0
    low, high = 0.0, 1.0
    for _ in range(50):
        middle = (low + high) / 2
        if passes(middle):
            low = middle
        else:
            high = middle
    return low


def study():
    panel = read("release-stage-budget.json")["rows"]
    stocks = {row["case"]: row for row in panel}
    cases = read("receiver-mix-budget.json")["projected"]
    if len(stocks) != 100 or [c["case"] for c in cases] != ["DS30-0163", "DS30-0173", "DS30-0359"]:
        raise ValueError("Benchmark enrollment changed")
    by_donor = {}
    for case in cases:
        key = case["case"]
        stock = stocks[key]
        saved = read(key.lower() + "-combined.json.gz")
        if saved["case"] != key:
            raise ValueError("Wrong saved recording")
        paid = saved["paid_setup_and_time"]
        downstream = paid["cpu_s"]["candidate_with_setup"]
        for donor, intake in case["transfer"].items():
            cpu = intake + downstream
            by_donor.setdefault(donor, []).append({
                "case": key, "stock_cpu_s": stock["cpu_s"], "stock_elapsed_s": stock["elapsed_s"],
                "stock_wait_s": stock["elapsed_s"] - stock["cpu_s"],
                "saved_wait_s": paid["elapsed_s"]["candidate_with_setup"] - downstream,
                "modeled_cpu_s": cpu, "gap_to_half_cpu_s": cpu - stock["cpu_s"] / 2,
                "max_total_wait_at_half_elapsed_s": stock["elapsed_s"] / 2 - cpu,
            })
    results = {}
    for donor, rows in by_donor.items():
        if len(rows) != len(cases):
            raise ValueError("Donor is missing a case")
        results[donor] = {
            "rows": rows, "max_retained_wait_fraction_for_both_gates": wait_limit(rows),
            "same_wait": compare(rows, 1), "only_measured_saved_wait": compare(rows, 0),
            "summed_cpu_speedup": sum(r["stock_cpu_s"] for r in rows) / sum(r["modeled_cpu_s"] for r in rows),
        }
    return {"sources": PINS, "historical_panel_median_wall_s": median(r["elapsed_s"] for r in panel),
            "donors": results}


if __name__ == "__main__":
    print(json.dumps(study(), indent=2, allow_nan=False))
