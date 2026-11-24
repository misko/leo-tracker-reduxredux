"""Assign, launch and reduce the fifth independently enrolled saved pair."""

import argparse
from gzip import decompress
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
import sys

from reports.ALGO08.v3 import ds30_0163_combined as combined
from reports.ALGO08.v3.nomination_handoff_0419_admission import enrollment
from reports.ALGO08.v3.nomination_handoff_0419_local import launch as prepare


CASE = "DS30-0173"
RANK_HASH = "10ea86209dc7e863cce7c4149b8920876d4a754385ef3ddf9d284c7f9d2f864e"
PAIR_PIN = "1a9ff1294c23b4ee162c883a339df60bf4469fb39207d62a5e9ba4020a0be5e4"
EARLIER = Path(__file__).with_name("measurements") / "ds30-0163-combined.json.gz"
EARLIER_PIN = "76121104353dfad92fe5f325a57bf0f8bcc10adc915a44093a3182970eb9c40e"
INPUTS = dict(
    native_sha256="d367716257b431537296e66f00835b214c8837428e18ec2af92e8da187d0f8df",
    inventory_sha256="b509df18a0649101840de09bb0e5bc46bbf22af4bcbacee9db13eaad3ae1eca4",
    offer_sha256="2698d6858da0a2d989d8c2185c9e3bbbba20d539988204c1f93a591eb9471236",
    terminal_sha256="sha256:afdd2d7838e9e57172ac5bf71e7c51ef29eeb4823b75854fa87b0ef6db42d8df",
    archive_sha256="sha256:aaf1d16e45645d5a6b8fb975f5ce81bfe67076795f58086b71bdf9d92a6821ad",
    frozen_specification="sha256:6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f",
    cutoff_utc_ns=1794801660638609596, issued=6773, admitted=4733, probes=9466, factors=3393,
)


def assigned():
    assignment = enrollment(ranked=5, case=CASE, ranking_hash=RANK_HASH, pair_pin=PAIR_PIN)
    return assignment | {"order": assignment["planned_order"], "archived_pair_sha256": PAIR_PIN}


def launch(output):
    job_root = output.with_name(output.name + "-ready")
    prepare(job_root, assign=assigned, execute=False, expected_inputs=INPUTS)
    combined.launch_fresh(output, job_root=job_root, assign=assigned)


def summed(controls, candidates):
    return dict(installed=sum(controls), routed=sum(candidates),
                summed_speedup=sum(controls) / sum(candidates),
                reciprocal_median_ratio=1 / median(b / a for a, b in zip(controls, candidates, strict=True)))


def independent_pool(earlier, current):
    studies = (earlier, current)
    modes = ("installed", "routed")
    if ([row["case"] for row in studies] != ["DS30-0163", CASE]
            or any(row["admission"]["sources"] != earlier["admission"]["sources"] for row in studies)):
        raise ValueError("The combined blind pool changed its cases or computational source")
    timings = {}
    for metric in ("elapsed_s", "cpu_s"):
        naked = [[row["time"][metric][mode] for row in studies] for mode in modes]
        common = [row["paid_setup_and_time"][metric]["combined_setup"] for row in studies]
        charged = [[x + setup for x, setup in zip(arm, common, strict=True)] for arm in naked]
        timings[metric] = dict(worker=summed(*naked), admission_charged=summed(*charged),
                               admission_by_case=dict(zip((row["case"] for row in studies), common, strict=True)),
                               failed_start_by_case={row["case"]: row["paid_setup_and_time"][metric]["failed_start"]
                                                     for row in studies})
    decisions = {row["case"]: {mode: row["jobs"][mode]["decision"] for mode in modes} for row in studies}
    return dict(
        cases=list(decisions), enrolled_cases=len(decisions), clock_pairs=len(studies), decisions=decisions,
        fixes={mode: sum(case[mode] == "complete" for case in decisions.values()) for mode in modes},
        withholds={mode: sum(case[mode] == "withheld" for case in decisions.values()) for mode in modes},
        failed_workers={mode: sum(case[mode] == "failed" for case in decisions.values()) for mode in modes},
        measured_worker_order={row["case"]: row["admission"]["actual_worker_order"] for row in studies},
        candidate_minus_installed_horizontal_m={
            row["case"]: row["candidate_minus_installed_horizontal_m"] for row in studies},
        comparable_position_pairs={
            arm: sum(row["candidate_minus_installed_horizontal_m"][arm] is not None for row in studies)
            for arm in ("c0", "fitted_c")},
        timing=timings,
    )


def reduce_pool(current):
    body = decompress(EARLIER.read_bytes())
    if sha256(body).hexdigest() != EARLIER_PIN:
        raise ValueError("The earlier sealed blind control changed")
    return independent_pool(json.loads(body), current)


if __name__ == "__main__":
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "score"))
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    if args.action == "launch":
        launch(args.output)
    else:
        combined.score(args.output, assign=assigned, case=CASE, pair_pin=PAIR_PIN, reduce_pool=reduce_pool)
