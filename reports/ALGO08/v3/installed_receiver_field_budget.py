"""Price the full installed detector on matched field receipts without replaying I/Q."""

import argparse
import gzip
from hashlib import sha256
import json
import math
from pathlib import Path
from statistics import median


DET = "sha256:2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5"
EXACT_WEAK = "sha256:713f49b6de436091ceddeb4ad4c641738c0d5ebe0b9d697d8bd8e85bcb833d67"
MIXED_WEAK_NATIVE = "sha256:5eea8c0db979ec729e83f56f2cb806823d785fbc65455730ee321cfc9de9a245"
CASES = ("DS30-0178", "DS30-0019", "DS30-0274", "DS30-0330", "DS30-0397", "DS30-0124", "DS30-0086",
         "DS30-0220", "DS30-0107", "DS30-0049")


def digest(body):
    return "sha256:" + sha256(body).hexdigest()


def read(path, pin=None):
    body = path.read_bytes()
    checksum = digest(body)
    if pin is not None and pin != checksum:
        raise ValueError(f"Changed archived receipt {path.name}")
    return json.loads(body), checksum


def arm(root, row):
    attempt = (root / row["attempt"]).resolve(strict=True)
    if not attempt.is_relative_to(root / "cases" / row["case"] / row["algorithm"]):
        raise ValueError("Result escaped the verified case and algorithm")
    result, _ = read(attempt, row["attempt_result_sha256"])
    folder = attempt.parent / "publication"
    (packet,) = (folder / "fast-scan-automatic-work").glob("*/detections.json")
    native, _ = read(packet, result["native_sha256"])
    ns = packet.stat().st_mtime_ns
    if not row["child_started_unix_ns"] <= ns <= row["child_finished_unix_ns"]:
        raise ValueError("The native publication must occur within the charged child")
    return result, native, folder, (ns - row["child_started_unix_ns"]) / 1e9


def field_pair(root, left, right):
    installed, stock, _, stock_file = arm(root, left)
    successor, mixed, folder, mixed_file = arm(root, right)
    source, witness = read(folder / "unified-short-bootstrap.json")
    science, solve_pin = read(folder / "exact-named-raw-witness.json")
    intake, intake_pin = read(folder / "legacy-original-acquisition.json")
    a, b = stock["source"], mixed["source"]
    metadata = lambda probes: [{k: v for k, v in row.items() if k != "candidates"} for row in probes]
    fields = ("input_manifest_sha256", "session_id", "raw_recording_authority_digest")
    count = len(a["probes"])
    bound = source["receiver_audit"]["native"]
    full = bound["native_calls"]["full"]
    sizes = [row["encoded"] for row in intake["members"] if row["chunk_index"]]
    speculative = source["prefetch"]
    if (any(a[key] != b[key] for key in fields) or metadata(a["probes"]) != metadata(b["probes"])
            or stock["provenance"]["detector_sha256"] != DET or "sha256:" + bound["installed_sha256"] != DET
            or stock["clock_anchor"] != mixed["clock_anchor"]
            or installed["raw_identity"] != successor["raw_identity"]
            or source["native_sha256"] != successor["native_sha256"]
            or source["receiver_audit"]["recording_authority"] != a["raw_recording_authority_digest"]
            or intake["finished_raw_authority"] != a["raw_recording_authority_digest"]
            or speculative["fallback"] or (len(sizes), sum(sizes)) != (speculative["hits"], speculative["hit_bytes"])
            or not 0 < full <= count or sum(bound["native_calls"].values()) != count):
        raise ValueError("Expected exact detector identity and a shared signed opportunity roster")
    phases = source["phases"]
    acquire = phases["authenticated_raw_acquisition"]
    decision = phases["decision_and_publication"]
    kernels = {k: n / 1e9 for k, n in bound["native_cpu_ns"].items()}
    prefetch = speculative["worker_cpu_ns"] / 1e9
    solve = science.get("timing", {}).get("solve", [])
    if (len(solve) != int(successor["outcome"] == "complete")
            or any(not 0 < times["cpu_s"] <= decision["cpu_s"] for times in solve)):
        raise ValueError("Inner solver clock does not belong to the published decision")
    return dict(case=left["case"], installed_outcome=installed["outcome"], successor_outcome=successor["outcome"],
                installed_s=left["elapsed_s"], successor_s=right["elapsed_s"],
                installed_wall_to_native_s=stock_file, successor_wall_to_native_s=mixed_file,
                measured_native_anchors=full, full_eligible_lanes=count, measured_mixed_native_process_cpu_s=kernels,
                measured_prefetch_thread_cpu_s=prefetch, measured_mixed_acquisition=acquire,
                measured_mixed_decision_and_publication=decision, measured_mixed_solve=solve[0] if solve else None,
                optimistic_ingress_remainder_s=max(0.0, acquire["cpu_s"] - prefetch - sum(kernels.values())),
                modeled_stock_native_s=kernels["full"] * count / full,
                installed_result_sha256=left["attempt_result_sha256"], successor_result_sha256=right["attempt_result_sha256"],
                installed_native_sha256=installed["native_sha256"], successor_native_sha256=successor["native_sha256"],
                speculative_member_bytes=sizes, successor_intake_sha256=intake_pin,
                successor_runtime_sha256=witness, successor_solve_sha256=solve_pin)


