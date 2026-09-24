#!/usr/bin/env python3
"""Post-seal evaluation/export for the bounded per-track fractional diagnostic."""

import csv
import hashlib
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt

HERE = Path(__file__).parent
REFERENCE = (37.84903264307456, -122.4856541910174)
CASES = (
    "train_20260921_00_16",
    "train_20260921_16_16",
    "validation_20260922_08_16",
    "validation_20260921_08_16",
)


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def haversine(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    q = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 6371.0088 * 2 * math.asin(math.sqrt(q))


def main():
    rows, bindings = [], {}
    for case in CASES:
        path = HERE / f"fractional_per_track_{case}.json"
        seal = path.with_suffix(".sha256")
        if (
            not path.exists()
            or not seal.exists()
            or seal.read_text().strip() != digest(path).split(":", 1)[1]
        ):
            raise ValueError(f"unsealed fractional diagnostic: {case}")
        bindings[case] = digest(path)
        payload = json.loads(path.read_text())
        if payload["held_used_for_fit"] or payload["truth_used_for_fit"]:
            raise ValueError("fractional fit used evaluation evidence")
        for row in payload["rows"]:
            value = dict(row)
            value["reference_error_km"] = haversine(
                (value["latitude_deg"], value["longitude_deg"]), REFERENCE
            )
            value["training_capped_rms_hz"] = 800 * math.sqrt(value["training_capped_loss"])
            value["held_capped_rms_hz"] = 800 * math.sqrt(value["held_capped_loss"])
            values = [x for x in value["per_track_tau_s"] if x is not None]
            value["fractional_track_count"] = len(values)
            value["fractional_tau_min_s"] = min(values) if values else None
            value["fractional_tau_max_s"] = max(values) if values else None
            value["fractional_tau_boundary_track_count"] = sum(
                abs(abs(x) - 5.0) <= 1e-10 for x in values
            )
            value["fractional_tau_boundary_track_fraction"] = (
                value["fractional_tau_boundary_track_count"] / len(values) if values else None
            )
            rows.append(value)
    if len(rows) != 16 or {x["case_id"] for x in rows} != set(CASES):
        raise ValueError("four-group fractional coverage incomplete")
    output = {
        "schema": "ds1-historical-fractional-per-track-evaluation/v1",
        "rows": rows,
        "reference_role": "post-seal evaluation only",
        "held_used_for_fit": False,
        "truth_used_for_fit": False,
        "bindings": bindings,
    }
    path = HERE / "fractional_per_track_evaluation.json"
    path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    path.with_suffix(".sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest() + "\n")
    columns = [
        "case_id",
        "partition",
        "group_id",
        "scan_count",
        "prior",
        "geographic_point_role",
        "training_capped_rms_hz",
        "held_capped_rms_hz",
        "reference_error_km",
        "fractional_track_count",
        "fractional_tau_min_s",
        "fractional_tau_max_s",
        "fractional_tau_boundary_track_count",
        "fractional_tau_boundary_track_fraction",
    ]
    with (HERE / "fractional_per_track_rows.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows([{key: row[key] for key in columns} for row in rows])
    # The inherited shared terminal point is the TRAIN-selected point in the
    # original DS1 trace; the baseline terminal point is a paired sensitivity.
    plot_rows = [x for x in rows if x["geographic_point_role"] == "shared"]
    fig, ax = plt.subplots(figsize=(8, 4), layout="constrained")
    for prior, marker in (("sacramento", "o"), ("reno", "s")):
        values = [x for x in plot_rows if x["prior"] == prior]
        ax.plot(
            [x["case_id"].replace("_202609", "\n202609") for x in values],
            [x["reference_error_km"] for x in values],
            marker=marker,
            label=prior,
        )
    ax.set_ylabel("post-seal reference error (km)")
    ax.set_title("Independent fractional per-track tau diagnostic, 16 scans")
    ax.legend()
    fig.savefig(HERE / "fractional_per_track_position_error.png", dpi=160)
    print(
        json.dumps(
            {
                "rows": len(rows),
                "shared_terminal_mean_error_km": sum(x["reference_error_km"] for x in plot_rows)
                / len(plot_rows),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
