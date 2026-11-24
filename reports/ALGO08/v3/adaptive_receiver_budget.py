"""Translate observed saved-publication ratios into conditional full-receiver budgets."""

import argparse
import gzip
import json
from hashlib import sha256
from math import isfinite

from acquisition_throughput import minimum_rate
from regional_dense_budget import DATA, HERE, select
from staged_budget import checked
from tools.pipeline_eval.qualification.score_paired_holdout import elapsed_ratios


RAW_CLOCKS_SHA = "fc46925e68437054169e2a3008388493554baf5c92f495eb3beb9434c10e620a"


def receiver_budget(rows, publication_speedup):
    """Uniform effective MB/s from launch to sealed detections, including I/O waits."""
    if publication_speedup <= 0 or not rows:
        raise ValueError("A positive publication speedup and an enrolled panel are required")
    combined = []
    for row in rows:
        acquisition, solve, tail = row["stages"]
        # The measured saved clocks include figures and process exit. For cases
        # without a stage split the original budget function charges the full clock.
        combined.append(dict(row, stages=(acquisition, solve + tail, 0)))
    rates = [minimum_rate(combined, 1 / publication_speedup, gate) for gate in (0, 1)]
    return dict(median_MB_s=rates[0], summed_MB_s=rates[1],
                both_MB_s=None if None in rates else max(rates))


def report():
    held = json.loads(gzip.decompress(checked(DATA / "held-adaptive-0160.json.gz",
        "f5245f109ddd368c5ced7e55bb9e21cde6fbf053a7585f0ec0dd24a1d491d91c")))
    dense = json.loads(gzip.decompress(checked(DATA / "named-hybrid-baseline.json.gz",
        "d9c03be94e87bd34ccfa2f96330eebb097d3349be39fb166d81acd578ed5eb55")))["result"]["document"]
    speeds = dict(unchanged=1.0, held_medium=held["speedup"]["elapsed_s"],
                  dense_first_use=dense["saved_elapsed_speed_ratio_first_use"],
                  dense_prebuilt=dense["saved_elapsed_speed_ratio"])
    rows = json.loads(checked(DATA / "acquisition-throughput.json", RAW_CLOCKS_SHA))["rows"]
    stages = json.loads(checked(HERE / "development/stages.json",
        "0bc940b1181b6fdb5f52ec1c5b768bfdbd6d2334e721fe8350cfc9ad3ca643c3"))["stages"]
    groups = {size: select(rows, [r["case"] for r in stages[size]["cases"]]) for size in ("4", "16")}
    groups["55"] = rows
    return {size: {name: receiver_budget(group, speed) for name, speed in speeds.items()}
            for size, group in groups.items()}


def matched_budget(raw, saved):
    """Transfer only the within-case saved time difference to v3's raw downstream clock."""
    acquisition, solve, tail = raw["stages"]
    named, candidate = (saved[mode]["elapsed_s"] for mode in ("named", "candidate"))
    mb = raw["compressed_MB"]
    if not all(isfinite(v) and v > 0 for v in (acquisition, solve, tail, named, candidate, mb)):
        raise ValueError("Expected complete positive acquisition, publication and byte counts")
    downstream = solve + tail - (named - candidate)
    if downstream <= 0:
        raise ValueError("Saved wall reduction exceeds original raw downstream time")
    total = acquisition + solve + tail
    available = total / 2 - downstream
    return dict(raw_v3_s=total, original_acquisition_s=acquisition, saved_improvement_s=named-candidate,
                modeled_downstream_s=downstream, acquisition_budget_s=available, compressed_MB=mb,
                required_MB_s=mb/available if available > 0 else None)


def exact_case_report(size=3):
    panels = {
        3: ("exact-named-saved-panel.json", "1b78a16f6ca23ca7dad27db73b482aeda6ab1858343118d7e9815b5a7622385b"),
        4: ("exact-named-saved-panel-four.json", "ffabb26e6e518afc44e026396efa06ce28609e1380223090bfb2bb6a85902b43"),
    }
    filename, digest = panels[size]
    panel = json.loads(checked(DATA / filename, digest))
    raw = json.loads(checked(DATA / "acquisition-throughput.json", RAW_CLOCKS_SHA))["rows"]
    prefixes = json.loads(gzip.decompress(checked(DATA / "physical-stage-envelope.json.gz",
        "f8ec74a516fe6682a3f08b133a6a3a180052734ccbcc30f4ef585d9e089d24bf")))
    cases = {}
    hashes = panel["earlier_receipts"] | {"0374": panel["dense_receipt_sha256"]}
    if size == 4:
        hashes["0402"] = panel["fourth_receipt_sha256"]
    for row in select(raw, list(panel["per_case"])):
        case = row["case"]
        content = gzip.decompress((DATA / f"exact-named-{case}.json.gz").read_bytes())
        evidence = json.loads(content)
        receipt = evidence["artifacts"]["named"]["worker"]["receipt"]
        if (sha256(content).hexdigest() != hashes[case.split("-")[1]] or not evidence["exact"]
                or receipt["session_id"] != "fast-" + row["inventory_sha256"].removeprefix("sha256:")[:32]
                or receipt["window_count"] != row["windows"] or evidence["clocks"] != panel["per_case"][case]["clocks"]):
            raise ValueError(f"Raw and saved evidence do not match for {case}")
        cases[case] = matched_budget(row, evidence["clocks"])
    verify = [a["cpu_ns"] for a in prefixes["arms"] if a["arm"] == "verify"]
    # Credit the faster CPU-only traversal with zero I/O wait and zero detector cost.
    rate = prefixes["nominal_compressed_bytes_per_arm"] * 1e3 / min(verify)
    projected = [(r["raw_v3_s"], r["modeled_downstream_s"] + r["compressed_MB"]/rate)
                 for r in cases.values()]
    median_gate, summed_gate = elapsed_ratios(projected)
    return dict(cases=cases, hypothetical_verify_only_MB_s=rate,
                median_ratio_at_verify_only_rate=median_gate, summed_ratio_at_verify_only_rate=summed_gate)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--exact-cases", type=int, nargs="?", const=3, choices=(3, 4),
                     help="Use the three- or four-recording panel's measured solver savings (default 3)")
    exact_cases = cli.parse_args().exact_cases
    print(json.dumps(exact_case_report(exact_cases) if exact_cases else report(), indent=2, allow_nan=False))
