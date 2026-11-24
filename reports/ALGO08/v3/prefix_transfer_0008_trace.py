"""Localize the untouched-suffix changes using only the sealed paid traces."""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from statistics import median
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from prefix_transfer_0008 import ORDER, checked, write
from prefix_transfer_0419 import observation_id


RESULT = "a6ec2ebafcd8794c2ffebff34ca646155ce9c0c24825f79021e40e73c507f8ed"


def diagnostic(root):
    from cropped_physical_iq_gate import SOURCE, SOURCE_SHA256
    from leo.contracts.fast_scan_native import FastScanPolicyV2

    result = json.loads(checked(root/"result.json", RESULT))
    sealed = json.loads(checked(root/"prediction-seal.json", result["prediction_sha256"]))
    native = json.loads(checked(SOURCE, SOURCE_SHA256))
    threshold = FastScanPolicyV2().strong_margin
    observations = {observation_id(native["source"]["session_id"], row): row for row in native["source"]["probes"]}
    switches = {}
    for arm, modes in result["switched_rosters"].items():
        switches[arm] = {x["id"]: x for x in modes["suffix"]["switched_lanes"]
                         if x["before"] and x["after"] and x["before"][0] != x["after"][0]}
    if switches["c0"] != switches["fitted_c"]:
        raise ValueError("The recorded calibration arms have different suffix transitions")
    relevant = switches["c0"]
    pairs = Counter((row["before"][0], row["after"][0]) for row in relevant.values())
    by_role = defaultdict(list)
    for key, row in relevant.items():
        factor, = observations[key]["candidates"]
        by_role[row["before"][1]].append(factor["fractional_margin"])
    traces, curves = {}, {}
    for mode in ORDER:
        names = [f"{mode}/routed/candidate/ports.json", f"{mode}/routed/risk-route.json"]
        ports, source = (json.loads(checked(root/name, sealed[name])) for name in names)
        route, = source["solves"]
        attempt, = route["lean_attempts"]
        cold = attempt["cold"]
        rank, = ports["rank"]
        traces[mode] = dict(
            graph={key: ports["graph"]["graph"][key] for key in ("assigned", "edges", "tracks")},
            rank_nodes=rank["nodes"], catalogue=cold["catalogue"],
            priors={key: value["catalogue_sha256"] for key, value in route["choice"]["census"]["prior"].items()},
            route=route["choice"]["route"], reason=route["choice"]["reason"], winner=cold["branch"],
            winner_position=cold["east_north_km"], first_saved_prefix=cold["prefix"][0],
            conditional_first=attempt["support"]["initial_curved"],
            confidence_counts=[row["scored_tracks"] for row in attempt["sensitive_confidence"]])
        curves[mode] = route["lean_final_fit"]["arms"]["c0"]["curves"]
    a, b = (curves[mode] for mode in ORDER)
    retained = []
    for name, curve in a.items():
        shared = set(curve["ids"]) & relevant.keys()
        if shared and name in b:
            other = b[name]
            if curve["ids"] == other["ids"] and set(curve["ids"]) == shared and curve["alias"] == other["alias"]:
                retained.append(dict(curve=name, alias=curve["alias"], old=curve["norad"], new=other["norad"], count=len(shared)))
    confidence = {role: dict(count=len(rows), below_strong_margin=sum(v < threshold for v in rows),
                          minimum=min(rows), median=median(rows), maximum=max(rows)) for role, rows in by_role.items()}
    return dict(scored_sha256=RESULT, prediction_sha256=result["prediction_sha256"],
                transitions=[dict(old=a, new=b, count=n) for (a,b), n in sorted(pairs.items())],
                visit_range=[min(x["visit_index"] for x in relevant.values()), max(x["visit_index"] for x in relevant.values())],
                unchanged_curve_rows=retained, native_strong_margin=threshold, native_margin_by_prior_role=confidence,
                stages=traces, analyses=0, waveform_reads=0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    write(args.output, diagnostic(args.root))
