#!/usr/bin/env python3
"""Run the preregistered V3/V4 acquisition and downstream-rate canary."""

from __future__ import annotations

import argparse
import csv
import dataclasses
import gzip
import hashlib
import importlib.util
import json
import math
import os
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.analysis.qam.pilot import (  # noqa: E402
    PilotFrameCfoConfig,
    estimate_edge_pilot_frame_cfo_split_validation,
)
from leo.analysis.research.v3_v4_downstream_rate import (  # noqa: E402
    V3V4ForecastConfig,
    V3V4RatePrediction,
    V3V4SplitFrame,
    common_mode_forecasts,
    method_forecasts,
)
from leo.analysis.research.v3_v4_rate_protocol import (  # noqa: E402
    SESSION_ID,
    load_v3_v4_rate_protocol,
)
from leo.analysis.starlink.templates import OFDM_SYMBOL_DURATION_S  # noqa: E402

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROTOCOL = Path("config/analysis/v3-v4-downstream-rate-benchmark-v1.json")
DEFAULT_CAPTURE_ROOT = Path("/srv/bulk/leo/recordings/2026/08/25/cap-20260825T150802-473cb5bbcbd6")
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_25_v3_v4_downstream_rate")
SCHEMA = "org.leo.research.v3-v4-downstream-rate-benchmark/v1"
FRAME_INVENTORY_SCHEMA = "org.leo.research.v3-v4-split-frame-inventory/v1"
ARTIFACT_SCHEMA = "org.leo.research.v3-v4-downstream-rate-artifacts/v1"
METHOD_V3 = "v3_alignment"
METHOD_V4 = "v4_acquisition"
METHODS = (METHOD_V3, METHOD_V4)
COLORS = {METHOD_V3: "#2b6cb0", METHOD_V4: "#d97706"}


@dataclass(frozen=True, slots=True)
class AcquisitionCoordinate:
    method: str
    epoch_sample: int
    absolute_cfo_hz: float
    source: str
    tracking_complete: bool


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--capture-root", type=Path, default=DEFAULT_CAPTURE_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args()


