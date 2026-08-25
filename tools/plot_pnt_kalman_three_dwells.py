#!/usr/bin/env python3
"""Plot sealed GLRT, frame-CFO, and V2/V3 Kalman tracks for matched dwells.

The input replay products are research artifacts, not public contracts.  This
tool validates that the V2 and V3 products describe the same recording path and
that their window/seed time coordinates agree before drawing anything.  Every
line is explicitly broken at window and reacquisition boundaries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

DEFAULT_DWELLS = (
    "D1:1.3:2.8",
    "D2:6.0:8.0",
    "D6:20.1:22.1",
)
IDENTITY_FIELDS = (
    "label",
    "session_id",
    "run_id",
    "scope_sha256",
    "stream_id",
    "radio_id",
    "receiver_id",
    "channel",
    "edge",
    "rf_hz",
    "sample_rate_hz",
    "sample_count",
    "recording_manifest_sha256",
    "analysis_manifest_sha256",
    "pilot_scan_sha256",
)
NPZ_FIELDS = (
    "window_index",
    "window_center_time_s",
    "window_raw_disjoint",
    "bin_index",
    "seed_sample_start",
    "seed_glrt_margin",
    "frame_index",
    "frame_start_sample",
    "absolute_time_s",
    "measurement_supported",
    "absolute_cfo_measurement_hz",
    "tracked_absolute_cfo_hz",
    "reacquired",
)

GLRT_COLOR = "#d48806"
FRAME_COLOR = "#5aa6c8"
V2_COLOR = "#7256a8"
V3_COLOR = "#17824b"
GRID_COLOR = "#dce3e8"


@dataclass(frozen=True, slots=True)
class DwellSpec:
    label: str
    zoom_start_s: float
    zoom_end_s: float


@dataclass(frozen=True, slots=True)
class InputArtifact:
    summary_path: Path
    npz_path: Path
    summary: dict[str, Any]
    arrays: dict[str, np.ndarray]


@dataclass(frozen=True, slots=True)
class DwellData:
    spec: DwellSpec
    v2: InputArtifact
    v3: InputArtifact
    seed_path: Path
    seed_document: dict[str, Any]
    glrt_start_time_s: np.ndarray
    glrt_time_s: np.ndarray
    glrt_cfo_hz: np.ndarray
    duration_s: float


@dataclass(frozen=True, slots=True)
class ZoomReference:
    reference_time_s: float
    intercept_hz: float
    slope_hz_s: float
    y_limits_hz: tuple[float, float]
    glrt_count: int
    glrt_outside_track_scale_count: int


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v2-root", type=Path, required=True)
    parser.add_argument("--v3-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--dwell",
        action="append",
        metavar="LABEL:ZOOM_START_S:ZOOM_END_S",
        help=(
            "dwell and explicit zoom interval; repeat for each row "
            f"(default: {', '.join(DEFAULT_DWELLS)})"
        ),
    )
    parser.add_argument("--dpi", type=int, default=190)
    return parser.parse_args()


def parse_dwell_spec(value: str) -> DwellSpec:
    """Parse and validate one ``LABEL:START:END`` request."""

    parts = value.split(":")
    if len(parts) != 3 or not parts[0].strip():
        raise ValueError(f"invalid dwell specification {value!r}; expected LABEL:START:END")
    try:
        start_s, end_s = (float(item) for item in parts[1:])
    except ValueError as error:
        raise ValueError(f"invalid dwell specification {value!r}; times must be numeric") from error
    if not np.isfinite(start_s) or not np.isfinite(end_s) or start_s < 0 or end_s <= start_s:
        raise ValueError(f"invalid dwell specification {value!r}; require 0 <= START < END")
    return DwellSpec(parts[0].strip(), start_s, end_s)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _repository_relative_path(path: Path) -> str | None:
    try:
        return str(path.resolve().relative_to(Path(__file__).resolve().parents[1]))
    except ValueError:
        return None


def _read_json(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return document


def _summary_paths(root: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for path in sorted(root.glob("*-filter-benchmark-summary.json")):
        label = str(_read_json(path).get("label", ""))
        if not label:
            raise ValueError(f"{path}: source summary does not declare label")
        if label in paths:
            raise ValueError(f"{root}: multiple source summaries declare label {label}")
        paths[label] = path
    return paths


def _load_artifact(summary_path: Path) -> InputArtifact:
    summary = _read_json(summary_path)
    relative = summary.get("npz_relative_path")
    if relative:
        npz_path = summary_path.parent / Path(str(relative)).name
    else:
        npz_path = summary_path.with_name(summary_path.name.replace("-summary.json", ".npz"))
    if not npz_path.is_file():
        raise ValueError(f"{summary_path}: missing replay NPZ {npz_path}")
    declared_hash = summary.get("npz_sha256")
    if declared_hash is not None and declared_hash != sha256(npz_path):
        raise ValueError(f"{summary_path}: declared NPZ digest does not match {npz_path}")
    with np.load(npz_path, allow_pickle=False) as source:
        missing = set(NPZ_FIELDS) - set(source.files)
        if missing:
            raise ValueError(f"{npz_path}: missing arrays {sorted(missing)}")
        arrays = {name: np.asarray(source[name]) for name in NPZ_FIELDS}
    lengths = {len(value) for value in arrays.values()}
    if len(lengths) != 1 or not lengths or not next(iter(lengths)):
        raise ValueError(f"{npz_path}: arrays must have one common non-zero length")
    for name in (
        "window_center_time_s",
        "seed_glrt_margin",
        "absolute_time_s",
        "absolute_cfo_measurement_hz",
        "tracked_absolute_cfo_hz",
    ):
        if not np.all(np.isfinite(arrays[name])):
            raise ValueError(f"{npz_path}: {name} contains non-finite values")
    sample_rate_hz = float(summary["sample_rate_hz"])
    frame_offsets_s = (
        arrays["absolute_time_s"].astype(float)
        - arrays["frame_start_sample"].astype(float) / sample_rate_hz
    )
    frame_offset_s = float(np.median(frame_offsets_s))
    if (
        frame_offset_s < -0.5 / sample_rate_hz
        or frame_offset_s > 1.0 / 750.0 + 0.5 / sample_rate_hz
        or float(np.max(np.abs(frame_offsets_s - frame_offset_s))) > 0.5 / sample_rate_hz + 1e-12
    ):
        raise ValueError(
            f"{npz_path}: frame timestamps do not have one consistent within-frame offset"
        )
    return InputArtifact(summary_path, npz_path, summary, arrays)


def _constant_by_window(
    artifact: InputArtifact,
    field: str,
) -> dict[int, float | int | bool]:
    windows = artifact.arrays["window_index"].astype(int)
    values = artifact.arrays[field]
    result: dict[int, float | int | bool] = {}
    for window in np.unique(windows):
        selected = values[windows == window]
        first = selected[0].item()
        if np.issubdtype(selected.dtype, np.floating):
            matches = np.allclose(selected, first, rtol=0.0, atol=1e-12)
        else:
            matches = bool(np.all(selected == first))
        if not matches:
            raise ValueError(f"{artifact.npz_path}: {field} varies inside window {window}")
        result[int(window)] = first
    return result


def _validate_matching_artifacts(v2: InputArtifact, v3: InputArtifact) -> None:
    for field in IDENTITY_FIELDS:
        if v2.summary.get(field) != v3.summary.get(field):
            raise ValueError(
                f"{v2.summary_path} and {v3.summary_path}: identity mismatch for {field}"
            )
    v2_centers = _constant_by_window(v2, "window_center_time_s")
    v3_centers = _constant_by_window(v3, "window_center_time_s")
    if not set(v3_centers).issubset(v2_centers):
        raise ValueError("V3 window indexes are not a subset of the matched V2 replay")
    sample_rate_hz = float(v3.summary["sample_rate_hz"])
    tolerance_s = 0.5 / sample_rate_hz + 1e-12
    v2_frame_offset_s = float(
        np.median(
            v2.arrays["absolute_time_s"]
            - v2.arrays["frame_start_sample"].astype(float) / sample_rate_hz
        )
    )
    v3_frame_offset_s = float(
        np.median(
            v3.arrays["absolute_time_s"]
            - v3.arrays["frame_start_sample"].astype(float) / sample_rate_hz
        )
    )
    if abs(v2_frame_offset_s - v3_frame_offset_s) > tolerance_s:
        raise ValueError("V2 and V3 within-frame timestamp references do not match")
    if any(
        abs(float(v3_centers[key]) - float(v2_centers[key])) > tolerance_s for key in v3_centers
    ):
        raise ValueError("V2 and V3 window timestamps do not match")
    for field in ("bin_index", "seed_sample_start", "seed_glrt_margin"):
        left = _constant_by_window(v2, field)
        right = _constant_by_window(v3, field)
        for key in right:
            if isinstance(right[key], float):
                matches = bool(np.isclose(right[key], left[key], rtol=0.0, atol=1e-12))
            else:
                matches = right[key] == left[key]
            if not matches:
                raise ValueError(f"V2 and V3 {field} disagree for window {key}")


def _seed_path(v3: InputArtifact) -> Path:
    relative = v3.summary.get("seed_relative_path")
    if relative:
        return v3.summary_path.parent / Path(str(relative)).name
    declared = v3.summary.get("seed_path")
    if declared:
        candidate = v3.summary_path.parent / Path(str(declared)).name
        if candidate.is_file():
            return candidate
    prefix = v3.summary_path.name.removesuffix("-filter-benchmark-summary.json")
    return v3.summary_path.with_name(f"{prefix}-seeds.json")


def _load_and_validate_seeds(v3: InputArtifact) -> tuple[Path, dict[str, Any]]:
    path = _seed_path(v3)
    if not path.is_file():
        raise ValueError(f"{v3.summary_path}: missing sealed seed document {path}")
    declared_hash = v3.summary.get("seed_sha256")
    if declared_hash is not None and declared_hash != sha256(path):
        raise ValueError(f"{v3.summary_path}: declared seed digest does not match {path}")
    document = _read_json(path)
    for field in IDENTITY_FIELDS:
        if field in document and document[field] != v3.summary.get(field):
            raise ValueError(f"{path}: seed identity mismatch for {field}")
    bins = document.get("bins")
    if not isinstance(bins, list) or not bins:
        raise ValueError(f"{path}: seed document contains no bins")
    by_index: dict[int, dict[str, Any]] = {}
    for item in bins:
        if not isinstance(item, dict):
            raise ValueError(f"{path}: seed bin is not an object")
        index = int(item["bin_index"])
        if index in by_index:
            raise ValueError(f"{path}: duplicate bin_index {index}")
        by_index[index] = item
    windows = v3.arrays["window_index"].astype(int)
    npz_bins = _constant_by_window(v3, "bin_index")
    npz_starts = _constant_by_window(v3, "seed_sample_start")
    npz_margins = _constant_by_window(v3, "seed_glrt_margin")
    npz_centers = _constant_by_window(v3, "window_center_time_s")
    for window in np.unique(windows):
        bin_index = int(npz_bins[int(window)])
        item = by_index.get(bin_index)
        if (
            item is None
            or item.get("status") != "selected"
            or not isinstance(item.get("seed"), dict)
        ):
            raise ValueError(f"{path}: replay window {window} has no selected seed bin")
        seed = item["seed"]
        if int(seed["sample_start"]) != int(npz_starts[int(window)]):
            raise ValueError(f"{path}: seed sample disagrees for replay window {window}")
        if not np.isclose(
            float(seed["glrt_margin"]), float(npz_margins[int(window)]), rtol=0.0, atol=1e-12
        ):
            raise ValueError(f"{path}: GLRT margin disagrees for replay window {window}")
        if not np.isclose(
            float(seed["center_time_s"]),
            float(npz_centers[int(window)]),
            rtol=0.0,
            atol=0.5 / float(v3.summary["sample_rate_hz"]) + 1e-12,
        ):
            raise ValueError(f"{path}: seed timestamp disagrees for replay window {window}")
        source_time_s = float(seed["source_time_s"])
        if not np.isclose(
            source_time_s,
            float(seed["sample_start"]) / float(v3.summary["sample_rate_hz"]),
            rtol=0.0,
            atol=0.5 / float(v3.summary["sample_rate_hz"]) + 1e-12,
        ):
            raise ValueError(f"{path}: seed source timestamp disagrees for replay window {window}")
        if not np.isclose(
            float(seed["center_time_s"]) - source_time_s,
            0.010,
            rtol=0.0,
            atol=0.5 / float(v3.summary["sample_rate_hz"]) + 1e-12,
        ):
            raise ValueError(f"{path}: selected seed is not a 20 ms observation")
    return path, document


def _selected_glrt_seeds(
    document: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rows = []
    for item in document["bins"]:
        seed = item.get("seed")
        if item.get("status") == "selected" and isinstance(seed, dict):
            rows.append(
                (
                    float(seed["source_time_s"]),
                    float(seed["center_time_s"]),
                    float(seed["tracking_cfo_hz"]),
                )
            )
    if not rows:
        raise ValueError("seed document has no selected GLRT observations")
    rows.sort()
    start_time_s, center_time_s, cfo_hz = zip(*rows, strict=True)
    return np.asarray(start_time_s), np.asarray(center_time_s), np.asarray(cfo_hz)


def segmented_trace(
    time_s: np.ndarray,
    value: np.ndarray,
    window_index: np.ndarray,
    reacquired: np.ndarray,
    *,
    included: np.ndarray | None = None,
    frame_index: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Insert NaNs at every boundary that must not be rendered as a line."""

    count = len(time_s)
    if not all(len(item) == count for item in (value, window_index, reacquired)):
        raise ValueError("trace arrays must have equal lengths")
    if included is None:
        included = np.ones(count, dtype=bool)
    if frame_index is not None and len(frame_index) != count:
        raise ValueError("frame_index must have the same length as the trace")
    if len(included) != count:
        raise ValueError("included must have the same length as the trace")
    plotted_time: list[float] = []
    plotted_value: list[float] = []
    previous: int | None = None
    segment_count = 0
    for index in range(count):
        if not bool(included[index]):
            previous = None
            continue
        boundary = previous is None
        if previous is not None:
            boundary = (
                int(window_index[index]) != int(window_index[previous])
                or bool(reacquired[index])
                or float(time_s[index]) <= float(time_s[previous])
                or (
                    frame_index is not None
                    and int(frame_index[index]) != int(frame_index[previous]) + 1
                )
            )
        if boundary:
            if plotted_time:
                plotted_time.append(float("nan"))
                plotted_value.append(float("nan"))
            segment_count += 1
        plotted_time.append(float(time_s[index]))
        plotted_value.append(float(value[index]))
        previous = index
    return np.asarray(plotted_time), np.asarray(plotted_value), segment_count


