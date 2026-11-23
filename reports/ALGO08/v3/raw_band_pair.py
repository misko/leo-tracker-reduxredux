"""Select an original DS30 case by issued visits and run the current whole raw pair."""

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from re import fullmatch

from raw_0016_best_trial import HERE, PairInputs, launch
from short_raw_0180 import BULK, Workload, checked


COHORT = HERE.parents[1] / "2026_11_21_ds30_full" / "cohort.json"
COHORT_SHA = "e7820b05f5ac829fa65860e0ae53cc523edd9ab9160d46216b071c86ff0deb20"
CHECKOUT = "b48d3d64cd618a5704bc203abd9ccc03fe21b1e9"
PROTOCOL_SHA = "384b59963b938a99e717c5f44214aacb3d5eebe153087dced5d4e9cc433db9e4"


@dataclass(frozen=True)
class Selection:
    minimum: int
    maximum: int
    inputs: PairInputs


BAND = Selection(
    384, 511,
    PairInputs(
        Workload("DS30-0306", BULK / "leo-dev/ds30-full-20261121/bindings/DS30-0306.json",
                 "c8fd4ee3378a80285d489d0fb6f0beff937f8c9ae0e326e7665e25d5d3278d44",
                 405, 46, 491_238_921, 520_000_000, ("stock", "candidate"), True),
        7, 398, 1794992226324353171,
        "sha256:f6a67cb771d46422ad71f49443e4997761728de231e3d821ffc2f781cd8af3e0",
        "sha256:6d2a2d45e60a3ca31f46be07037a13db85cfc693151ddc1332b9afad7714c1b8",
    ),
)


def select_member(members, minimum, maximum):
    """Order only by issued visits and the cohort's dataset label."""
    if (minimum < 1 or maximum < minimum or len({row["id"] for row in members}) != len(members)
            or any(not fullmatch(r"DS30-\d{4}", row["id"]) or type(row["windows"]) is not int
                   or row["windows"] < 0 for row in members)):
        raise ValueError("Invalid visit band or cohort identities")
    eligible = sorted((row for row in members if minimum <= row["windows"] <= maximum),
                      key=lambda row: (row["windows"], row["id"]))
    if not eligible:
        raise ValueError("No originals in the predeclared visit band")
    return eligible


def selection(selection=BAND):
    cohort = json.loads(checked(COHORT, COHORT_SHA))
    members = cohort["members"]
    eligible = select_member(members, selection.minimum, selection.maximum)
    winner = eligible[0]
    workload = selection.inputs.workload
    if len(members) != 455 or (winner["id"], winner["windows"]) != (workload.id, workload.windows):
        raise ValueError("Pinned whole-raw enrollment differs from the visit-count selection")
    return dict(checkout=CHECKOUT, cohort_sha256=COHORT_SHA, cohort_size=len(members),
                band=[selection.minimum, selection.maximum], order_by=["issued_visits", "dataset_label"],
                eligible=[dict(dataset_label=row["id"], issued_visits=row["windows"]) for row in eligible],
                recording_state=winner["recording_state"], protocol_sha256=PROTOCOL_SHA)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    checked(HERE/"raw-band-pair-protocol.md", PROTOCOL_SHA)
    launch(args.root, BAND.inputs, selection=selection())
