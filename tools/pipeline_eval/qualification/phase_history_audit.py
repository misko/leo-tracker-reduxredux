"""Read the original first five phase fits without using position labels or refitting v5."""

import argparse
import json
import math
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from zipfile import ZipFile

from ..__main__ import encoded, local_output, read_predictions, save_json
from ..scoring import ARMS, distribution
from ..variants.v5_lean import SOURCE_SHA256
from . import initial_branch_audit, phase_budget, search_budget
from .initial_branch_audit import read_choices
from .prefix_figures import csv_file
from .search_budget import digest
from .v5_postfit import ARCHIVE, _map
from .v5_prefix_audit import DS29, value


def compare(histories, fifth_winner):
    """Use the original shared c=0 branch rule at both budgets."""
    if any(len(branch[arm]) != 5 for branch in histories for arm in ARMS):
        raise ValueError("expected the five original phase fits for each branch and arm")

    def choose(epoch):
        return min(range(len(histories)), key=lambda b: histories[b]["c0"][epoch]["score"])

    second = choose(1)
    if choose(4) != fifth_winner:
        raise ValueError("reconstructed five-fit branch differs from v5")
    rows = []
    for arm in ARMS:
        two = histories[second][arm][1]
        same_branch = histories[second][arm][4]
        five = histories[fifth_winner][arm][4]
        rows.append(
            dict(
                arm=arm,
                two_winner=second,
                five_winner=fifth_winner,
                shift_on_two_winner_km=math.dist(two["xy"], same_branch["xy"]),
                selected_initial_shift_km=math.dist(two["xy"], five["xy"]),
                after_two_max_phase_update_s=two["change"],
                after_five_max_phase_update_s=five["change"],
                two_selected_rf_rms_hz=two["rms"],
                five_selected_rf_rms_hz=five["rms"],
            )
        )
    return rows


def extract(record):
    ident = record["id"]
    root = ARCHIVE if ident.startswith("DS26-") else DS29
    path = root / f"{ident}-r0" / "baseline/experimental-evidence.zip"
    archive_sha = record["source_archive_sha256"]
    if digest(path) != archive_sha:
        raise ValueError(f"{ident} original numerical archive digest differs")
    histories = []
    with ZipFile(path) as archive:
        raw = archive.read("values.json")
        tag = encoded(["request_sha256", "sha256:" + record["input_sha256"]])
        if raw.count(tag) != 1:
            raise ValueError(f"{ident} original numerical request differs")
        branches, winner = read_choices(raw)
        del raw
        for branch in branches:
            fits = {}
            for arm, obj in _map(branch["arms"]).items():
                history = _map(obj)["phase_rounds"]
                if history[0] != "list":
                    raise ValueError("expected a list of original orbital phase fits")
                steps = []
                for epoch, entry in enumerate(history[1]):
                    step = _map(entry)
                    if step["epoch"] != epoch:
                        raise ValueError("phase history is out of order")
                    fit = _map(step["fit"])
                    steps.append(
                        dict(
                            score=value(fit["score"], archive),
                            xy=value(fit["parameters"], archive),
                            rms=value(fit["residual_rms_hz"], archive),
                            change=value(step["max_reference_change_s"], archive),
                        )
                    )
                fits[arm] = steps
            histories.append(fits)
    if winner != record["result"]["metrics"]["winning_rank"]:
        raise ValueError("cross-check of original selected branch failed")
    return [
        dict(recording=ident, archive_sha256=archive_sha, **row)
        for row in compare(histories, winner)
    ]


def audit(output, jobs):
    if jobs < 1:
        raise ValueError("positive worker count required")
    source = search_budget.REPORT / "initial-checkpoints"
    receipt = json.loads((source / "receipt.json").read_bytes())
    file = source / f"{initial_branch_audit.STOCK}.jsonl.gz"
    if receipt["scientific_source"] != SOURCE_SHA256 or receipt["files"][file.name] != digest(file):
        raise ValueError("initial-branch archive index differs from the published receipt")
    records = read_predictions(file)
    if sorted(records) != receipt["cases"]:
        raise ValueError("initial-branch archive index roster differs")
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        rows = [r for group in pool.map(extract, records.values()) for r in group]
    groups = []
    for arm in ARMS:
        for dataset in ("DS26", "DS29", "all"):
            entries = [
                r for r in rows if r["arm"] == arm and dataset in ("all", r["recording"][:4])
            ]
            groups.append(
                dict(
                    arm=arm,
                    dataset=dataset,
                    recordings=len(entries),
                    different_branch=sum(r["two_winner"] != r["five_winner"] for r in entries),
                    **{
                        k: distribution(r[k] for r in entries)
                        for k in (
                            "selected_initial_shift_km",
                            "shift_on_two_winner_km",
                            "after_two_max_phase_update_s",
                            "after_five_max_phase_update_s",
                        )
                    },
                )
            )
    csv_file(output / "initial-phase-history.csv", rows)
    save_json(
        output / "initial-phase-history.json",
        dict(
            source_receipt_sha256=digest(source / "receipt.json"),
            groups=groups,
            table_sha256=digest(output / "initial-phase-history.csv"),
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=phase_budget.REPORT)
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    audit(local_output(args.out), args.jobs)