def _load_dwell(spec: DwellSpec, v2_path: Path, v3_path: Path) -> DwellData:
    v2 = _load_artifact(v2_path)
    v3 = _load_artifact(v3_path)
    _validate_matching_artifacts(v2, v3)
    if spec.label != v3.summary["label"]:
        raise ValueError(f"requested {spec.label}, loaded {v3.summary['label']}")
    duration_s = float(v3.summary["sample_count"]) / float(v3.summary["sample_rate_hz"])
    if spec.zoom_end_s > duration_s:
        raise ValueError(
            f"{spec.label}: zoom end {spec.zoom_end_s} exceeds dwell duration {duration_s}"
        )
    seed_path, seed_document = _load_and_validate_seeds(v3)
    glrt_start_time_s, glrt_time_s, glrt_cfo_hz = _selected_glrt_seeds(seed_document)
    return DwellData(
        spec=spec,
        v2=v2,
        v3=v3,
        seed_path=seed_path,
        seed_document=seed_document,
        glrt_start_time_s=glrt_start_time_s,
        glrt_time_s=glrt_time_s,
        glrt_cfo_hz=glrt_cfo_hz,
        duration_s=duration_s,
    )


def _trace_for(
    artifact: InputArtifact, field: str, *, supported_only: bool
) -> tuple[np.ndarray, np.ndarray, int]:
    arrays = artifact.arrays
    included = arrays["measurement_supported"].astype(bool) if supported_only else None
    return segmented_trace(
        arrays["absolute_time_s"].astype(float),
        arrays[field].astype(float),
        arrays["window_index"].astype(int),
        arrays["reacquired"].astype(bool),
        included=included,
        frame_index=arrays["frame_index"].astype(int),
    )


