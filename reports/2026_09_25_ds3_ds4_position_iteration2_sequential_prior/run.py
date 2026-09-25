#!/usr/bin/env python3
"""Fit a DS3-only position prior and causally update it with DS4 scans."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
INPUT = ROOT / "reports/2026_09_25_ds3_ds4_position_iteration1/inputs.json"
REFERENCE = (37.84903264307456, -122.4856541910174)
KEEP_FRACTION = 0.75


def canonical(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def verify_seal(path: Path) -> None:
    expected = path.with_suffix(path.suffix + ".sha256").read_text().strip()
    if expected.removeprefix("sha256:") != digest(path).removeprefix("sha256:"):
        raise ValueError(f"invalid seal: {path}")


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(path)
    return value


def write_sealed(path: Path, value: dict[str, Any]) -> None:
    text = canonical(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        handle.write(text)
        pending = Path(handle.name)
    pending.replace(path)
    path.with_suffix(path.suffix + ".sha256").write_text(
        hashlib.sha256(text.encode()).hexdigest() + "\n"
    )


def vector(row: dict[str, Any]) -> np.ndarray:
    latitude = math.radians(float(row["latitude_deg"]))
    longitude = math.radians(float(row["longitude_deg"]))
    return np.asarray(
        (
            math.cos(latitude) * math.cos(longitude),
            math.cos(latitude) * math.sin(longitude),
            math.sin(latitude),
        )
    )


def coordinate(vector_sum: np.ndarray) -> tuple[float, float]:
    value = vector_sum / np.linalg.norm(vector_sum)
    return (
        math.degrees(math.asin(float(value[2]))),
        math.degrees(math.atan2(float(value[1]), float(value[0]))),
    )


def estimate_record(
    name: str,
    vector_sum: np.ndarray,
    session_ids: list[str],
    *,
    new_session_ids: list[str],
) -> dict[str, Any]:
    latitude, longitude = coordinate(vector_sum)
    return {
        "estimate_id": name,
        "latitude_deg": latitude,
        "longitude_deg": longitude,
        "effective_session_count": len(session_ids),
        "session_ids": session_ids,
        "new_session_ids": new_session_ids,
    }


def infer(input_path: Path, output: Path) -> dict[str, Any]:
    verify_seal(input_path)
    source = load(input_path)
    if source.get("reference_coordinate_present") is not False:
        raise ValueError("reference-bearing inference input")
    memberships = source["dataset_memberships"]
    sessions = source["sessions"]
    ds3_ids = list(map(str, memberships["DS3"]["sessions"]))
    ds4_ids = list(map(str, memberships["DS4"]["sessions"]))
    if len(ds3_ids) != 56 or len(ds4_ids) != 91:
        raise ValueError("unexpected dataset membership")

    retained_count = math.ceil(KEEP_FRACTION * len(ds3_ids))
    retained_ids = sorted(ds3_ids, key=lambda sid: float(sessions[sid]["rf_rms_hz"]))[
        :retained_count
    ]
    prior_sum = np.sum([vector(sessions[sid]) for sid in retained_ids], axis=0)
    estimates = [
        estimate_record(
            "ds3_rf_trimmed_prior",
            prior_sum,
            retained_ids,
            new_session_ids=retained_ids,
        )
    ]

    cumulative_sum = prior_sum.copy()
    cumulative_ids = list(retained_ids)
    covered_by_groups: list[str] = []
    for index, group in enumerate(memberships["DS4"]["groups8"], start=1):
        group_ids = list(map(str, group))
        group_sum = np.sum([vector(sessions[sid]) for sid in group_ids], axis=0)
        estimates.append(
            estimate_record(
                f"ds4_group8_{index:02d}_with_frozen_ds3_prior",
                prior_sum + group_sum,
                retained_ids + group_ids,
                new_session_ids=group_ids,
            )
        )
        cumulative_sum += group_sum
        cumulative_ids.extend(group_ids)
        covered_by_groups.extend(group_ids)
        estimates.append(
            estimate_record(
                f"ds4_cumulative_checkpoint_{index:02d}",
                cumulative_sum,
                list(cumulative_ids),
                new_session_ids=group_ids,
            )
        )

    if covered_by_groups != ds4_ids[:88]:
        raise ValueError("group-of-eight chronology changed")
    full_sum = prior_sum + np.sum([vector(sessions[sid]) for sid in ds4_ids], axis=0)
    estimates.append(
        estimate_record(
            "ds4_all91_with_frozen_ds3_prior",
            full_sum,
            retained_ids + ds4_ids,
            new_session_ids=ds4_ids,
        )
    )
    value = {
        "schema": "ds3-ds4-sequential-position-inference/v1",
        "complete": True,
        "reference_coordinate_present": False,
        "known_position_used_for_inference": False,
        "truth_accessed": False,
        "runner": {"path": str(Path(__file__).resolve()), "sha256": digest(Path(__file__))},
        "input": {"path": str(input_path), "sha256": digest(input_path)},
        "method": {
            "prior_training_dataset": "DS3",
            "prior_selection": "lowest RF-RMS 75 percent, fixed from iteration 1",
            "retained_scan_count": retained_count,
            "update": "sum unit-sphere vectors with one vote per retained/new scan",
            "chronology": "DS3 prior frozen before all DS4 updates",
            "timing_fit": "none; consumes independent per-scan truth-blind position estimates",
        },
        "estimates": estimates,
    }
    write_sealed(output, value)
    return value


def haversine_km(point: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*point, *REFERENCE))
    value = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * 6371.0088 * math.asin(math.sqrt(min(1.0, value)))


def postseal(inference_path: Path, output: Path, png: Path) -> dict[str, Any]:
    verify_seal(inference_path)
    inference = load(inference_path)
    evaluated = []
    for row in inference["estimates"]:
        evaluated.append(
            {
                **row,
                "horizontal_error_km": haversine_km(
                    (float(row["latitude_deg"]), float(row["longitude_deg"]))
                ),
            }
        )
    frozen = [row["horizontal_error_km"] for row in evaluated if "group8" in row["estimate_id"]]
    cumulative = [
        row["horizontal_error_km"]
        for row in evaluated
        if "cumulative_checkpoint" in row["estimate_id"]
    ]
    summary = {
        "ds3_prior_error_km": evaluated[0]["horizontal_error_km"],
        "ds4_frozen_prior_group8": distribution(frozen),
        "ds4_cumulative_checkpoints": distribution(cumulative),
        "ds4_final_88_error_km": cumulative[-1],
        "ds4_all91_posterior_error_km": next(
            row["horizontal_error_km"]
            for row in evaluated
            if row["estimate_id"] == "ds4_all91_with_frozen_ds3_prior"
        ),
    }
    value = {
        "schema": "ds3-ds4-sequential-position-postseal/v1",
        "complete": True,
        "reference_used_for_inference": False,
        "reference": {"latitude_deg": REFERENCE[0], "longitude_deg": REFERENCE[1]},
        "inference": {"path": str(inference_path), "sha256": digest(inference_path)},
        "summary": summary,
        "evaluations": evaluated,
    }
    write_sealed(output, value)
    render(value, png)
    png.with_suffix(png.suffix + ".sha256").write_text(
        hashlib.sha256(png.read_bytes()).hexdigest() + "\n"
    )
    return value


def distribution(values: list[float]) -> dict[str, Any]:
    array = np.asarray(values, float)
    return {
        "count": len(values),
        "median_error_km": float(np.median(array)),
        "p90_error_km": float(np.percentile(array, 90)),
        "maximum_error_km": float(np.max(array)),
        "sub_km_count": int(np.sum(array < 1.0)),
    }


def render(value: dict[str, Any], output: Path) -> None:
    import matplotlib.pyplot as plt

    rows = value["evaluations"]
    frozen = [row for row in rows if "group8" in row["estimate_id"]]
    cumulative = [row for row in rows if "cumulative_checkpoint" in row["estimate_id"]]
    x = np.arange(1, len(frozen) + 1)
    figure, axis = plt.subplots(figsize=(12, 6), constrained_layout=True)
    axis.plot(
        x,
        [row["horizontal_error_km"] for row in frozen],
        "o-",
        label="Each group8 + frozen DS3 prior",
    )
    axis.plot(
        x,
        [row["horizontal_error_km"] for row in cumulative],
        "o-",
        label="Cumulative DS4 update",
    )
    axis.axhline(1.0, color="black", linestyle="--", linewidth=1, label="1 km target")
    axis.set_xlabel("Chronological DS4 group of eight")
    axis.set_ylabel("Post-seal horizontal error (km)")
    axis.set_title("Causal DS3 prior updated with DS4 scans")
    axis.grid(alpha=0.25)
    axis.legend()
    figure.savefig(output, dpi=170)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inference = commands.add_parser("infer")
    inference.add_argument("--input", type=Path, default=INPUT)
    inference.add_argument("--output", type=Path, default=HERE / "inference.json")
    evaluation = commands.add_parser("postseal")
    evaluation.add_argument("--inference", type=Path, default=HERE / "inference.json")
    evaluation.add_argument("--output", type=Path, default=HERE / "postseal.json")
    evaluation.add_argument("--png", type=Path, default=HERE / "sequential-performance.png")
    args = parser.parse_args()
    result = (
        infer(args.input, args.output)
        if args.command == "infer"
        else postseal(args.inference, args.output, args.png)
    )
    print(canonical({"schema": result["schema"], "complete": result["complete"]}), end="")


if __name__ == "__main__":
    main()
