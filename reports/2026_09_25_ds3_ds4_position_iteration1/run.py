#!/usr/bin/env python3
"""Truth-blind aggregation of sealed per-scan TLE position estimates on DS3/DS4."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DS3 = ROOT / "reports/2026_09_24_ds3_all_captures/manifest.json"
DS4 = ROOT / "reports/2026_09_25_ds4_post_ds3_captures/evaluation-units.json"
SOURCE = Path("/srv/bulk/leo/scanner-adaptive-tle-position-v2")
REFERENCE = (37.84903264307456, -122.4856541910174)
METHODS = (
    "equal_spherical_mean",
    "inverse_rf_rms2_mean",
    "rf_trimmed_mean",
    "spatial_trimmed_mean",
    "geometric_median",
    "huber_center",
)


def canonical(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def compact(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def verify_seal(path: Path) -> None:
    actual = digest(path).removeprefix("sha256:")
    if not any(
        item.is_file() and item.read_text().strip().split()[0].removeprefix("sha256:") == actual
        for item in (path.with_suffix(path.suffix + ".sha256"), path.with_suffix(".sha256"))
    ):
        raise ValueError(f"unsealed input: {path}")


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(path)
    return value


def write_sealed(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = canonical(value)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        handle.write(text)
        pending = Path(handle.name)
    pending.replace(path)
    path.with_suffix(path.suffix + ".sha256").write_text(
        hashlib.sha256(text.encode()).hexdigest() + "\n"
    )


def source_document(session_id: str) -> tuple[dict[str, Any], dict[str, str]]:
    manifest_path = SOURCE / session_id / "manifest.json"
    document_path = SOURCE / session_id / "document.json"
    envelope = load(manifest_path)
    outer = envelope.get("document")
    if not isinstance(outer, dict) or envelope.get("sha256") != "sha256:" + hashlib.sha256(
        compact(outer)
    ).hexdigest():
        raise ValueError(f"invalid source manifest seal: {session_id}")
    document = outer.get("document")
    if not isinstance(document, dict) or document != load(document_path):
        raise ValueError(f"source document/manifest mismatch: {session_id}")
    return document, {
        "manifest_path": str(manifest_path),
        "manifest_file_sha256": digest(manifest_path),
        "document_file_sha256": digest(document_path),
        "storage_document_sha256": str(envelope["sha256"]),
    }


def memberships() -> dict[str, dict[str, Any]]:
    verify_seal(DS3)
    verify_seal(DS4)
    ds3 = load(DS3)
    ds4 = load(DS4)
    ds3_ids = [
        str(row["session_id"])
        for row in ds3["captures"]
        if row.get("admission_status") == "included"
    ]
    ds4_ids = list(map(str, ds4["full_dataset"]["session_ids"]))
    if len(ds3_ids) != 56 or len(ds4_ids) != 91 or set(ds3_ids) & set(ds4_ids):
        raise ValueError("DS3/DS4 membership contract failed")
    return {
        "DS3": {
            "sessions": ds3_ids,
            "groups8": [ds3_ids[index : index + 8] for index in range(0, 56, 8)],
            "source": {"path": str(DS3), "sha256": digest(DS3)},
        },
        "DS4": {
            "sessions": ds4_ids,
            "groups8": [row["session_ids"] for row in ds4["groups_of_8"]],
            "remainder": ds4["groups_of_8_remainder"]["session_ids"],
            "source": {"path": str(DS4), "sha256": digest(DS4)},
        },
    }


def extract(output: Path) -> dict[str, Any]:
    datasets = memberships()
    rows: dict[str, Any] = {}
    configuration = None
    for dataset in datasets.values():
        for session_id in dataset["sessions"]:
            document, binding = source_document(session_id)
            if document.get("analysis_id") != "scanner-adaptive-tle-position-v2":
                raise ValueError(f"wrong analysis: {session_id}")
            diagnostics = document.get("diagnostics", {})
            config = diagnostics.get("configuration", {})
            if config.get("known_position_used_for_inference") is not False:
                raise ValueError(f"reference-bearing source: {session_id}")
            if configuration is None:
                configuration = document["configuration_sha256"]
            if document.get("configuration_sha256") != configuration:
                raise ValueError("mixed source configurations")
            priors = {str(row["name"]): row for row in document.get("priors", [])}
            if "sacramento" not in priors:
                raise ValueError(f"Sacramento prior absent: {session_id}")
            selected = priors["sacramento"]["selected"]
            rows[session_id] = {
                "session_id": session_id,
                "latitude_deg": float(selected["latitude_deg"]),
                "longitude_deg": float(selected["longitude_deg"]),
                "rf_rms_hz": float(selected["capped_weighted_rmse_hz"]),
                "matched_track_count": int(selected["matched_track_count"]),
                "qualifying_observation_count": int(selected["qualifying_observation_count"]),
                "search_spacing_km": float(selected["spacing_km"]),
                "source": binding,
            }
    value = {
        "schema": "ds3-ds4-position-iteration1-inputs/v1",
        "complete": True,
        "runner": {"path": str(Path(__file__)), "sha256": digest(Path(__file__))},
        "reference_coordinate_present": False,
        "known_position_used_for_inference": False,
        "source_method": "scanner-adaptive-tle-position-v2/Sacramento-selected",
        "source_configuration_sha256": configuration,
        "dataset_memberships": datasets,
        "sessions": rows,
    }
    write_sealed(output, value)
    return value


def unit_vectors(points: np.ndarray) -> np.ndarray:
    lat = np.deg2rad(points[:, 0])
    lon = np.deg2rad(points[:, 1])
    return np.column_stack((np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)))


def from_vector(vector: np.ndarray) -> tuple[float, float]:
    value = vector / np.linalg.norm(vector)
    return float(np.rad2deg(np.arcsin(value[2]))), float(np.rad2deg(np.arctan2(value[1], value[0])))


def spherical_mean(points: np.ndarray, weights: np.ndarray | None = None) -> tuple[float, float]:
    vectors = unit_vectors(points)
    return from_vector(np.average(vectors, axis=0, weights=weights))


def local_xy(points: np.ndarray) -> tuple[np.ndarray, tuple[float, float]]:
    origin = spherical_mean(points)
    lat0, lon0 = map(math.radians, origin)
    xy = np.column_stack(
        (
            np.deg2rad(points[:, 1] - math.degrees(lon0)) * 6371.0088 * math.cos(lat0),
            np.deg2rad(points[:, 0] - math.degrees(lat0)) * 6371.0088,
        )
    )
    return xy, origin


def from_xy(value: np.ndarray, origin: tuple[float, float]) -> tuple[float, float]:
    lat0 = math.radians(origin[0])
    return (
        origin[0] + math.degrees(float(value[1]) / 6371.0088),
        origin[1] + math.degrees(float(value[0]) / (6371.0088 * math.cos(lat0))),
    )


def geometric_median(
    points: np.ndarray, base_weights: np.ndarray | None = None
) -> tuple[float, float]:
    xy, origin = local_xy(points)
    base = np.ones(len(xy)) if base_weights is None else np.asarray(base_weights, float)
    estimate = np.average(xy, axis=0, weights=base)
    for _ in range(200):
        distance = np.linalg.norm(xy - estimate, axis=1)
        if float(np.min(distance)) < 1e-10:
            estimate = xy[int(np.argmin(distance))]
            break
        weights = base / np.maximum(distance, 1e-10)
        updated = np.average(xy, axis=0, weights=weights)
        if float(np.linalg.norm(updated - estimate)) < 1e-9:
            estimate = updated
            break
        estimate = updated
    return from_xy(estimate, origin)


def huber_center(points: np.ndarray) -> tuple[float, float]:
    xy, origin = local_xy(points)
    estimate = np.mean(xy, axis=0)
    for _ in range(100):
        distance = np.linalg.norm(xy - estimate, axis=1)
        scale = max(float(np.median(distance)), 1e-6)
        cutoff = 1.5 * scale
        weights = np.minimum(1.0, cutoff / np.maximum(distance, 1e-12))
        updated = np.average(xy, axis=0, weights=weights)
        if float(np.linalg.norm(updated - estimate)) < 1e-9:
            estimate = updated
            break
        estimate = updated
    return from_xy(estimate, origin)


def estimate(method: str, rows: list[dict[str, Any]]) -> tuple[float, float]:
    points = np.asarray([[row["latitude_deg"], row["longitude_deg"]] for row in rows], float)
    rf = np.asarray([row["rf_rms_hz"] for row in rows], float)
    if method == "equal_spherical_mean":
        return spherical_mean(points)
    if method == "inverse_rf_rms2_mean":
        return spherical_mean(points, 1.0 / np.maximum(rf, 1.0) ** 2)
    if method == "rf_trimmed_mean":
        keep = np.argsort(rf)[: max(1, math.ceil(0.75 * len(rows)))]
        return spherical_mean(points[keep])
    if method == "spatial_trimmed_mean":
        xy, _ = local_xy(points)
        center = geometric_median(points)
        center_xy, _ = local_xy(np.vstack((points, np.asarray(center))))
        distance = np.linalg.norm(center_xy[:-1] - center_xy[-1], axis=1)
        keep = np.argsort(distance)[: max(1, math.ceil(0.75 * len(rows)))]
        return spherical_mean(points[keep])
    if method == "geometric_median":
        return geometric_median(points)
    if method == "huber_center":
        return huber_center(points)
    raise ValueError(method)


def infer(inputs: Path, output: Path) -> dict[str, Any]:
    verify_seal(inputs)
    source = load(inputs)
    if source.get("reference_coordinate_present") is not False:
        raise ValueError("inference input contains reference coordinate")
    sessions = source["sessions"]
    estimates = []
    for dataset_name, dataset in source["dataset_memberships"].items():
        units = [
            *[
                (f"single-{index + 1:03d}", [sid], "single")
                for index, sid in enumerate(dataset["sessions"])
            ],
            *[
                (f"group8-{index + 1:03d}", ids, "group8")
                for index, ids in enumerate(dataset["groups8"])
            ],
            ("full", dataset["sessions"], "full"),
        ]
        for unit_id, ids, scope in units:
            rows = [sessions[sid] for sid in ids]
            for method in METHODS:
                latitude, longitude = estimate(method, rows)
                estimates.append(
                    {
                        "dataset": dataset_name,
                        "scope": scope,
                        "unit_id": unit_id,
                        "session_count": len(ids),
                        "session_ids": ids,
                        "method": method,
                        "latitude_deg": latitude,
                        "longitude_deg": longitude,
                    }
                )
    value = {
        "schema": "ds3-ds4-position-iteration1-inference/v1",
        "complete": True,
        "runner": {"path": str(Path(__file__)), "sha256": digest(Path(__file__))},
        "reference_coordinate_present": False,
        "known_position_used_for_inference": False,
        "source": {"path": str(inputs), "sha256": digest(inputs)},
        "methods": list(METHODS),
        "method_contract": {
            "prior": "fixed Sacramento 250 km source result",
            "session_weight": "one vote per complete scan unless method explicitly uses RF RMS",
            "rf_trim_fraction": 0.25,
            "spatial_trim_fraction": 0.25,
            "huber_cutoff": "1.5 times current median spatial distance",
        },
        "estimates": estimates,
    }
    if (
        "reference" in canonical(value).lower()
        and value["reference_coordinate_present"] is not False
    ):
        raise ValueError("reference leaked into inference")
    write_sealed(output, value)
    return value


def haversine_km(point: tuple[float, float], reference: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*point, *reference))
    value = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * 6371.0088 * math.asin(math.sqrt(min(1.0, value)))


def postseal(inference: Path, output: Path, csv_output: Path, png_output: Path) -> dict[str, Any]:
    verify_seal(inference)
    source = load(inference)
    rows = []
    for row in source["estimates"]:
        rows.append(
            {
                **row,
                "horizontal_error_km": haversine_km(
                    (float(row["latitude_deg"]), float(row["longitude_deg"])), REFERENCE
                ),
            }
        )
    summaries = []
    for dataset in ("DS3", "DS4"):
        for method in METHODS:
            for scope in ("single", "group8", "full"):
                values = [
                    row["horizontal_error_km"]
                    for row in rows
                    if row["dataset"] == dataset
                    and row["method"] == method
                    and row["scope"] == scope
                ]
                summaries.append(
                    {
                        "dataset": dataset,
                        "method": method,
                        "scope": scope,
                        "unit_count": len(values),
                        "median_error_km": float(np.median(values)),
                        "minimum_error_km": float(np.min(values)),
                        "maximum_error_km": float(np.max(values)),
                    }
                )
    value = {
        "schema": "ds3-ds4-position-iteration1-postseal/v1",
        "complete": True,
        "runner": {"path": str(Path(__file__)), "sha256": digest(Path(__file__))},
        "reference_used_for_inference": False,
        "reference": {"latitude_deg": REFERENCE[0], "longitude_deg": REFERENCE[1]},
        "inference": {"path": str(inference), "sha256": digest(inference)},
        "summaries": summaries,
        "evaluations": rows,
    }
    write_sealed(output, value)
    with csv_output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)
    csv_output.with_suffix(csv_output.suffix + ".sha256").write_text(
        hashlib.sha256(csv_output.read_bytes()).hexdigest() + "\n"
    )
    render(value, png_output)
    png_output.with_suffix(png_output.suffix + ".sha256").write_text(
        hashlib.sha256(png_output.read_bytes()).hexdigest() + "\n"
    )
    return value


def render(value: dict[str, Any], output: Path) -> None:
    import matplotlib.pyplot as plt

    rows = value["summaries"]
    figure, axes = plt.subplots(1, 2, figsize=(15, 6), constrained_layout=True)
    colors = {"DS3": "#1f77b4", "DS4": "#ff7f0e"}
    labels = [name.replace("_", "\n") for name in METHODS]
    x = np.arange(len(METHODS))
    for dataset, shift in (("DS3", -0.18), ("DS4", 0.18)):
        full = [
            next(
                row["median_error_km"]
                for row in rows
                if row["dataset"] == dataset and row["method"] == method and row["scope"] == "full"
            )
            for method in METHODS
        ]
        axes[0].bar(x + shift, full, width=0.34, label=dataset, color=colors[dataset])
        group = [
            next(
                row["median_error_km"]
                for row in rows
                if row["dataset"] == dataset
                and row["method"] == method
                and row["scope"] == "group8"
            )
            for method in METHODS
        ]
        axes[1].bar(x + shift, group, width=0.34, label=dataset, color=colors[dataset])
    titles = ("Full-dataset position error", "Median eight-scan error")
    for axis, title in zip(axes, titles, strict=True):
        axis.axhline(1.0, color="black", linestyle="--", linewidth=1, label="1 km target")
        axis.set_xticks(x, labels, rotation=0, fontsize=8)
        axis.set_ylabel("Horizontal error (km)")
        axis.set_title(title)
        axis.grid(axis="y", alpha=0.25)
        axis.legend()
    figure.suptitle("DS3 and DS4 truth-blind aggregation of per-scan Sacramento estimates")
    figure.savefig(output, dpi=170)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    extraction = sub.add_parser("extract")
    extraction.add_argument("--output", type=Path, default=HERE / "inputs.json")
    inference = sub.add_parser("infer")
    inference.add_argument("--inputs", type=Path, default=HERE / "inputs.json")
    inference.add_argument("--output", type=Path, default=HERE / "inference.json")
    evaluation = sub.add_parser("postseal")
    evaluation.add_argument("--inference", type=Path, default=HERE / "inference.json")
    evaluation.add_argument("--output", type=Path, default=HERE / "postseal.json")
    evaluation.add_argument("--csv", type=Path, default=HERE / "summary.csv")
    evaluation.add_argument("--png", type=Path, default=HERE / "comparison.png")
    args = parser.parse_args()
    if args.command == "extract":
        value = extract(args.output)
    elif args.command == "infer":
        value = infer(args.inputs, args.output)
    else:
        value = postseal(args.inference, args.output, args.csv, args.png)
    print(canonical({"schema": value["schema"], "complete": value["complete"]}), end="")


if __name__ == "__main__":
    main()