def _zoom_reference(dwell: DwellData) -> ZoomReference:
    start_s, end_s = dwell.spec.zoom_start_s, dwell.spec.zoom_end_s
    v3 = dwell.v3.arrays
    frame_mask = (
        v3["measurement_supported"].astype(bool)
        & (v3["absolute_time_s"] >= start_s)
        & (v3["absolute_time_s"] <= end_s)
    )
    frame_time_s = v3["absolute_time_s"][frame_mask].astype(float)
    frame_cfo_hz = v3["absolute_cfo_measurement_hz"][frame_mask].astype(float)
    if len(frame_time_s) < 2:
        raise ValueError(f"{dwell.spec.label}: zoom contains fewer than two supported frames")
    reference_time_s = float(np.median(frame_time_s))
    design = np.column_stack((np.ones(len(frame_time_s)), frame_time_s - reference_time_s))
    intercept_hz, slope_hz_s = np.linalg.lstsq(design, frame_cfo_hz, rcond=None)[0]

    residual_sets = []
    for artifact, field, support_only in (
        (dwell.v3, "absolute_cfo_measurement_hz", True),
        (dwell.v2, "tracked_absolute_cfo_hz", False),
        (dwell.v3, "tracked_absolute_cfo_hz", False),
    ):
        arrays = artifact.arrays
        mask = (arrays["absolute_time_s"] >= start_s) & (arrays["absolute_time_s"] <= end_s)
        if support_only:
            mask &= arrays["measurement_supported"].astype(bool)
        time_s = arrays["absolute_time_s"][mask].astype(float)
        values_hz = arrays[field][mask].astype(float)
        residual_sets.append(values_hz - (intercept_hz + slope_hz_s * (time_s - reference_time_s)))
    combined = np.concatenate(residual_sets)
    lower_hz = float(np.min(combined))
    upper_hz = float(np.max(combined))
    padding_hz = max(0.06 * (upper_hz - lower_hz), 15.0)
    y_limits_hz = (lower_hz - padding_hz, upper_hz + padding_hz)
    glrt_mask = (dwell.glrt_time_s >= start_s) & (dwell.glrt_time_s <= end_s)
    glrt_residual_hz = dwell.glrt_cfo_hz[glrt_mask] - (
        intercept_hz + slope_hz_s * (dwell.glrt_time_s[glrt_mask] - reference_time_s)
    )
    outside = np.count_nonzero(
        (glrt_residual_hz < y_limits_hz[0]) | (glrt_residual_hz > y_limits_hz[1])
    )
    return ZoomReference(
        reference_time_s=reference_time_s,
        intercept_hz=float(intercept_hz),
        slope_hz_s=float(slope_hz_s),
        y_limits_hz=y_limits_hz,
        glrt_count=int(np.count_nonzero(glrt_mask)),
        glrt_outside_track_scale_count=int(outside),
    )


