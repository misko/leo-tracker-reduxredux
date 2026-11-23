"""Transfer dense survey stage fractions onto the historical 4/16 release clocks."""

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path

from staged_budget import CLOCK_SHA, ROOT, acquisition_allowance, checked, gates, stage_rows


def estimate():
    acquisitions = ROOT / "measurements/acquisition-split-DS30-0008.json"
    scores = ROOT / "measurements/survey-channels.json"
    roster = ROOT / "development/stages.json"
    measured = json.loads(acquisitions.read_bytes())
    dense = json.loads(scores.read_bytes())["cases"]["DS30-0008"]
    if measured["raw_authority"] != dense["input"]["raw_authority"]:
        raise ValueError("Acquisition and solve describe different recordings")
    detector = list(measured["detector_groups"].values())
    admitted = dense["mask"]["admitted_visits"]
    if sum(group["visits"] for group in detector) != admitted:
        raise ValueError("Visit counts differ between the acquisition and survey")
    acquisition = measured["outside_detector_cpu_s"] + (
        sum(group["cpu_s"] for group in detector) * dense["mask"]["paid_visits"] / admitted)
    acquisition_fraction = acquisition / measured["in_process_to_solver_cpu_s"]
    solve_fraction = dense["decision"]["charged"]["elapsed_s"] / dense["baseline_clocks"]["v3"]["elapsed_s"]
    source = checked(ROOT / "first-55/stage-clocks.csv", CLOCK_SHA)
    clocks = {row["recording"]: row for row in csv.DictReader(source.decode().splitlines())}
    result = {}
    for size, batch in json.loads(roster.read_bytes())["stages"].items():
        for case, elapsed in batch["unsplit_failures_charged_in_full"].items():
            clocks[case] = dict(launch_to_detections_s=0, detections_to_terminal_s=0,
                                terminal_to_exit_s=elapsed, elapsed_s=elapsed)
        stages = stage_rows(batch["cases"], clocks)
        median, summed = gates(stages, acquisition_fraction, solve_fraction)
        result[size] = dict(median_paired_ratio=median, summed_ratio=summed,
                            max_acquisition_fraction=acquisition_allowance(stages, solve_fraction))
    return dict(acquisition_cpu_s=acquisition, acquisition_fraction=acquisition_fraction,
                through_evidence_cpu_s=acquisition + dense["decision"]["charged"]["cpu_s"],
                solve_elapsed_fraction=solve_fraction, projected_stages=result,
                source_sha256={p.name: sha256(p.read_bytes()).hexdigest() for p in (acquisitions, scores, roster)})


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    with cli.parse_args().output.open("x") as stream:
        json.dump(estimate(), stream, indent=2, allow_nan=False)
        stream.write("\n")
