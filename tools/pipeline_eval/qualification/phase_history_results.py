"""Compare archived early-stop checkpoints with the original initial and final endpoints."""

import argparse
import gzip
import json
import math
from collections import Counter
from pathlib import Path

from ..__main__ import local_output, save_json
from ..scoring import ARMS, distance_km, distribution
from . import prefix_figures
from . import stable_phase_history_audit as audit
from .full_v5_check import _sha

HISTORIES = "phase-histories.jsonl.gz"
FILES = {audit.METHOD: "positions.jsonl.gz", audit.CONTROL: "five-round-positions.jsonl.gz"}
BOUNDARY = "Archived initial-only diagnostic from the original v5 phase-refresh trajectory"


def prediction(row, *, control):
    selected = row["original_rank"] if control else row["stopped_rank"]
    arms = row["original_initial" if control else "stopped_initial"]
    return dict(
        {
            k: row[k]
            for k in (
                "id",
                "native_sha256",
                "catalog_sha256",
                "input_sha256",
                "source_archive_sha256",
            )
        },
        method=audit.CONTROL if control else audit.METHOD,
        result=dict(
            status="ok",
            boundary=BOUNDARY,
            arms=arms,
            metrics=dict(
                checkpoint_only=True,
                cold_rank=selected,
                rounds={
                    arm: audit.ROUNDS
                    if control
                    else 1 + row["branches"][selected][arm]["stop_index"]
                    for arm in ARMS
                },
            ),
        ),
    )


def summarize(histories, evaluated, branch_rows):
    counts = {}
    for arm in ARMS:
        branches = [r for r in branch_rows if r["arm"] == arm]
        rows = [r for r in evaluated if r["arm"] == arm]
        saved = sum(r["updates_saved"] for r in branches)
        budget = audit.ROUNDS * len(branches)
        counts[arm] = dict(
            branch_fits=len(branches),
            original_rounds=budget,
            potential_rounds_saved=saved,
            potential_fraction_saved=saved / budget,
            branches_stopping_before_final=sum(r["updates_saved"] > 0 for r in branches),
            stops_by_zero_based_epoch=dict(
                Counter(str(r["stop_epoch"]) for r in branches if r["settled"])
            ),
            selected_branch_rounds_saved=sum(r["selected_updates_saved"] for r in rows),
            selected_branch_savings_cases=sum(r["selected_updates_saved"] > 0 for r in rows),
            displacement_from_original_initial_m=distribution(r["initial_shift_m"] for r in rows),
            initial_shift_among_saved_cases_m=distribution(
                r["initial_shift_m"] for r in rows if r["selected_updates_saved"]
            ),
            displacement_from_final_m=distribution(r["final_shift_m"] for r in rows),
            errors_km={
                key: distribution(r[key] for r in rows)
                for key in (
                    "stopped_error_km",
                    "original_initial_error_km",
                    "original_final_error_km",
                )
            },
            conditional_rms_hz={
                key: distribution(r[key] for r in rows)
                for key in ("stopped_rms_hz", "original_initial_rms_hz", "original_final_rms_hz")
            },
            stopped_minus_original_initial_rms_hz=distribution(
                r["stopped_rms_hz"] - r["original_initial_rms_hz"] for r in rows
            ),
        )
    changed = [r["id"] for r in histories if r["original_rank"] != r["stopped_rank"]]
    return dict(
        case_count=len(histories),
        branch_counts=dict(Counter(str(len(r["branches"])) for r in histories)),
        changed_c0_winner_ids=changed,
        arms=counts,
    )


def write_results(output):
    lock = json.loads((output / "audit-lock.json").read_bytes())
    path = output / HISTORIES
    if (
        _sha(path) != lock["files"][HISTORIES]
        or _sha(Path(audit.stable_phase.__file__)) != lock["rule_sha256"]
        or _sha(Path(audit.__file__)) != lock["audit_sha256"]
    ):
        raise ValueError("archived phase history or frozen audit source changed")
    with gzip.open(path, "rt") as source:
        histories = list(map(json.loads, source))
    refs = prefix_figures.load_rows(prefix_figures.REPORT)
    if lock["cases"] != [r["id"] for r in histories] or set(lock["cases"]) != set(refs):
        raise ValueError("phase history does not cover the complete matched roof cohort")

    files = {HISTORIES: _sha(path)}
    for key, name in FILES.items():
        files[name] = audit.pack(
            output, name, (prediction(row, control=key == audit.CONTROL) for row in histories)
        )
    plot_lock = dict(
        cases=lock["cases"], files=files, audit_lock_sha256=_sha(output / "audit-lock.json")
    )
    save_json(output / "prediction-lock.json", plot_lock)
    evaluated, branch_rows = [], []
    for row in histories:
        ident = row["id"]
        ref = refs[ident][0]
        for index, branch in enumerate(row["branches"]):
            for arm, data in branch.items():
                stop = data["stop_index"]
                point = data["rounds"][stop]
                branch_rows.append(
                    dict(
                        id=ident,
                        dataset=row["dataset"],
                        arm=arm,
                        rank=index,
                        original_winner=index == row["original_rank"],
                        stopped_winner=index == row["stopped_rank"],
                        stop_epoch=stop,
                        updates_saved=audit.ROUNDS - stop - 1,
                        raw_phase_change_s=point["raw_phase_change_s"],
                        movement_km=point["movement_km"],
                        settled=stop >= 1
                        and point["raw_phase_change_s"] <= audit.stable_phase.PHASE_SECONDS
                        and point["movement_km"] <= audit.stable_phase.POSITION_KM,
                        stopped_objective=point["objective"],
                        five_round_objective=data["rounds"][-1]["objective"],
                        stopped_rms_hz=point["conditional_rms_hz"],
                        five_round_rms_hz=data["rounds"][-1]["conditional_rms_hz"],
                        stopped_to_five_round_local_m=1000
                        * math.dist(point["east_north_km"], data["rounds"][-1]["east_north_km"]),
                    )
                )
        for arm in ARMS:
            stopped, original, final = (
                row[key][arm] for key in ("stopped_initial", "original_initial", "original_final")
            )
            evaluated.append(
                dict(
                    id=ident,
                    dataset=row["dataset"],
                    arm=arm,
                    original_rank=row["original_rank"],
                    stopped_rank=row["stopped_rank"],
                    selected_updates_saved=audit.ROUNDS
                    - 1
                    - row["branches"][row["stopped_rank"]][arm]["stop_index"],
                    stopped_error_km=distance_km(stopped["latlon"], ref["truth"]),
                    original_initial_error_km=distance_km(original["latlon"], ref["truth"]),
                    original_final_error_km=distance_km(final["latlon"], ref["truth"]),
                    initial_shift_m=1000 * distance_km(stopped["latlon"], original["latlon"]),
                    final_shift_m=1000 * distance_km(stopped["latlon"], final["latlon"]),
                    stopped_rms_hz=stopped["rf_rms_hz"],
                    original_initial_rms_hz=original["rf_rms_hz"],
                    original_final_rms_hz=final["conditional_rms_hz"],
                )
            )
    prefix_figures.csv_file(output / "per-branch-arm.csv", branch_rows)
    prefix_figures.csv_file(output / "per-recording.csv", evaluated)
    save_json(output / "summary.json", summarize(histories, evaluated, branch_rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=local_output, default=audit.REPORT)
    write_results(parser.parse_args().out)


if __name__ == "__main__":
    main()