def _draw_panel(
    axis: plt.Axes,
    dwell: DwellData,
    interval_s: tuple[float, float],
    *,
    zoom_reference: ZoomReference | None = None,
) -> None:
    frame_time, frame_cfo, _ = _trace_for(
        dwell.v3, "absolute_cfo_measurement_hz", supported_only=True
    )
    v2_time, v2_cfo, _ = _trace_for(dwell.v2, "tracked_absolute_cfo_hz", supported_only=False)
    v3_time, v3_cfo, _ = _trace_for(dwell.v3, "tracked_absolute_cfo_hz", supported_only=False)
    glrt_start_time_s = dwell.glrt_start_time_s.copy()
    glrt_end_time_s = glrt_start_time_s + 0.020
    glrt_cfo = dwell.glrt_cfo_hz.copy()
    if zoom_reference is None:
        frame_cfo /= 1000.0
        glrt_cfo /= 1000.0
        v2_cfo /= 1000.0
        v3_cfo /= 1000.0
        glrt_start_cfo = glrt_cfo
        glrt_end_cfo = glrt_cfo
        y_label = "Absolute CFO (kHz)"
    else:
        reference = zoom_reference

        def residual(time_s: np.ndarray, cfo_hz: np.ndarray) -> np.ndarray:
            return cfo_hz - (
                reference.intercept_hz
                + reference.slope_hz_s * (time_s - reference.reference_time_s)
            )

        frame_cfo = residual(frame_time, frame_cfo)
        glrt_start_cfo = residual(glrt_start_time_s, glrt_cfo)
        glrt_end_cfo = residual(glrt_end_time_s, glrt_cfo)
        glrt_cfo = residual(dwell.glrt_time_s, glrt_cfo)
        v2_cfo = residual(v2_time, v2_cfo)
        v3_cfo = residual(v3_time, v3_cfo)
        y_label = "CFO residual to local frame line (Hz)"
    axis.plot(
        frame_time,
        frame_cfo,
        color=FRAME_COLOR,
        linewidth=0.65,
        alpha=0.38,
        zorder=1,
    )
    glrt_segment_time = np.column_stack(
        (glrt_start_time_s, glrt_end_time_s, np.full(len(glrt_cfo), np.nan))
    ).ravel()
    glrt_segment_cfo = np.column_stack(
        (glrt_start_cfo, glrt_end_cfo, np.full(len(glrt_cfo), np.nan))
    ).ravel()
    axis.plot(
        glrt_segment_time,
        glrt_segment_cfo,
        color=GLRT_COLOR,
        linewidth=1.3,
        alpha=0.82,
        zorder=2,
    )
    axis.scatter(
        dwell.glrt_time_s,
        glrt_cfo,
        s=5,
        color=GLRT_COLOR,
        marker="o",
        linewidths=0,
        alpha=0.82,
        zorder=2,
    )
    axis.plot(v2_time, v2_cfo, color=V2_COLOR, linewidth=0.85, alpha=0.82, zorder=3)
    axis.plot(v3_time, v3_cfo, color=V3_COLOR, linewidth=1.05, alpha=0.95, zorder=4)
    axis.set_xlim(*interval_s)
    if zoom_reference is not None:
        axis.set_ylim(*zoom_reference.y_limits_hz)
        if zoom_reference.glrt_outside_track_scale_count:
            axis.text(
                0.012,
                0.025,
                f"{zoom_reference.glrt_outside_track_scale_count}/"
                f"{zoom_reference.glrt_count} GLRT seeds outside track-scale view; see full panel",
                transform=axis.transAxes,
                fontsize=7.5,
                color=GLRT_COLOR,
                ha="left",
                va="bottom",
            )
    axis.grid(True, color=GRID_COLOR, linewidth=0.6, alpha=0.75)
    axis.tick_params(labelsize=8)
    axis.set_xlabel("Time from dwell start (s)", fontsize=9)
    axis.set_ylabel(y_label, fontsize=9)
    axis.margins(y=0.06)


