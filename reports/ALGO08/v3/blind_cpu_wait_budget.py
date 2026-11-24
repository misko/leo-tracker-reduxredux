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
    "first-member-0163-resume-acquisition.json.gz": "5cf1c7e7c785c84913851515242ddcd434b02ee4de33c1a244e3f53732ee7c8f",
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


def check_first_member(donors, documents):
    stage = documents["resumed-stage.json"]["document"]
    member = stage["member"]
    if (stage["case"] != "DS30-0163" or member["first_sequence"] != 0
            or stage["decoded"]["raw_sha256"] != member["uncompressed_sha256"]
            or not documents["result.json"]["document"]["qualified"]):
        raise ValueError("Expected the authenticated first 0163 member")
    worker = documents["integrated/worker.json"]["document"]
    receiver = worker["receiver"]["native"]
    native = sum(receiver["native_cpu_ns"].values()) / 1e9
    actual = worker["receiver_acquire"]["cpu_s"]
    comparisons = {}
    for donor in donors:
        callbacks = sum(count * donor["cpu_s_per_call"][mode]
                        for mode, count in receiver["native_calls"].items())
        residual = member["compressed_bytes"] * donor["other_cpu_s_per_byte"]
        comparisons[donor["name"]] = {
            "native_cpu_s": callbacks, "other_acquisition_cpu_s": residual,
            "total_cpu_s": callbacks + residual,
            "relative_error": (callbacks + residual) / actual - 1,
        }
    return {"visits": member["window_count"], "compressed_bytes": member["compressed_bytes"],
            "native_calls": receiver["native_calls"], "measured_native_cpu_s": native,
            "measured_other_acquisition_cpu_s": actual - native, "measured_acquisition_cpu_s": actual,
            "predictions": comparisons}


def study():
    panel = read("release-stage-budget.json")["rows"]
    stocks = {row["case"]: row for row in panel}
    model = read("receiver-mix-budget.json")
    cases = model["projected"]
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
    first_member = read("first-member-0163-resume-acquisition.json.gz")
    return {"sources": PINS, "historical_panel_median_wall_s": median(r["elapsed_s"] for r in panel),
            "first_member_model_check": check_first_member(model["measured"], first_member["documents"]),
            "donors": results}


if __name__ == "__main__":
    print(json.dumps(study(), indent=2, allow_nan=False))
