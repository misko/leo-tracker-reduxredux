"""Price the isolated short-verifier experiment at the observed DS30 call mix."""

import argparse
import gzip
import json
from math import fsum
from pathlib import Path
from statistics import median

from .ds30_routing_first64 import CASE_KEY, EXPORT, restricted_json
from .field_speed_reachability import checked, gates
from .receiver_solver_targets import aperture_seconds, targets


MEASUREMENTS = Path(__file__).with_name("measurements")
CLOCKS = "122de8ddfdf498f6f372f6f3896387b6ede886b4b136c180aa3e45f4da783c03"
DONOR = "7af4ceb7167ba5cbb16b980bdfaf7029a88a130b83fe59b04316a62b75be5614"
SHORT = "c5b57b0602e81a6a85c14caf648eb12341f098d09915b4d3f705094ed309574c"
FULL = "2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5"


def counts(native, row):
    if (native["short_primary_sha256"], native["installed_sha256"]) != (SHORT, FULL):
        raise ValueError("Different receiver implementation")
    for clock, field in (("native_cpu_ns", "native_detector_process_cpu_s"), ("native_wall_ns", "native_detector_s")):
        aperture_seconds(native[clock], row[field])
    calls = native["native_calls"].get("short_primary", 0)
    positive = native["factors"].get("short_primary", 0)
    if any(type(n) is not int for n in (calls, positive)) or not 0 <= positive <= calls:
        raise ValueError("Unexpected short call or single-factor count")
    return dict(positive=positive, empty=calls-positive, short_cpu=native["native_cpu_ns"].get("short_primary", 0)/1e9,
                short_wall=native["native_wall_ns"].get("short_primary", 0)/1e9)


def transfer(row, prices):
    seconds = fsum(row[k] * prices[k] / 1e9 for k in ("empty", "positive"))
    return min(seconds, row["short_cpu"], row["short_wall"])


def timing(rows, saving):
    result = gates(rows, saving)
    return dict(summed_speedup=1/result["sum_ratio"], median_paired_speedup=1/result["paired_median_ratio"],
                seconds_removed=result["saving"], remaining_seconds_to_half=result["gap_to_half"])


def run(snapshot, campaign):
    field = json.loads(gzip.decompress(checked(MEASUREMENTS / "first64-producer-transfer.json.gz", CLOCKS)))
    donor = json.loads(checked(MEASUREMENTS / "short-shared-integer-phase.json", DONOR))
    roster = {row["case"]: row for row in field["rows"]}
    rows = []
    for line in restricted_json(checked(snapshot, EXPORT).splitlines(), CASE_KEY, roster):
        record = json.loads(line)
        if record["algorithm"] != "successor":
            continue
        row = roster[record["case"]]
        if not record["verified_pair"] or record["attempt_result_sha256"] != row["pins"]["result"]:
            raise ValueError("Different selected field attempt")
        packet = (campaign / record["attempt"]).resolve().parent / "publication/unified-short-bootstrap.json"
        if not packet.resolve().is_relative_to(campaign.resolve()):
            raise ValueError("Packet outside the campaign")
        native = json.loads(checked(packet, row["pins"]["raw"]))["receiver_audit"]["native"]
        rows.append({key: row[key] for key in ("case", "stock_wall_s", "actual_wall_s")} | counts(native, row))
    if len(rows) != 64 or {row["case"] for row in rows} != set(roster):
        raise ValueError("Expected exactly the first 64 paired recordings")
    # The field export and producer receipt use different case orders.
    by_case = {row["case"]: row for row in rows}
    rows = [by_case[key] for key in roster]
    results = {}
    for name, estimate in donor["field_price"]["estimate_by_donor"].items():
        rounds = estimate["by_outcome"]
        prices = {key: median(rounds[key]["paired_saved_ns"]) for key in ("empty", "positive")}
        repeated = [timing(rows, [transfer(row, dict(empty=a, positive=b)) for row in rows])
                    for a, b in zip(rounds["empty"]["paired_saved_ns"], rounds["positive"]["paired_saved_ns"], strict=True)]
        kernel_credit = [transfer(row, prices) for row in rows]
        combinations = {}
        for source, scope in (("0049_slots_first_bytes", "producer_cpu_if_wall"),
                              ("0016_natural_combined_bytes", "acquisition_non_native_wall")):
            inputs = field["alternatives"][source]["individual"]
            saved = [kernel + item[scope] for kernel, item in zip(kernel_credit, inputs, strict=True)]
            combinations[source] = timing(rows, saved)
        results[name] = dict(prices_ns=prices, projected=timing(rows, kernel_credit), six_matched_rounds=repeated,
                             with_input_transport=combinations)
    costs = [(r["stock_wall_s"], r["actual_wall_s"], 0., r["short_wall"]) for r in rows]
    return dict(clocks_sha256=CLOCKS, donor_sha256=DONOR, export_sha256=EXPORT,
                totals={key: sum(r[key] for r in rows) for key in ("positive", "empty", "short_cpu", "short_wall")},
                unchanged=timing(rows, [0.]*len(rows)), donors=results, zero_cost_short=timing(rows, [r["short_wall"] for r in rows]),
                required_uniform_short_wall_reduction=targets(costs, 1.), rows=rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("campaign", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.snapshot, args.campaign), indent=2, allow_nan=False))