def _legend_handles() -> list[Line2D]:
    return [
        Line2D(
            [],
            [],
            color=GLRT_COLOR,
            marker="o",
            linestyle="-",
            linewidth=1.3,
            markersize=4,
            label="GLRT-64 20 ms observation (winner / 100 ms bin)",
        ),
        Line2D([], [], color=FRAME_COLOR, linewidth=2, label="supported ≈1.333 ms frame CFO"),
        Line2D([], [], color=V2_COLOR, linewidth=2, label="Kalman V2 tracklets"),
        Line2D([], [], color=V3_COLOR, linewidth=2, label="Kalman V3 tracklets"),
    ]


def _save_figure(figure: plt.Figure, path: Path, dpi: int) -> None:
    figure.savefig(
        path,
        dpi=dpi,
        bbox_inches="tight",
        metadata={"Software": "leo-tracker"},
    )
    plt.close(figure)


def _render_composite(dwells: list[DwellData], path: Path, dpi: int) -> None:
    figure, axes = plt.subplots(len(dwells), 2, figsize=(16, 4.15 * len(dwells)), squeeze=False)
    for row, dwell in enumerate(dwells):
        _draw_panel(axes[row, 0], dwell, (0.0, dwell.duration_s))
        reference = _zoom_reference(dwell)
        _draw_panel(
            axes[row, 1],
            dwell,
            (dwell.spec.zoom_start_s, dwell.spec.zoom_end_s),
            zoom_reference=reference,
        )
        axes[row, 0].set_title(f"{dwell.spec.label} · full {dwell.duration_s:.1f} s", fontsize=11)
        axes[row, 1].set_title(
            f"{dwell.spec.label} · prescribed zoom "
            f"{dwell.spec.zoom_start_s:g}–{dwell.spec.zoom_end_s:g} s",
            fontsize=11,
        )
    figure.suptitle(
        "GLRT, frame-CFO, and Kalman tracking — continuity seams intentionally disconnected",
        fontsize=14,
        y=0.995,
    )
    figure.legend(
        handles=_legend_handles(),
        loc="upper center",
        bbox_to_anchor=(0.5, 0.973),
        ncol=4,
        frameon=False,
        fontsize=9,
    )
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.945))
    _save_figure(figure, path, dpi)


