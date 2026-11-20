"""Replay the frozen cumulative gate on disjoint 25 km offers."""

import argparse
from math import cos, radians
from pathlib import Path
from unittest.mock import patch

from .. import cavity_runtime, whole_iq
from ..__main__ import local_output, save_json
from . import sequential_fix_trial as trial
from .full_v5_check import _sha

REPORT = trial.REPORT / "omitted"
OFFER = "east-30-km"


def east_offer(tile):
    lat, lon = tile["center"]
    width = tile.get("width_km", 25.0)
    if width != 25.0:
        raise ValueError("this control binds the original 25 km offer")
    longitude_km = 111.32 * cos(radians(lat))
    east = lon + 30.0 / longitude_km
    gap = ((east - width / 2 / longitude_km) - (lon + width / 2 / longitude_km)) * longitude_km
    if gap <= 0 or east + width / 2 / longitude_km >= 180:
        raise ValueError("the eastward control needs two disjoint squares within the local domain")
    return dict(id=OFFER, center=[lat, east], width_km=width), gap


def prepare(base, report):
    if (report / "source-lock.json").exists():
        raise FileExistsError("disjoint offer source is already locked")
    main = whole_iq.read(trial.REPORT / "prediction-lock.json")
    source = whole_iq.checked(trial.REPORT / "source-lock.json", main["files"]["source-lock.json"])
    original = whole_iq.read(source)
    base.mkdir(parents=True, exist_ok=False)
    receiver = cavity_runtime.install(base / "receiver", profile="phase-release")
    cases = {ident: original["cases"][ident] for ident in trial.ANCHORS}
    offers = {}
    for ident, spec in cases.items():
        shifted, gap = east_offer(spec["tile"])
        offers[ident] = dict(original=spec["tile"], shifted=shifted, separation_km=gap)
    lock = dict(
        original_source_sha256=_sha(source),
        original_prediction_lock_sha256=_sha(trial.REPORT / "prediction-lock.json"),
        protocol_sha256=_sha(report / "PROTOCOL.md"),
        sources=original["sources"]
        | {str(Path(__file__).relative_to(trial.ROOT)): _sha(Path(__file__))},
        cases=cases,
        offers=offers,
        assignment=[
            dict(id=ident, offer=OFFER, cpu=cpu)
            for ident, cpu in zip(trial.ANCHORS, (16, 17), strict=True)
        ],
        checkpoints=original["checkpoints"],
        caps_s=original["caps_s"],
        memory_bytes=original["memory_bytes"],
        swap_max_bytes=original["swap_max_bytes"],
        receiver_files=whole_iq.receiver_identity(receiver),
    )
    save_json(report / "source-lock.json", lock)
    (base / "source-lock.sha256").write_text(_sha(report / "source-lock.json"))


def measure(base, report):
    plan = trial.verified_plan(base, report)
    if any(
        east_offer(row["original"]) != (row["shifted"], row["separation_km"])
        for row in plan["offers"].values()
    ):
        raise ValueError("the offered squares differ from the frozen geometry")

    def shift(tile):
        return east_offer(tile)[0]

    with patch.object(trial, "omitted", shift):
        trial.execute(base, report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run"))
    parser.add_argument("base", type=local_output)
    parser.add_argument("--report", type=local_output, default=REPORT)
    args = parser.parse_args()
    (prepare if args.action == "prepare" else measure)(args.base, args.report)
