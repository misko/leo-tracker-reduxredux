"""Freeze measured predictions and rescore them with the permanent benchmark."""

import argparse
import csv
import gzip
import hashlib
import io
import json
from collections import defaultdict
from pathlib import Path

from tools.pipeline_eval.__main__ import VARIANTS, encoded, read_predictions, references, write
from tools.pipeline_eval.scoring import baseline_rows, distribution, score

HERE = Path(__file__).resolve().parent
TRANSFER = ("orbit_interp", "shape_score", "track_reduce", "projected_fit")
PANELS = {
    "roof16": tuple(VARIANTS),
    "transfer124": TRANSFER,
    "ds26-common127": ("orbit_interp", "projected_fit"),
}


def csv_file(path, rows):
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    write(path, buf.getvalue().encode())


def compact_record(record):
    # Keep every candidate output, control measurement and individual case. Large
    # waveform arrays and per-window traces are available from the execution directory.
    return {k: v for k, v in record.items() if k != "artifacts"}


def calibration(refs, panel):
    rows = []
    groups = defaultdict(list)
    for item in refs:
        if item["condition"] == "present" and "baseline" in item["reference"]:
            groups[item["group"]].append(item)
    for group, members in groups.items():
        for role in ("baseline", "selective-gap", "omitted-track-one", "omitted-tracks"):
            pairs = [item["reference"][role] for item in members]
            pairs = [
                r for r in pairs if all(r[a]["error_km"] is not None for a in ("c0", "fitted_c"))
            ]
            errors = [r["fitted_c"]["error_km"] - r["c0"]["error_km"] for r in pairs]
            rms = [
                r["fitted_c"]["matched_rf_rms_hz"] - r["c0"]["matched_rf_rms_hz"]
                for r in pairs
                if r["c0"].get("matched_rf_rms_hz") is not None
            ]
            rows.append(
                dict(
                    panel=panel,
                    dataset=group,
                    method=role,
                    paired=len(pairs),
                    position_improved=sum(x < -1e-9 for x in errors),
                    gps_delta_median_km=distribution(errors)["p50"],
                    matched_rf_cases=len(rms),
                    rf_improved=sum(x < 0 for x in rms),
                    matched_rf_delta_median_hz=distribution(rms)["p50"],
                )
            )
    return rows


def compile_report(root, corrected, replay):
    all_rows, groups, cal, controls = [], [], [], []
    book = dict(schema_version=1, panels={}, prediction_sha256={})
    for panel, methods in PANELS.items():
        _, refs = references(panel, None)
        cal.extend(calibration(refs, panel))
        for row in baseline_rows(refs):
            errors = row["error_km"]
            controls.append(
                dict(
                    panel=panel,
                    dataset=row["group"],
                    condition=row["condition"],
                    method=row["method"],
                    arm=row["arm"],
                    attempts=row["attempts"],
                    fixes=errors["n"],
                    within_5_km=row["within_km"]["5"],
                    median_km=errors["p50"],
                    p95_km=errors["p95"],
                    worst_km=errors["max"],
                )
            )
        book["panels"][panel] = {}
        for method in methods:
            stored = HERE / "predictions" / panel / f"{method}.jsonl.gz"
            if replay:
                records = read_predictions(stored)
            else:
                base = corrected if panel == "roof16" and method == "iq_position" else root
                directory = base / panel / method
                path = directory / "current" / "predictions.jsonl"
                if not path.is_file():
                    path = directory / "predictions.jsonl"
                records = read_predictions(path)
                raw = b"".join(encoded(compact_record(records[r["id"]])) + b"\n" for r in refs)
                write(stored, gzip.compress(raw, mtime=0))
            if set(records) != {r["id"] for r in refs}:
                raise ValueError(f"incomplete recorded panel for {panel}/{method}")
            book["prediction_sha256"][str(stored.relative_to(HERE))] = hashlib.sha256(
                stored.read_bytes()
            ).hexdigest()
            result, rows = score(refs, records)
            book["panels"][panel][method] = result
            all_rows.extend(dict(panel=panel, method=method, **r) for r in rows)
            for g in result["groups"]:
                groups.append(
                    dict(
                        panel=panel,
                        method=method,
                        dataset=g["group"],
                        condition=g["condition"],
                        arm=g["arm"],
                        attempts=g["attempts"],
                        coordinates=g["error_km"]["n"],
                        within_5_km=g["within_km"]["5"],
                        median_km=g["error_km"]["p50"],
                        p90_km=g["error_km"]["p90"],
                        p95_km=g["error_km"]["p95"],
                        worst_km=g["error_km"]["max"],
                        v5_median_km=g["v5_error_km"]["p50"],
                        v5_p95_km=g["v5_error_km"]["p95"],
                        lost_v5_fixes=g["lost_v5_fixes"],
                        max_v5_coordinate_delta_km=g["v5_coordinate_delta_km"]["max"],
                        false_publications=g["false_publications"],
                        keeps_v5=g["keeps_v5_panel"],
                        decisions=json.dumps(g["decision_counts"], sort_keys=True),
                    )
                )
    csv_file(HERE / "errors.csv", all_rows)
    csv_file(HERE / "distributions.csv", groups)
    csv_file(HERE / "calibration.csv", cal)
    csv_file(HERE / "original-distributions.csv", controls)
    full = HERE / "evidence" / "full-iq"
    _, smoke = references("smoke", None)
    complete_recordings = {}
    for case in smoke:
        complete_recordings.update(read_predictions(full / case["id"] / "prediction.jsonl"))
    if set(complete_recordings) != {case["id"] for case in smoke}:
        raise ValueError("complete-recording evidence differs from the smoke roster")
    _, full_rows = score(smoke, complete_recordings)
    csv_file(full / "scorer-errors.csv", full_rows)
    write(
        HERE / "results.json",
        json.dumps(book, indent=2, sort_keys=True, allow_nan=False).encode() + b"\n",
    )
    print(f"Scored {len(all_rows)} recording, variant, and calibration rows.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path)
    parser.add_argument("--corrected-iq", type=Path)
    args = parser.parse_args()
    if bool(args.runs) != bool(args.corrected_iq):
        parser.error("supply both --runs and --corrected-iq to freeze a new measured run")
    compile_report(args.runs, args.corrected_iq, args.runs is None)
