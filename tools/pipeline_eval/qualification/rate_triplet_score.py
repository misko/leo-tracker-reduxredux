"""Score sealed rate-triplet positions using a separate frozen truth port."""

import argparse
import gzip
import json
from pathlib import Path

from ..__main__ import local_output, references, save_json
from ..scoring import ARMS, distance_km, distribution, validate_result
from .prefix_figures import csv_file
from .rate_triplet_trials import MODES, OUTPUT, ROSTER


def evaluation_refs():
    return {
        row["id"]: row
        for panel, family in (("ds26-common127", "DS26"), ("roof16", "DS29"))
        for row in references(panel, [i for i in ROSTER if i.startswith(family)])[1]
    }


def calibration_delta(rows, field):
    points = {(r["id"], r["arm"]): r[field] for r in rows}
    return distribution(
        fitted - zero
        for case in ROSTER
        for zero, fitted in [(points[case, "c0"], points[case, "fitted_c"])]
        if zero is not None and fitted is not None
    )


def score(directory):
    raw = {}
    for mode in MODES:
        with gzip.open(directory / f"{mode}.jsonl.gz", "rt") as source:
            raw[mode] = list(map(json.loads, source))
    if any([r["id"] for r in rows] != list(ROSTER) for rows in raw.values()):
        raise ValueError("predictions do not cover the six predeclared recordings")
    if len({r["implementation_sha256"] for rows in raw.values() for r in rows}) != 1:
        raise ValueError("prediction workers did not use the same implementation")
    for first, second in zip(*raw.values(), strict=True):
        for key in ("native_sha256", "catalog_sha256"):
            if first[key] != second[key]:
                raise ValueError("global and matched-tile inputs differ")

    refs = evaluation_refs()
    summary = {}
    position, frequency = [], []
    for mode in MODES:
        pos, rms = [], []
        for r in raw[mode]:
            if r["mode"] != mode:
                raise ValueError("invalid search-mode binding")
            case = r["id"]
            result = r["result"]
            validate_result(result)
            truth = refs[case]["truth"]
            for arm in ARMS:
                a = result["arms"][arm]
                pos.append(
                    dict(
                        id=case,
                        mode=mode,
                        arm=arm,
                        status=result["status"],
                        returned_km=distance_km(a["latlon"], truth),
                        forced_km=distance_km(a["forced_latlon"], truth),
                        original_v5_km=(
                            refs[case]["reference"]["baseline"][arm]["error_km"]
                            if mode == "matched-tile"
                            else None
                        ),
                        worker_wall_s=r["worker_wall_s"],
                    )
                )
                rms.append(
                    dict(
                        id=case,
                        mode=mode,
                        arm=arm,
                        conditional_rms_hz=a.get("conditional_rms_hz"),
                        fit_score=a.get("fit_score"),
                        fitted_c_hz_per_ghz=a.get("fitted_c_hz_per_ghz"),
                    )
                )
        position.extend(pos)
        frequency.extend(rms)
        summary[mode] = {
            "attempts": len(ROSTER),
            "paired_fitted_minus_zero_forced_km": calibration_delta(pos, "forced_km"),
            "paired_fitted_minus_zero_rms_hz": calibration_delta(rms, "conditional_rms_hz"),
            "worker_wall_s": distribution(r["worker_wall_s"] for r in raw[mode]),
        }
        for arm in ARMS:
            p = [r for r in pos if r["arm"] == arm]
            returned = [r["returned_km"] for r in p]
            summary[mode][arm] = dict(
                returned_km=distribution(returned),
                forced_km=distribution(r["forced_km"] for r in p),
                within_5_km=sum(v is not None and v <= 5 for v in returned),
                original_v5_km=distribution(r["original_v5_km"] for r in p),
                conditional_rms_hz=distribution(
                    r["conditional_rms_hz"] for r in rms if r["arm"] == arm
                ),
            )
    csv_file(directory / "position-errors.csv", position)
    csv_file(directory / "conditional-frequency-rms.csv", frequency)
    save_json(directory / "summary.json", summary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=OUTPUT)
    score(local_output(parser.parse_args().directory))