def _load_canary_module() -> Any:
    path = REPOSITORY_ROOT / "tools" / "replay_150802_pnt_kalman_v4_canary.py"
    name = "leo_frozen_v4_canary_for_downstream_rate"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load frozen canary support: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _validate_output_root(path: Path, capture_root: Path) -> Path:
    output = path.resolve()
    capture = capture_root.resolve()
    qnap = Path("/mnt/qnap01").resolve()
    if output in (capture, qnap) or capture in output.parents or qnap in output.parents:
        raise ValueError("benchmark output cannot be written beneath capture or QNAP storage")
    output.mkdir(parents=True, exist_ok=True)
    return output


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _plain(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    if isinstance(value, np.generic):
        return _plain(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("benchmark output contains a nonfinite float")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"benchmark output contains unsupported {type(value).__name__}")


def _json_bytes(value: object) -> bytes:
    return (json.dumps(_plain(value), allow_nan=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as target:
            target.write(payload)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary_name, path)
        os.chmod(path, 0o664)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _scientific_rows(protocol: Any) -> dict[int, dict[str, Any]]:
    rows = protocol.scientific_receipt.get("rows")
    if not isinstance(rows, list) or len(rows) != 537:
        raise ValueError("scientific receipt does not contain the frozen 537 rows")
    output: dict[int, dict[str, Any]] = {}
    for raw in rows:
        if not isinstance(raw, dict) or isinstance(raw.get("row_index"), bool):
            raise ValueError("scientific receipt row is malformed")
        index = int(raw["row_index"])
        if index in output:
            raise ValueError("scientific receipt row indexes are not unique")
        output[index] = raw
    if set(output) != set(range(537)):
        raise ValueError("scientific receipt does not account every frozen row index")
    return output


def _yield_summary(rows: Mapping[int, dict[str, Any]]) -> dict[str, Any]:
    numerical: Counter[tuple[str, str]] = Counter(
        (str(row["v3"]["status"]), str(row["v4"]["numerical_status"])) for row in rows.values()
    )
    acquisition: Counter[tuple[bool, bool]] = Counter()
    ledger: list[dict[str, Any]] = []
    for index in sorted(rows):
        row = rows[index]
        v3_alignment = row["v3"].get("initial_alignment")
        v3_acquired = isinstance(v3_alignment, dict) and v3_alignment.get("status") == "complete"
        v4_components = row["v4"].get("component_inventory")
        if not isinstance(v4_components, list):
            raise ValueError("V4 component inventory is malformed")
        v4_acquired = any(component.get("accepted") is True for component in v4_components)
        acquisition[(v3_acquired, v4_acquired)] += 1
        ledger.append(
            {
                "row_index": index,
                "row_key": row["row_key"],
                "v3_alignment_complete": v3_acquired,
                "v3_tracking_status": row["v3"]["status"],
                "v4_accepted_mode": v4_acquired,
                "v4_tracking_status": row["v4"]["numerical_status"],
            }
        )
    return {
        "population_row_count": len(rows),
        "v3_alignment_complete_count": sum(count for (v3, _v4), count in acquisition.items() if v3),
        "v4_accepted_mode_count": sum(count for (_v3, v4), count in acquisition.items() if v4),
        "v3_numerical_complete_count": sum(
            count for (v3, _v4), count in numerical.items() if v3 == "complete"
        ),
        "v4_numerical_complete_count": sum(
            count for (_v3, v4), count in numerical.items() if v4 == "complete"
        ),
        "acquisition_contingency": {
            (
                f"v3_{'acquired' if v3 else 'not_acquired'}"
                f"__v4_{'acquired' if v4 else 'not_acquired'}"
            ): count
            for (v3, v4), count in sorted(acquisition.items())
        },
        "numerical_contingency": {
            f"v3_{v3}__v4_{v4}": count for (v3, v4), count in sorted(numerical.items())
        },
        "row_ledger": ledger,
    }


def _v3_coordinate(row: dict[str, Any]) -> AcquisitionCoordinate | None:
    alignment = row["v3"].get("initial_alignment")
    if not isinstance(alignment, dict) or alignment.get("status") != "complete":
        return None
    return AcquisitionCoordinate(
        method=METHOD_V3,
        epoch_sample=int(alignment["epoch_sample"]),
        absolute_cfo_hz=float(alignment["absolute_cfo_hz"]),
        source="V3 initial_alignment",
        tracking_complete=row["v3"]["status"] == "complete",
    )


def _v4_coordinate(row: dict[str, Any]) -> AcquisitionCoordinate | None:
    inventory = row["v4"].get("component_inventory")
    if not isinstance(inventory, list):
        raise ValueError("V4 component inventory is malformed")
    accepted = [component for component in inventory if component.get("accepted") is True]
    if not accepted:
        return None
    selected = min(accepted, key=lambda item: (int(item["rank"]), str(item["candidate_id"])))
    return AcquisitionCoordinate(
        method=METHOD_V4,
        epoch_sample=int(selected["epoch_sample"]),
        absolute_cfo_hz=float(selected["absolute_cfo_hz"]),
        source="lowest-rank accepted V4 component",
        tracking_complete=selected.get("tracking_status") == "complete",
    )


def _extract_frames(
    values: np.ndarray,
    *,
    anchor_sample_start: int,
    coordinate: AcquisitionCoordinate,
    edge: str,
    source_rate_hz_s: float,
    sample_rate_hz: int,
) -> tuple[V3V4SplitFrame, ...]:
    frame_content = round(302 * sample_rate_hz * OFDM_SYMBOL_DURATION_S)
    reference_offset_samples = float(
        np.mean((np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S) * sample_rate_hz
    )
    settings = PilotFrameCfoConfig(
        residual_half_width_hz=2_000.0,
        minimum_exact_coherence=0.02,
        minimum_coherence_margin=0.0,
    )
    output = []
    frame_ordinal = 0
    while True:
        local_start = coordinate.epoch_sample + round(frame_ordinal * sample_rate_hz / 750.0)
        if local_start + frame_content + 1 > len(values):
            break
        if local_start < 1:
            frame_ordinal += 1
            continue
        global_start = anchor_sample_start + local_start
        reference_sample = global_start + reference_offset_samples
        delta_s = (reference_sample - anchor_sample_start) / sample_rate_hz
        nco_cfo_hz = coordinate.absolute_cfo_hz + source_rate_hz_s * delta_s
        split = estimate_edge_pilot_frame_cfo_split_validation(
            values[local_start - 1 : local_start + frame_content + 1],
            float(sample_rate_hz),
            frame_start_sample=global_start,
            acquisition_absolute_cfo_hz=nco_cfo_hz,
            edge=edge,
            config=settings,
        )
        numeric = (
            split.even_absolute_cfo_hz,
            split.odd_absolute_cfo_hz,
            split.even_frequency_uncertainty_hz,
            split.even_exact_coherence,
            split.even_control_coherence,
        )
        if all(value is not None and math.isfinite(float(value)) for value in numeric):
            assert split.even_absolute_cfo_hz is not None
            assert split.odd_absolute_cfo_hz is not None
            assert split.even_frequency_uncertainty_hz is not None
            assert split.even_exact_coherence is not None
            assert split.even_control_coherence is not None
            output.append(
                V3V4SplitFrame(
                    frame_ordinal=frame_ordinal,
                    frame_start_sample=global_start,
                    reference_time_s=reference_sample / sample_rate_hz,
                    even_cfo_hz=float(split.even_absolute_cfo_hz),
                    odd_cfo_hz=float(split.odd_absolute_cfo_hz),
                    even_frequency_uncertainty_hz=float(split.even_frequency_uncertainty_hz),
                    even_exact_coherence=float(split.even_exact_coherence),
                    even_control_coherence=float(split.even_control_coherence),
                    training_supported=bool(split.training_supported),
                    even_search_boundary=bool(split.even_search_boundary),
                    odd_search_boundary=bool(split.odd_search_boundary),
                )
            )
        frame_ordinal += 1
    return tuple(output)


def _population_for_coordinates(coordinates: Mapping[str, AcquisitionCoordinate]) -> str:
    methods = set(coordinates)
    if methods == set(METHODS):
        return "both_method_method_own"
    if methods == {METHOD_V4}:
        return "v4_only_recovered"
    if methods == {METHOD_V3}:
        return "v3_only_alignment"
    return "neither_acquired"


def _prediction_document(
    prediction: V3V4RatePrediction,
    *,
    anchor_sample_start: int,
    sample_rate_hz: int,
) -> dict[str, Any]:
    target_sample = anchor_sample_start + round(
        prediction.target_offset_ms * sample_rate_hz / 1_000
    )
    document = dataclasses.asdict(prediction)
    document.update(
        {
            "pair_id": (
                f"{prediction.anchor_key}:{prediction.target_offset_ms}ms:{prediction.history_ms}ms"
            ),
            "recording_block_index": target_sample // round(sample_rate_hz * 0.250),
            "actual_target_offset_ms": 1_000.0
            * (prediction.target_frame_start_sample - anchor_sample_start)
            / sample_rate_hz,
            "actual_forecast_ms": 1_000.0
            * (prediction.target_reference_time_s - prediction.fit_reference_time_s),
        }
    )
    return document


def _aggregate_predictions(predictions: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in predictions:
        grouped[(str(row["population"]), int(row["history_ms"]), str(row["method"]))].append(row)
    output = []
    for (population, history_ms, method), rows in sorted(grouped.items()):
        residual = np.asarray([float(row["odd_residual_hz"]) for row in rows])
        by_anchor: dict[str, list[float]] = defaultdict(list)
        by_block: dict[int, list[float]] = defaultdict(list)
        for row in rows:
            by_anchor[str(row["anchor_key"])].append(float(row["odd_residual_hz"]))
            by_block[int(row["recording_block_index"])].append(float(row["odd_residual_hz"]))
        anchor_mse = [float(np.mean(np.square(values))) for values in by_anchor.values()]
        block_mse = [float(np.mean(np.square(values))) for values in by_block.values()]
        output.append(
            {
                "population": population,
                "history_ms": history_ms,
                "method": method,
                "prediction_count": len(rows),
                "anchor_count": len(by_anchor),
                "recording_block_count": len(by_block),
                "pooled_rms_hz": float(np.sqrt(np.mean(residual**2))),
                "anchor_equal_rms_hz": float(np.sqrt(np.mean(anchor_mse))),
                "block_equal_rms_hz": float(np.sqrt(np.mean(block_mse))),
                "median_absolute_error_hz": float(np.median(np.abs(residual))),
                "mean_fitted_rate_hz_s": float(
                    np.mean([float(row["fitted_rate_hz_s"]) for row in rows])
                ),
                "median_fit_rms_hz": float(np.median([float(row["fit_rms_hz"]) for row in rows])),
            }
        )
    return output


def _paired_summary(
    predictions: Sequence[dict[str, Any]],
    aggregates: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    common = [row for row in predictions if row["population"] == "both_method_common_mode"]
    by_pair: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in common:
        by_pair[str(row["pair_id"])][str(row["method"])] = row
    if any(set(pair) != set(METHODS) for pair in by_pair.values()):
        raise ValueError("common-mode prediction rows are not fully paired")
    comparisons: list[dict[str, Any]] = []
    for history_ms in (20, 500):
        selected = [
            pair
            for pair in by_pair.values()
            if int(next(iter(pair.values()))["history_ms"]) == history_ms
        ]
        left = np.asarray(
            [float(pair[METHOD_V3]["odd_residual_hz"]) for pair in selected], dtype=float
        )
        right = np.asarray(
            [float(pair[METHOD_V4]["odd_residual_hz"]) for pair in selected], dtype=float
        )
        aggregate_by_method = {
            str(row["method"]): row
            for row in aggregates
            if row["population"] == "both_method_common_mode" and row["history_ms"] == history_ms
        }
        if not len(selected):
            comparisons.append(
                {
                    "history_ms": history_ms,
                    "pair_count": 0,
                    "anchor_count": 0,
                    "v4_over_v3_anchor_equal_rms_ratio": None,
                }
            )
            continue
        v3_aggregate = aggregate_by_method[METHOD_V3]
        v4_aggregate = aggregate_by_method[METHOD_V4]
        comparisons.append(
            {
                "history_ms": history_ms,
                "pair_count": len(selected),
                "anchor_count": len({str(pair[METHOD_V3]["anchor_key"]) for pair in selected}),
                "v3_pooled_rms_hz": float(np.sqrt(np.mean(left**2))),
                "v4_pooled_rms_hz": float(np.sqrt(np.mean(right**2))),
                "v4_over_v3_pooled_rms_ratio": float(
                    np.sqrt(np.mean(right**2)) / np.sqrt(np.mean(left**2))
                ),
                "v3_anchor_equal_rms_hz": v3_aggregate["anchor_equal_rms_hz"],
                "v4_anchor_equal_rms_hz": v4_aggregate["anchor_equal_rms_hz"],
                "v4_over_v3_anchor_equal_rms_ratio": float(
                    v4_aggregate["anchor_equal_rms_hz"] / v3_aggregate["anchor_equal_rms_hz"]
                ),
                "v3_block_equal_rms_hz": v3_aggregate["block_equal_rms_hz"],
                "v4_block_equal_rms_hz": v4_aggregate["block_equal_rms_hz"],
                "v4_over_v3_block_equal_rms_ratio": float(
                    v4_aggregate["block_equal_rms_hz"] / v3_aggregate["block_equal_rms_hz"]
                ),
                "v4_lower_absolute_error_pair_count": int(
                    np.count_nonzero(np.abs(right) < np.abs(left))
                ),
                "equal_absolute_error_pair_count": int(
                    np.count_nonzero(np.isclose(np.abs(right), np.abs(left), atol=1e-9))
                ),
            }
        )
    return {"histories": comparisons}


def _interpretation(
    yield_summary: dict[str, Any],
    paired: dict[str, Any],
) -> dict[str, Any]:
    fixed = next(row for row in paired["histories"] if row["history_ms"] == 500)
    support = bool(fixed["anchor_count"] >= 8 and fixed["pair_count"] >= 40)
    numerical_yield = bool(
        yield_summary["v4_numerical_complete_count"] >= yield_summary["v3_numerical_complete_count"]
    )
    ratio = fixed["v4_over_v3_anchor_equal_rms_ratio"]
    noninferior = bool(ratio is not None and ratio <= 1.05)
    material = bool(ratio is not None and ratio <= 0.95)
    return {
        "adequate_common_support": support,
        "v4_numerical_yield_not_lower": numerical_yield,
        "common_fixed_500_noninferior": noninferior,
        "common_fixed_500_material_improvement": material,
        "v4_acquisition_useful_gate": support and numerical_yield and noninferior,
        "standard_promotion": False,
        "primary_ratio": "anchor-equal fixed-500-ms future odd-Qin RMS, V4/V3",
        "claim": (
            "opened-canary acquisition/downstream implementation evidence only; not holdout, "
            "physical Doppler truth, or Standard qualification"
        ),
    }


def _write_predictions(path: Path, predictions: Sequence[dict[str, Any]]) -> None:
    fields = (
        "pair_id",
        "population",
        "method",
        "anchor_key",
        "target_offset_ms",
        "target_ordinal",
        "target_frame_start_sample",
        "target_reference_time_s",
        "actual_target_offset_ms",
        "recording_block_index",
        "history_ms",
        "training_frame_count",
        "training_first_ordinal",
        "training_last_ordinal",
        "training_span_ms",
        "fit_reference_time_s",
        "actual_forecast_ms",
        "fitted_cfo_hz",
        "fitted_rate_hz_s",
        "fit_rms_hz",
        "predicted_cfo_hz",
        "target_odd_cfo_hz",
        "odd_residual_hz",
    )
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", newline="", encoding="utf-8") as target:
            writer = csv.DictWriter(target, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(predictions)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary_name, path)
        os.chmod(path, 0o664)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _write_frame_inventory(path: Path, inventory: Sequence[dict[str, Any]]) -> None:
    payload = _json_bytes({"schema": FRAME_INVENTORY_SCHEMA, "frames": inventory})
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
                compressed.write(payload)
            raw.flush()
            os.fsync(raw.fileno())
        os.replace(temporary_name, path)
        os.chmod(path, 0o664)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _render_yield(path: Path, summary: dict[str, Any]) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(12.5, 4.8), constrained_layout=True)
    labels = ("acquired lattice", "numerical track")
    v3 = (
        summary["v3_alignment_complete_count"],
        summary["v3_numerical_complete_count"],
    )
    v4 = (summary["v4_accepted_mode_count"], summary["v4_numerical_complete_count"])
    x = np.arange(2)
    width = 0.34
    axes[0].bar(x - width / 2, v3, width, color=COLORS[METHOD_V3], label="V3")
    axes[0].bar(x + width / 2, v4, width, color=COLORS[METHOD_V4], label="V4")
    axes[0].set_xticks(x, labels)
    axes[0].set_ylabel("Frozen rows (of 537)")
    axes[0].set_title("A · Acquisition and numerical yield are different questions", loc="left")
    axes[0].legend(frameon=False)
    axes[0].grid(axis="y", alpha=0.25)
    for index, values in enumerate((v3, v4)):
        offset = -width / 2 if index == 0 else width / 2
        for column, value in enumerate(values):
            axes[0].text(column + offset, value + 7, str(value), ha="center", va="bottom")

    contingency = summary["numerical_contingency"]
    categories = (
        "both complete",
        "V4 only",
        "V3 only",
        "neither",
    )
    contingency_values = (
        contingency.get("v3_complete__v4_complete", 0),
        contingency.get("v3_no_result__v4_complete", 0),
        contingency.get("v3_complete__v4_no_result", 0),
        contingency.get("v3_no_result__v4_no_result", 0),
    )
    bars = axes[1].barh(
        categories,
        contingency_values,
        color=("#64748b", COLORS[METHOD_V4], COLORS[METHOD_V3], "#cbd5e1"),
    )
    axes[1].bar_label(bars, padding=4)
    axes[1].set_xlim(0, max(contingency_values) * 1.15)
    axes[1].set_xlabel("Frozen rows")
    axes[1].set_title("B · Full failure ledger, unchanged population", loc="left")
    axes[1].grid(axis="x", alpha=0.25)
    figure.suptitle(
        "V3/V4 opened-canary yield · cap-20260825T150802-473cb5bbcbd6",
        fontsize=14,
    )
    figure.savefig(path, dpi=180)
    plt.close(figure)


def _render_paired(
    path: Path,
    predictions: Sequence[dict[str, Any]],
    paired: dict[str, Any],
) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(13.5, 5.1), constrained_layout=True)
    histories = paired["histories"]
    x = np.arange(len(histories))
    width = 0.34
    v3 = [row.get("v3_anchor_equal_rms_hz", math.nan) for row in histories]
    v4 = [row.get("v4_anchor_equal_rms_hz", math.nan) for row in histories]
    axes[0].bar(x - width / 2, v3, width, color=COLORS[METHOD_V3], label="V3 lattice")
    axes[0].bar(x + width / 2, v4, width, color=COLORS[METHOD_V4], label="V4 lattice")
    axes[0].set_xticks(x, [f"fixed {row['history_ms']} ms" for row in histories])
    axes[0].set_ylabel("Anchor-equal future odd-Qin RMS (Hz)")
    axes[0].set_title("A · Same target ordinals and even-only training mask", loc="left")
    axes[0].legend(frameon=False)
    axes[0].grid(axis="y", alpha=0.25)

    common = [
        row
        for row in predictions
        if row["population"] == "both_method_common_mode" and row["history_ms"] == 500
    ]
    by_pair: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in common:
        by_pair[str(row["pair_id"])][str(row["method"])] = row
    left = np.asarray([abs(float(pair[METHOD_V3]["odd_residual_hz"])) for pair in by_pair.values()])
    right = np.asarray(
        [abs(float(pair[METHOD_V4]["odd_residual_hz"])) for pair in by_pair.values()]
    )
    axes[1].scatter(left, right, s=24, alpha=0.65, color="#334155", edgecolors="none")
    limit = max(1.0, float(max(np.max(left, initial=0.0), np.max(right, initial=0.0))))
    axes[1].plot((0, limit), (0, limit), color="#94a3b8", linestyle="--", linewidth=1.2)
    axes[1].set_xlim(0, limit * 1.03)
    axes[1].set_ylim(0, limit * 1.03)
    axes[1].set_xlabel("V3 absolute odd-Qin error (Hz)")
    axes[1].set_ylabel("V4 absolute odd-Qin error (Hz)")
    axes[1].set_title("B · Fixed-500-ms paired future predictions", loc="left")
    axes[1].grid(alpha=0.25)
    fixed_500 = next(row for row in histories if row["history_ms"] == 500)
    figure.suptitle(
        "Downstream rate after V3 versus V4 acquisition · 125 ms future response\n"
        f"{fixed_500['anchor_count']} common anchors / {fixed_500['pair_count']} fixed-500-ms "
        "pairs — below the preregistered 8-anchor / 40-pair support gate",
        fontsize=14,
    )
    figure.savefig(path, dpi=180)
    plt.close(figure)


def _render_anchor_residuals(path: Path, predictions: Sequence[dict[str, Any]]) -> None:
    common = [
        row
        for row in predictions
        if row["population"] == "both_method_common_mode" and row["history_ms"] == 500
    ]
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in common:
        grouped[(str(row["anchor_key"]), str(row["method"]))].append(float(row["odd_residual_hz"]))
    anchors = sorted({key[0] for key in grouped})
    figure, axes = plt.subplots(2, 1, figsize=(13.5, 8.0), constrained_layout=True)
    x = np.arange(len(anchors))
    width = 0.36
    for method, offset in ((METHOD_V3, -width / 2), (METHOD_V4, width / 2)):
        values = [
            math.sqrt(float(np.mean(np.square(grouped[(anchor, method)]))))
            if grouped[(anchor, method)]
            else math.nan
            for anchor in anchors
        ]
        axes[0].bar(x + offset, values, width, color=COLORS[method], label=method)
    axes[0].set_xticks(x, [anchor[7:15] for anchor in anchors], rotation=45, ha="right")
    axes[0].set_ylabel("Future odd-Qin RMS (Hz)")
    axes[0].set_title("A · Fixed-500-ms error by preregistered common anchor", loc="left")
    axes[0].legend(frameon=False)
    axes[0].grid(axis="y", alpha=0.25)

    if anchors:
        selected = anchors[0]
        for method in METHODS:
            rows = sorted(
                (
                    row
                    for row in common
                    if row["anchor_key"] == selected and row["method"] == method
                ),
                key=lambda row: int(row["target_offset_ms"]),
            )
            axes[1].plot(
                [row["target_offset_ms"] for row in rows],
                [row["odd_residual_hz"] for row in rows],
                marker="o",
                markersize=3.5,
                color=COLORS[method],
                label=method,
            )
        axes[1].set_title(f"B · Lexicographically first common anchor {selected[7:19]}", loc="left")
    axes[1].axhline(0.0, color="#64748b", linewidth=1.0)
    axes[1].set_xlabel("Target offset from frozen anchor (ms)")
    axes[1].set_ylabel("Future odd-Qin residual (Hz)")
    axes[1].legend(frameon=False)
    axes[1].grid(alpha=0.25)
    figure.suptitle(
        "No response-selected example: fixed anchor ordering and full residual ledger\n"
        f"Only {len(anchors)} anchors passed the fixed-500-ms common mask",
        fontsize=14,
    )
    figure.savefig(path, dpi=180)
    plt.close(figure)


def run_benchmark(protocol_path: Path, capture_root: Path, output_root: Path) -> dict[str, Any]:
    protocol = load_v3_v4_rate_protocol(protocol_path, repository_root=REPOSITORY_ROOT)
    output = _validate_output_root(output_root, capture_root)
    rows = _scientific_rows(protocol)
    yield_summary = _yield_summary(rows)
    population_windows = protocol.frozen_population["windows"]
    canary = _load_canary_module()
    reader = canary.FrozenCi16Reader(
        capture_root,
        expected_manifest_digest=protocol.document["dataset_policy"]["recording_manifest_sha256"],
        expected_session_id=SESSION_ID,
        maximum_cached_chunks=2,
    )
    sample_rate_hz = int(protocol.document["measurement"]["sample_rate_hz"])
    if not math.isclose(reader.sample_rate_hz, sample_rate_hz, rel_tol=0.0, abs_tol=0.0):
        raise ValueError("recording sample rate disagrees with the protocol")
    segment_sample_count = round(
        protocol.document["downstream_anchor_selection"]["segment_duration_ms"]
        * sample_rate_hz
        / 1_000
    )
    forecast_config = V3V4ForecastConfig()

    anchor_ledger = []
    inventory = []
    prediction_documents = []
    for position, anchor in enumerate(protocol.anchors, start=1):
        print(f"anchor {position}/{len(protocol.anchors)} {anchor.row_key}", flush=True)
        receipt_row = rows[anchor.row_index]
        source = population_windows[anchor.row_index]
        if receipt_row["row_key"] != anchor.row_key:
            raise ValueError("anchor row key disagrees with scientific receipt")
        coordinates = {
            coordinate.method: coordinate
            for coordinate in (_v3_coordinate(receipt_row), _v4_coordinate(receipt_row))
            if coordinate is not None
        }
        population = _population_for_coordinates(coordinates)
        ledger: dict[str, Any] = {
            **dataclasses.asdict(anchor),
            "population": population,
            "source_rate_hz_s": (
                0.0
                if source.get("standard_v1_local_rate_hz_s") is None
                else float(source["standard_v1_local_rate_hz_s"])
            ),
            "methods": {},
            "common_prediction_count": 0,
            "iq_read_status": "not_required_no_acquisition",
            "failure_reason": None,
        }
        if not coordinates:
            anchor_ledger.append(ledger)
            continue
        try:
            values, _receipts = reader.read_complex(
                anchor.stream,
                anchor.receiver,
                anchor.source_probe_sample_start,
                segment_sample_count,
            )
            ledger["iq_read_status"] = "complete_digest_verified"
        except Exception as error:  # retained in the complete failure ledger
            ledger["iq_read_status"] = "error"
            ledger["failure_reason"] = f"{type(error).__name__}: {error}"
            anchor_ledger.append(ledger)
            continue

        points_by_method: dict[str, tuple[V3V4SplitFrame, ...]] = {}
        for method in METHODS:
            coordinate = coordinates.get(method)
            if coordinate is None:
                ledger["methods"][method] = {"status": "not_acquired"}
                continue
            try:
                points = _extract_frames(
                    values,
                    anchor_sample_start=anchor.source_probe_sample_start,
                    coordinate=coordinate,
                    edge=str(source["edge"]),
                    source_rate_hz_s=float(ledger["source_rate_hz_s"]),
                    sample_rate_hz=sample_rate_hz,
                )
            except Exception as error:  # retained; another method may still complete
                ledger["methods"][method] = {
                    "status": "extraction_error",
                    "reason": f"{type(error).__name__}: {error}",
                    "coordinate": dataclasses.asdict(coordinate),
                }
                continue
            points_by_method[method] = points
            own = method_forecasts(
                points,
                method=method,
                population=population,
                anchor_key=anchor.row_key,
                config=forecast_config,
            )
            for prediction in own:
                prediction_documents.append(
                    _prediction_document(
                        prediction,
                        anchor_sample_start=anchor.source_probe_sample_start,
                        sample_rate_hz=sample_rate_hz,
                    )
                )
            ledger["methods"][method] = {
                "status": "complete",
                "coordinate": dataclasses.asdict(coordinate),
                "frame_count": len(points),
                "even_training_supported_count": sum(point.training_supported for point in points),
                "even_boundary_count": sum(point.even_search_boundary for point in points),
                "odd_boundary_count": sum(point.odd_search_boundary for point in points),
                "own_fixed_20_prediction_count": sum(item.history_ms == 20 for item in own),
                "own_fixed_500_prediction_count": sum(item.history_ms == 500 for item in own),
            }
            for point in points:
                inventory.append(
                    {
                        "anchor_key": anchor.row_key,
                        "method": method,
                        **dataclasses.asdict(point),
                    }
                )
        if set(points_by_method) == set(METHODS):
            common = common_mode_forecasts(
                points_by_method[METHOD_V3],
                points_by_method[METHOD_V4],
                left_method=METHOD_V3,
                right_method=METHOD_V4,
                anchor_key=anchor.row_key,
                config=forecast_config,
            )
            for prediction in common:
                prediction_documents.append(
                    _prediction_document(
                        prediction,
                        anchor_sample_start=anchor.source_probe_sample_start,
                        sample_rate_hz=sample_rate_hz,
                    )
                )
            ledger["common_prediction_count"] = len(common) // 2
        anchor_ledger.append(ledger)

    prediction_documents.sort(
        key=lambda row: (
            str(row["population"]),
            str(row["anchor_key"]),
            int(row["target_offset_ms"]),
            int(row["history_ms"]),
            str(row["method"]),
        )
    )
    inventory.sort(
        key=lambda row: (
            str(row["anchor_key"]),
            str(row["method"]),
            int(row["frame_ordinal"]),
        )
    )
    aggregates = _aggregate_predictions(prediction_documents)
    paired = _paired_summary(prediction_documents, aggregates)
    interpretation = _interpretation(yield_summary, paired)
    verified_chunks = [
        dataclasses.asdict(receipt) for _path, receipt in sorted(reader.verified_chunks.items())
    ]
    result = {
        "schema": SCHEMA,
        "execution_utc": datetime.now(UTC).isoformat(),
        "repository_commit": subprocess.run(
            ("git", "rev-parse", "HEAD"),
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip(),
        "protocol": {
            "path": str(protocol.path.relative_to(REPOSITORY_ROOT)),
            "sha256": protocol.digest,
            "preregistration_commit": "759aa0546007b1894bbe359749394e5d71e4b75d",
        },
        "capture": {
            "session_id": SESSION_ID,
            "recording_manifest_sha256": reader.manifest_digest,
            "post_refill_fix": True,
            "opened_canary_not_holdout": True,
        },
        "method_scope": {
            "v3": "V3 discrete initial_alignment plus common parity-split downstream fitter",
            "v4": (
                "lowest-rank accepted V4 acquisition component plus the same parity-split "
                "downstream fitter"
            ),
            "v4_continuous_tracker": "unchanged V3 core; V4 is not a new tracker",
            "upstream_conditioning_disclosure": (
                "frozen Standard sources and V3/V4 acquisition include wider and/or odd-Qin "
                "evidence; odd Qin is withheld only from this downstream line"
            ),
        },
        "implementation": {
            "tool_sha256": _sha256(Path(__file__)),
            "downstream_rate_module_sha256": _sha256(
                REPOSITORY_ROOT
                / "src"
                / "leo"
                / "analysis"
                / "research"
                / "v3_v4_downstream_rate.py"
            ),
            "protocol_loader_sha256": _sha256(
                REPOSITORY_ROOT / "src" / "leo" / "analysis" / "research" / "v3_v4_rate_protocol.py"
            ),
            "split_frame_cfo_source_sha256": _sha256(
                REPOSITORY_ROOT / "src" / "leo" / "analysis" / "qam" / "pilot.py"
            ),
        },
        "yield": yield_summary,
        "downstream": {
            "anchor_ledger": anchor_ledger,
            "frame_inventory_count": len(inventory),
            "prediction_count": len(prediction_documents),
            "aggregates": aggregates,
            "paired_common_mode": paired,
        },
        "interpretation": interpretation,
        "verified_consumed_chunks": verified_chunks,
        "limitations": protocol.document["claim_limits"],
    }

    results_path = output / "benchmark-results.json"
    predictions_path = output / "predictions.csv"
    inventory_path = output / "frame-inventory.json.gz"
    yield_path = output / "acquisition-yield.png"
    paired_path = output / "paired-future-odd-prediction.png"
    anchors_path = output / "anchor-residuals.png"
    _atomic_write(results_path, _json_bytes(result))
    _write_predictions(predictions_path, prediction_documents)
    _write_frame_inventory(inventory_path, inventory)
    _render_yield(yield_path, yield_summary)
    _render_paired(paired_path, prediction_documents, paired)
    _render_anchor_residuals(anchors_path, prediction_documents)
    artifacts = {
        path.name: {"bytes": path.stat().st_size, "sha256": _sha256(path)}
        for path in (
            results_path,
            predictions_path,
            inventory_path,
            yield_path,
            paired_path,
            anchors_path,
        )
    }
    _atomic_write(
        output / "artifact-manifest.json",
        _json_bytes({"schema": ARTIFACT_SCHEMA, "artifacts": artifacts}),
    )
    return result


def main() -> None:
    arguments = _arguments()
    result = run_benchmark(arguments.protocol, arguments.capture_root, arguments.output_root)
    print(json.dumps(result["interpretation"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