def _render_individual(dwell: DwellData, path: Path, dpi: int) -> None:
    figure, axes = plt.subplots(2, 1, figsize=(12.5, 8.2), squeeze=False)
    full, zoom = axes[:, 0]
    _draw_panel(full, dwell, (0.0, dwell.duration_s))
    _draw_panel(
        zoom,
        dwell,
        (dwell.spec.zoom_start_s, dwell.spec.zoom_end_s),
        zoom_reference=_zoom_reference(dwell),
    )
    full.set_title(f"{dwell.spec.label} · full {dwell.duration_s:.1f} s", fontsize=11)
    zoom.set_title(
        f"{dwell.spec.label} · prescribed zoom "
        f"{dwell.spec.zoom_start_s:g}–{dwell.spec.zoom_end_s:g} s",
        fontsize=11,
    )
    figure.suptitle(
        f"{dwell.spec.label}: GLRT, ≈1.333 ms frame CFO, Kalman V2, and Kalman V3",
        fontsize=14,
        y=0.995,
    )
    figure.legend(
        handles=_legend_handles(),
        loc="upper center",
        bbox_to_anchor=(0.5, 0.955),
        ncol=2,
        frameon=False,
        fontsize=9,
    )
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.91))
    _save_figure(figure, path, dpi)


def _artifact_receipt(artifact: InputArtifact) -> dict[str, Any]:
    return {
        "summary_path": str(artifact.summary_path.resolve()),
        "summary_sha256": sha256(artifact.summary_path),
        "npz_path": str(artifact.npz_path.resolve()),
        "npz_sha256": sha256(artifact.npz_path),
        "pnt_source_sha256": artifact.summary.get("pnt_source_sha256"),
        "replay_source_inventory_sha256": artifact.summary.get("replay_source_inventory_sha256"),
    }


