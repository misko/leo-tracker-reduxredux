#!/usr/bin/env python3
"""Build the final DS1/DS2 comparison artifact from sealed report outputs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text())


def digest(path: str) -> str:
    return "sha256:" + hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def row(rows: list[dict], method: str) -> dict:
    return next(item for item in rows if item["method"] == method)


def main() -> None:
    portable_path = "reports/2026_09_24_ds2_portable_evaluation/evaluation.json"
    closure_path = "reports/2026_09_24_ds2_consistent_rate_screen/postseal-evaluation.json"
    missing_path = "reports/2026_09_24_ds2_missing_models/evaluation.json"
    geometry_path = (
        "reports/2026_09_24_ds2_geometry_cone_evaluation/blind-postseal-evaluation.json"
    )
    quality_path = "reports/2026_09_24_ds2_quality/summary.json"
    ds1_path = "reports/2026_09_24_ds1_iteration12_comparison/summary.json"
    portable = load(portable_path)
    closure = load(closure_path)
    missing = load(missing_path)
    geometry = load(geometry_path)
    quality = load(quality_path)
    ds1 = load(ds1_path)

    fine = {item["method"]: item for item in portable["joint_rows"]}
    closure_rows = {item["method"]: item for item in closure["rows"]}
    missing_rows = {item["method"]: item for item in missing["rows"]}
    geometry_joint = next(
        item
        for item in geometry["results"]
        if item["label"] == "joint-three-geometry-captures"
        and item["method"]
        == "blind re-associated local fitted cone, 50° full FOV"
    )
    ds1_error = min(
        item["postseal_error_km"]
        for item in ds1["results"]
        if item["postseal_error_km"] is not None
    )

    methods = [
        ("DS1 expanded exact", ds1_error, "development"),
        ("DS2 baseline", fine["baseline"]["postseal_error_km"], "portable"),
        (
            "DS2 causal rate",
            fine["equal-weight-joint-rate"]["postseal_error_km"],
            "portable",
        ),
        (
            "DS2 consistent cap-800",
            closure_rows["consistent cap-800 proposal/exact"]["postseal_error_km"],
            "bounded local",
        ),
        (
            "DS2 rate-aware screen",
            closure_rows["rate-aware cache screen"]["postseal_error_km"],
            "bounded local",
        ),
        (
            "DS2 session scale",
            missing_rows["common-plus-session-scale"]["postseal_error_km"],
            "unqualified",
        ),
        (
            "DS2 robust residual",
            missing_rows["residual-ar1-student-t"]["postseal_error_km"],
            "diagnostic",
        ),
        ("DS2 blind LT3D cone", geometry_joint["horizontal_error_km"], "3 captures"),
    ]
    output = {
        "schema": "ds1-ds2-final-comparison/v1",
        "development_evaluation": True,
        "reference_coordinate": portable["reference_coordinate"],
        "sources": {
            path: digest(path)
            for path in (
                portable_path,
                closure_path,
                missing_path,
                geometry_path,
                quality_path,
                ds1_path,
            )
        },
        "headline": {
            "ds1_best_error_km": ds1_error,
            "ds2_best_error_km": closure_rows["consistent cap-800 proposal/exact"][
                "postseal_error_km"
            ],
            "ds2_best_method": "consistent cap-800 proposal/exact",
            "ds2_sessions": quality["corpus"]["sessions"],
            "ds2_tracklets": quality["corpus"]["tracklets"],
            "ds2_tracklet_observations": quality["corpus"]["tracklet_observations"],
            "ds2_reviewed_randomized_rms_median_hz": quality["quality"][
                "rank1_randomized_evaluation_rms_hz"
            ]["median"],
        },
        "comparison_rows": [
            {"method": name, "postseal_error_km": value, "scope": scope}
            for name, value, scope in methods
        ],
    }
    content = json.dumps(output, indent=2, sort_keys=True) + "\n"
    (HERE / "summary.json").write_text(content)
    (HERE / "summary.json.sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )

    labels = [name.replace("DS2 ", "") for name, _, _ in methods]
    values = [value for _, value, _ in methods]
    scopes = [scope for _, _, scope in methods]
    palette = {
        "development": "#7f8c8d",
        "portable": "#2f83a7",
        "bounded local": "#2a9d8f",
        "unqualified": "#e9c46a",
        "diagnostic": "#f4a261",
        "3 captures": "#8e6bbd",
    }
    fig, ax = plt.subplots(figsize=(13, 6.5), constrained_layout=True)
    bars = ax.barh(
        list(reversed(labels)),
        list(reversed(values)),
        color=[palette[item] for item in reversed(scopes)],
    )
    ax.axvline(1.0, color="#d62728", linestyle="--", linewidth=1.5, label="1 km")
    ax.set_xlabel("Post-seal horizontal position error (km)")
    ax.set_title("DS1 and DS2 positioning results on reused development evidence")
    ax.grid(axis="x", alpha=0.25)
    for bar, value in zip(bars, reversed(values), strict=True):
        ax.text(value + 0.04, bar.get_y() + bar.get_height() / 2, f"{value:.3f}", va="center")
    ax.legend(loc="lower right")
    fig.savefig(HERE / "ds1-ds2-final-comparison.png", dpi=180)


if __name__ == "__main__":
    main()
