"""Render the bounded full-dwell GLRT-64 trajectory feedback artifact."""

from __future__ import annotations

import io
from typing import cast

import matplotlib
import numpy as np
from pydantic import JsonValue

from leo.pipeline import (
    AnalysisContext,
    IqReader,
    OutputSink,
    ProductReader,
    StageOutcome,
    StageResult,
    StageSpec,
)

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402


class Glrt64TrajectoryPresentationAnalyzer:
    """Publish one full-duration PNG from the scientific feedback products."""

    def __init__(self, spec: StageSpec) -> None:
        if len(spec.output_products) != 1 or spec.output_products[0].media_type != "image/png":
            raise ValueError("GLRT-64 presentation stage must publish exactly one PNG")
        self.spec = spec

    def analyze(
        self,
        context: AnalysisContext,
        _iq: IqReader,
        products: ProductReader,
        outputs: OutputSink,
    ) -> StageResult:
        documents = tuple(
            products.read_json(requirement) for requirement in self.spec.input_products
        )
        if any(document is None for document in documents):
            raise ValueError("GLRT-64 presentation inputs are incomplete")
        detections, _bank, redetection, table = cast(
            tuple[dict[str, JsonValue], ...], documents
        )
        payload = render_glrt64_trajectory_png(
            context.run_id,
            detections,
            redetection,
            table,
        )
        published = outputs.publish_bytes(self.spec.output_products[0], payload)
        rows = table.get("trajectories", [])
        return StageResult(
            outcome=StageOutcome.COMPLETE,
            products=(published,),
            summary={
                "glrt64_trajectory_count": len(rows) if isinstance(rows, list) else 0,
                "candidate_only": True,
            },
            message="full-dwell GLRT-64 baseline, correction, and polynomial CFO trajectories",
        )


def render_glrt64_trajectory_png(
    run_id: str,
    detections: dict[str, JsonValue],
    redetection: dict[str, JsonValue],
    table: dict[str, JsonValue],
) -> bytes:
    """Render the one canonical full-time GLRT-64 diagnostic PNG."""

    initial = _initial_glrt64(detections)
    corrected = _corrected_glrt64(redetection)
    trajectories = _trajectory_rows(table)
    duration = max(
        [time_s for time_s, *_ in initial]
        + [time_s for _, time_s, _ in corrected]
        + [_number(row, "end_s") for row in trajectories]
        + [1.0]
    )
    figure, axes = plt.subplots(2, 1, figsize=(16, 9), sharex=True, constrained_layout=True)
    response_axis, cfo_axis = axes
    if initial:
        initial_array = np.asarray(initial, dtype=float)
        response_axis.scatter(
            initial_array[:, 0],
            initial_array[:, 1],
            s=9,
            color="#8b95a5",
            alpha=0.5,
            label="initial GLRT-64 exact − control",
        )
        cfo_axis.scatter(
            initial_array[:, 0],
            initial_array[:, 2] / 1_000,
            s=8,
            color="#8b95a5",
            alpha=0.4,
            label="initial GLRT-64 CFO",
        )
    family_colors = plt.get_cmap("tab10")
    for index, (family_id, points) in enumerate(_by_family(corrected).items()):
        values = np.asarray(points, dtype=float)
        response_axis.plot(
            values[:, 0],
            values[:, 1],
            linewidth=1.2,
            color=family_colors(index % 10),
            label=f"corrected {family_id.removeprefix('sha256:')[:8]}",
        )
    model_colors = {"linear": "#277da1", "quadratic": "#f8961e", "cubic": "#9b5de5"}
    labeled: set[str] = set()
    for row in trajectories:
        if not bool(row["fit_matches_well"]):
            continue
        model = str(row["model"])
        start = _number(row, "start_s")
        end = _number(row, "end_s")
        reference = _number(row, "reference_time_s")
        coefficients = np.asarray(_number_list(row, "coefficients_hz"), dtype=float)
        times = np.linspace(start, end, max(40, round((end - start) * 20)))
        frequency = np.polyval(coefficients, times - reference) / 1_000
        selected = bool(row["selected_for_correction"])
        label = f"{model} fit" if model not in labeled else None
        labeled.add(model)
        cfo_axis.plot(
            times,
            frequency,
            color=model_colors[model],
            linewidth=2.4 if selected else 1.0,
            alpha=0.95 if selected else 0.45,
            label=label,
        )
        if selected:
            cfo_axis.text(
                (start + end) / 2,
                float(np.polyval(coefficients, (start + end) / 2 - reference) / 1_000),
                f"{model}\nRMS {_number(row, 'residual_rms_hz'):.0f} Hz",
                fontsize=7,
                color=model_colors[model],
                ha="center",
                va="bottom",
            )
    response_axis.axhline(0, color="black", linewidth=0.6, alpha=0.5)
    response_axis.set_ylabel("GLRT-64 exact − rolled control")
    response_axis.set_title("Initial and trajectory-corrected GLRT-64 response", loc="left")
    cfo_axis.set_ylabel("baseband CFO (kHz)")
    cfo_axis.set_xlabel("recording time (s)")
    cfo_axis.set_title(
        "Well-matched GLRT-64 CFO trajectories · thick lines selected for correction",
        loc="left",
    )
    for axis in axes:
        axis.set_xlim(0, duration)
        axis.grid(alpha=0.16)
        handles, labels = axis.get_legend_handles_labels()
        if handles:
            axis.legend(handles, labels, loc="best", fontsize=8, ncols=2)
    figure.suptitle(
        f"Standard GLRT-64 trajectory feedback · run {run_id}\n"
        "candidate-only · linear / quadratic / cubic iterative fits",
        fontweight="bold",
    )
    target = io.BytesIO()
    figure.savefig(
        target,
        format="png",
        dpi=160,
        metadata={"Software": "leo-tracker", "Creation Time": None},
    )
    plt.close(figure)
    return target.getvalue()