def _dwell_receipt(dwell: DwellData, figure_path: Path) -> dict[str, Any]:
    _, _, frame_segments = _trace_for(dwell.v3, "absolute_cfo_measurement_hz", supported_only=True)
    _, _, v2_segments = _trace_for(dwell.v2, "tracked_absolute_cfo_hz", supported_only=False)
    _, _, v3_segments = _trace_for(dwell.v3, "tracked_absolute_cfo_hz", supported_only=False)
    v2_arrays = dwell.v2.arrays
    v3_arrays = dwell.v3.arrays
    reference = _zoom_reference(dwell)
    return {
        "label": dwell.spec.label,
        "session_id": dwell.v3.summary["session_id"],
        "run_id": dwell.v3.summary["run_id"],
        "scope_sha256": dwell.v3.summary["scope_sha256"],
        "stream_id": dwell.v3.summary["stream_id"],
        "receiver_id": dwell.v3.summary["receiver_id"],
        "channel": dwell.v3.summary["channel"],
        "edge": dwell.v3.summary["edge"],
        "sample_rate_hz": dwell.v3.summary["sample_rate_hz"],
        "duration_s": dwell.duration_s,
        "zoom_interval_s": [dwell.spec.zoom_start_s, dwell.spec.zoom_end_s],
        "zoom_reference": {
            "method": "equal-weight line fit to supported V3 frame-CFO inside zoom",
            "reference_time_s": reference.reference_time_s,
            "cfo_at_reference_hz": reference.intercept_hz,
            "slope_hz_s": reference.slope_hz_s,
            "track_scale_y_limits_hz": list(reference.y_limits_hz),
            "glrt_seed_count": reference.glrt_count,
            "glrt_seed_outside_track_scale_count": reference.glrt_outside_track_scale_count,
        },
        "glrt_20ms_seed_count": len(dwell.glrt_time_s),
        "supported_frame_cfo_count": int(np.count_nonzero(v3_arrays["measurement_supported"])),
        "supported_frame_cfo_segment_count": frame_segments,
        "kalman_v2_state_count": len(v2_arrays["absolute_time_s"]),
        "kalman_v2_segment_count": v2_segments,
        "kalman_v2_reacquisition_count": int(np.count_nonzero(v2_arrays["reacquired"])),
        "kalman_v3_state_count": len(v3_arrays["absolute_time_s"]),
        "kalman_v3_segment_count": v3_segments,
        "kalman_v3_reacquisition_count": int(np.count_nonzero(v3_arrays["reacquired"])),
        "v2": _artifact_receipt(dwell.v2),
        "v3": _artifact_receipt(dwell.v3),
        "sealed_seed": {
            "path": str(dwell.seed_path.resolve()),
            "sha256": sha256(dwell.seed_path),
            "schema": dwell.seed_document.get("schema"),
            "selection": dwell.seed_document.get("selection"),
        },
        "individual_figure": {
            "path": str(figure_path.resolve()),
            "repository_relative_path": _repository_relative_path(figure_path),
            "sha256": sha256(figure_path),
        },
    }