def gates(records, times):
    elapsed = [r["installed_s"] for r in records]
    ratios = [t / s for t, s in zip(times, elapsed, strict=True)]
    return dict(median=median(ratios), summed=sum(times) / sum(elapsed))


def rate_threshold(records, fixed, stock_native):
    """Largest proportional factor on the projected native CPU that passes both gates."""
    if max(gates(records, fixed).values()) > .5:
        return None

    def passes(rate):
        return max(gates(records, [n * rate + o for n, o in zip(stock_native, fixed, strict=True)]).values()) <= .5

    low, high = 0.0, sum(row["installed_s"] for row in records) / sum(stock_native)
    for _ in range(52):
        middle = (low + high) / 2
        if passes(middle):
            low = middle
        else:
            high = middle
    return low


def summarize(records, transfer):
    stock = [r["modeled_stock_native_s"] for r in records]
    solve = [(r["measured_mixed_solve"] or {}).get("cpu_s", 0) for r in records]
    publication = [r["measured_mixed_decision_and_publication"]["elapsed_s"] for r in records]
    remainder = [r["optimistic_ingress_remainder_s"] for r in records]
    scopes = {"all_other_work_free": [0] * len(records), "only_solver_cpu": solve,
              "full_decision_publication": publication,
              "full_decision_publication_and_optimistic_ingress": [p + i for p, i in zip(publication, remainder, strict=True)]}
    scenarios = {}
    for name, others in scopes.items():
        times = [n + o for n, o in zip(stock, others, strict=True)]
        adjusted = [n * transfer + o for n, o in zip(stock, others, strict=True)]
        scenarios[name] = dict(per_recording_s=times, anchor_projection=gates(records, times),
                               calibrated_on_weak_donor=gates(records, adjusted),
                               max_allowed_anchor_fraction=rate_threshold(records, others, stock))
    fixed_favorable = [n * transfer + p for n, p in zip(stock, publication, strict=True)]
    return dict(actual=gates(records, [r["successor_s"] for r in records]), scenarios=scenarios,
                max_ingress_fraction_with_weak_calibration=rate_threshold(records, fixed_favorable, remainder))


def weak_transfer(exact_path, mixed_path):
    body = gzip.decompress(exact_path.read_bytes())
    if digest(body) != EXACT_WEAK:
        raise ValueError("Expected the complete exact installed detector control")
    exact = json.loads(body)
    mixed, pin = read(mixed_path)
    native = exact["native_work"]
    b = mixed["receiver_audit"]["native"]
    if (not exact["qualified"] or mixed["native_sha256"] != MIXED_WEAK_NATIVE
            or mixed["receiver_audit"]["recording_authority"] != exact["stock_archival"]["science"]["raw_authority"]
            or sum(b["native_calls"].values()) != native["native_calls"]["full"] or "sha256:" + b["installed_sha256"] != DET):
        raise ValueError("Weak calibration donors must be the identical signed recording")
    x = native["native_cpu_ns"]["full"] / native["native_calls"]["full"] / 1e6
    y = b["native_cpu_ns"]["full"] / b["native_calls"]["full"] / 1e6
    sizes = [member["encoded"] for member in exact["candidate"]["members"] if member["chunk_index"]]
    hits = exact["snapshots"]["statistics"]
    if (len(sizes), sum(sizes)) != (hits["hits"], hits["hit_bytes"]):
        raise ValueError("Exact weak packet needs the same verified speculative member sizes")
    return dict(exact_full_thread_cpu_ms_per_lane=x, mixed_anchor_process_cpu_ms_per_lane=y,
                multiplier=x / y, exact_result_sha256=EXACT_WEAK, mixed_witness_sha256=pin, resident_prefetch_sizes=sizes)


def study(root, exact_path, mixed_path):
    ledger = (root / "rows.jsonl").read_bytes()
    donor = weak_transfer(exact_path, mixed_path)
    selected = [row for row in map(json.loads, ledger.splitlines()) if row["case"] in CASES and row.get("verified_pair")]
    records = []
    for case in CASES:
        installed, = [row for row in selected if row["case"] == case and row["algorithm"] == "installed"]
        successor, = [row for row in selected if row["case"] == case and row["algorithm"] == "successor"]
        records.append(field_pair(root, installed, successor))
    if any(not math.isfinite(r["installed_s"]) or r["installed_s"] <= 0 for r in records):
        raise ValueError("Budget needs a finite positive named comparator")
    successful_long = [r for r in records if r["installed_outcome"] == "complete" and r["full_eligible_lanes"] > 2000]
    return dict(scope="archived ten field pairs", no_raw_children=True, ledger_sha256=digest(ledger), weak=donor,
                cases=records, all_observed=summarize(records, donor["multiplier"]),
                successful_long_sensitivity=summarize(successful_long, donor["multiplier"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    parser.add_argument("exact_weak_receipt", type=Path)
    parser.add_argument("mixed_weak_bootstrap", type=Path)
    args = parser.parse_args()
    print(json.dumps(study(args.campaign.resolve(strict=True), args.exact_weak_receipt, args.mixed_weak_bootstrap),
                     sort_keys=True, allow_nan=False))