def _initial_glrt64(document: dict[str, JsonValue]) -> list[tuple[float, float, float]]:
    result = []
    values = document.get("detections", [])
    if not isinstance(values, list):
        raise ValueError("pilot detection document has invalid detections")
    for detection in values:
        if not isinstance(detection, dict):
            continue
        scores = detection.get("scores", [])
        if not isinstance(scores, list):
            continue
        for score in scores:
            if isinstance(score, dict) and score.get("method") == "glrt64":
                result.append(
                    (
                        float(cast(float, detection["time_s"])),
                        float(cast(float, score["margin"])),
                        float(cast(float, score["tracking_cfo_hz"])),
                    )
                )
    return result


def _corrected_glrt64(document: dict[str, JsonValue]) -> list[tuple[str, float, float]]:
    result = []
    values = document.get("results", [])
    if not isinstance(values, list):
        raise ValueError("trajectory redetection document has invalid results")
    for item in values:
        if isinstance(item, dict) and item.get("detector_method") == "glrt64":
            result.append(
                (
                    str(item["family_id"]),
                    float(cast(float, item["time_s"])),
                    float(cast(float, item["corrected_margin"])),
                )
            )
    return result


def _trajectory_rows(document: dict[str, JsonValue]) -> list[dict[str, JsonValue]]:
    values = document.get("trajectories", [])
    if not isinstance(values, list) or any(not isinstance(item, dict) for item in values):
        raise ValueError("GLRT-64 trajectory table is invalid")
    return cast(list[dict[str, JsonValue]], values)


def _by_family(
    corrected: list[tuple[str, float, float]],
) -> dict[str, list[tuple[float, float]]]:
    result: dict[str, list[tuple[float, float]]] = {}
    for family_id, time_s, margin in corrected:
        result.setdefault(family_id, []).append((time_s, margin))
    for points in result.values():
        points.sort()
    return result


def _number(document: dict[str, JsonValue], key: str) -> float:
    value = document.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric")
    return float(value)


def _number_list(document: dict[str, JsonValue], key: str) -> list[float]:
    values = document.get(key)
    if not isinstance(values, list):
        raise ValueError(f"{key} must be a numeric list")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
        raise ValueError(f"{key} must be a numeric list")
    return [float(value) for value in cast(list[int | float], values)]