def render(
    v2_root: Path,
    v3_root: Path,
    output_root: Path,
    specs: list[DwellSpec],
    *,
    dpi: int = 190,
) -> Path:
    """Validate inputs, render composite/individual figures, and write a receipt."""

    if not specs:
        raise ValueError("at least one dwell must be requested")
    labels = [item.label for item in specs]
    if len(set(labels)) != len(labels):
        raise ValueError("dwell labels must be unique")
    if dpi < 50:
        raise ValueError("dpi must be at least 50")
    v2_paths = _summary_paths(v2_root)
    v3_paths = _summary_paths(v3_root)
    missing_v2 = [label for label in labels if label not in v2_paths]
    missing_v3 = [label for label in labels if label not in v3_paths]
    if missing_v2 or missing_v3:
        raise ValueError(f"missing requested summaries: V2={missing_v2}, V3={missing_v3}")
    dwells = [_load_dwell(spec, v2_paths[spec.label], v3_paths[spec.label]) for spec in specs]
    output_root.mkdir(parents=True, exist_ok=True)
    composite_path = output_root / "three-dwell-pnt-tracking-comparison.png"
    _render_composite(dwells, composite_path, dpi)
    individual_paths: dict[str, Path] = {}
    for dwell in dwells:
        path = output_root / f"{dwell.spec.label.lower()}-pnt-tracking-comparison.png"
        _render_individual(dwell, path, dpi)
        individual_paths[dwell.spec.label] = path
    tool_path = Path(__file__).resolve()
    receipt = {
        "schema": "org.leo.research.pnt-kalman-three-dwell-plots/v1",
        "tool": {
            "path": str(tool_path),
            "repository_relative_path": _repository_relative_path(tool_path),
            "sha256": sha256(tool_path),
        },
        "numpy_version": np.__version__,
        "matplotlib_version": matplotlib.__version__,
        "configuration": {
            "v2_root": str(v2_root.resolve()),
            "v3_root": str(v3_root.resolve()),
            "output_root": str(output_root.resolve()),
            "dpi": dpi,
            "continuity_policy": (
                "line breaks before every changed window_index, reacquired state, "
                "non-increasing timestamp, frame-index discontinuity, and excluded frame"
            ),
            "frame_cfo_policy": "V3 absolute frame-CFO measurements with support=true only",
            "glrt_policy": (
                "all selected sealed GLRT-64 20ms observations; one winner per 100ms bin; "
                "each is drawn from source_time_s through source_time_s + 0.020 seconds"
            ),
            "zoom_policy": (
                "subtract an equal-weight local line fitted to supported V3 frame-CFO; set the "
                "track-scale y range from frame-CFO plus V2/V3 states and report clipped GLRT seeds"
            ),
        },
        "composite_figure": {
            "path": str(composite_path.resolve()),
            "repository_relative_path": _repository_relative_path(composite_path),
            "sha256": sha256(composite_path),
            "layout": f"{len(dwells)} rows x 2 columns (full dwell, prescribed zoom)",
        },
        "dwells": [_dwell_receipt(dwell, individual_paths[dwell.spec.label]) for dwell in dwells],
    }
    receipt_path = output_root / "three-dwell-pnt-tracking-summary.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt_path


def main() -> None:
    arguments = _arguments()
    try:
        specs = [parse_dwell_spec(value) for value in (arguments.dwell or DEFAULT_DWELLS)]
        receipt = render(
            arguments.v2_root,
            arguments.v3_root,
            arguments.output_root,
            specs,
            dpi=arguments.dpi,
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(receipt)


if __name__ == "__main__":
    main()
