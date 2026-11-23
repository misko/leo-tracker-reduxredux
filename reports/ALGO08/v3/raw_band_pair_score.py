"""Verify a frozen raw visit-band pair and score both calibration arms."""

import argparse
import json
from pathlib import Path

from raw_0016_best_score import ARMS, process_rows
from raw_0016_best_trial import FLAGS, seal, sha
from raw_band_pair import BAND, selection


def paired_error_delta(geographic):
    runs = geographic["runs"]
    reference = runs["stock"]["horizontal_error_km"]
    candidate = runs["candidate"]["horizontal_error_km"]
    return {arm: 1e3 * (candidate[arm] - reference[arm]) if None not in (candidate[arm], reference[arm]) else None
            for arm in ARMS}


def score(root, output, selected=BAND):
    from aperture_trial import write
    from triage_bounds import calibration_comparison

    inputs = selected.inputs
    workload = inputs.workload
    witness = (root/"prediction-seal.json").read_bytes()
    if json.loads(witness) != seal(root, workload.order):
        raise ValueError("Sealed child outputs changed before scoring")
    admission = json.loads((root/"admission.json").read_bytes())
    if (admission["selection"] != selection(selected) or admission["case"] != workload.id
            or admission["binding"] != workload.binding_sha or tuple(admission["order"]) != workload.order
            or admission["inventory"] != inputs.inventory or admission["archive"]["sha256"] != inputs.archive
            or admission["cutoff_utc_ns"] != inputs.cutoff_ns or admission["issued"] != workload.windows
            or admission["admitted"] != inputs.admitted or tuple(admission["route_flags"]) != FLAGS):
        raise ValueError("Execution admission differs from the selected signed original")
    rows = process_rows(root, admission, inputs)
    stock, candidate = rows["stock"], rows["candidate"]
    clocks = {name: run["process"]["clock"] for name, run in rows.items()}
    if (candidate["opportunities"] != stock["opportunities"] or candidate["probes"] != stock["probes"]
            or any(clocks[a]["started_unix_ns"] >= clocks[b]["started_unix_ns"]
                   for a, b in zip(workload.order, workload.order[1:]))):
        raise ValueError("The predeclared order or physical opportunity equality failed")
    geographic = calibration_comparison({name: run["science"] for name, run in rows.items()}, workload.id)
    stock_owners, candidate_owners = (run["science"]["owners"] for run in (stock, candidate))
    write(output, dict(pre_score_sha256=sha(witness), admission=admission, original=rows, geographic=geographic,
                       error_delta_m=paired_error_delta(geographic), conditioning=json.loads((root/"conditioning.json").read_bytes()),
                       verification=dict(same_opportunities=True,
                                         same_terminal_state=stock["science"]["receipt"]["decision"] == candidate["science"]["receipt"]["decision"],
                                         same_arm_owners={arm: stock_owners[arm] == candidate_owners[arm]
                                                          if arm in stock_owners and arm in candidate_owners else None
                                                          for arm in ARMS}),
                       speedup=clocks["stock"]["elapsed_s"]/clocks["candidate"]["elapsed_s"],
                       cpu_speedup=clocks["stock"]["cpu_s"]/clocks["candidate"]["cpu_s"]))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    score(args.root, args.output)
