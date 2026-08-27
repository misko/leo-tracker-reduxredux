"""Deterministic figures for a response-free candidate-observability atlas.

Rendering is downstream of a digest-closed :class:`CandidateObservabilityResult`.
The closest-pair panel selects curves only by response-free projected distance.
Optional catalogue-number annotations are applied after every plotted series is
fixed and therefore cannot change the scientific inventory.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import matplotlib

matplotlib.use("Agg", force=True)

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.axes import Axes  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from leo.analysis.catalogue_observability import (  # noqa: E402
    CandidateObservabilityResult,
    PairDistanceCurve,
    candidate_observability_result_payload,
)
from leo.contracts.digests import Sha256Digest, canonical_digest, sha256_digest  # noqa: E402

_SAFE_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
_REQUIRED_HISTORIES_MS = (20.0, 125.0, 500.0)
_FIGURE_VERSION: Literal["catalogue-observability-figures-v1"] = (
    "catalogue-observability-figures-v1"
)
_HISTORY_COLORS = {
    20.0: "#0072B2",
    125.0: "#009E73",
    500.0: "#D55E00",
}
_FIELD_COLORS = {
    -500: "#7B3294",
    500: "#008837",
}
_RC: Any = {
    "axes.grid": True,
    "axes.titlesize": 11,
    "axes.labelsize": 9,
    "figure.facecolor": "white",
    "font.family": "DejaVu Sans",
    "font.size": 8,
    "grid.alpha": 0.22,
    "legend.fontsize": 7,
    "lines.linewidth": 1.35,
    "path.simplify": False,
    "savefig.facecolor": "white",
}

FigureKind = Literal[
    "candidate-count",
    "closest-pairs",
    "tau-envelope",
    "wrong-epoch-alternatives",
]


class CatalogueObservabilityFigureError(ValueError):
    """A result, rendering control, or exclusive output path is invalid."""


@dataclass(frozen=True, slots=True)
class CatalogueObservabilityFigureReceipt:
    figure_kind: FigureKind
    file_name: str
    sha256: Sha256Digest
    byte_size: int
    source_result_digest: Sha256Digest
    plotted_series_ids: tuple[str, ...]
    annotated_catalog_numbers: tuple[int, ...]
    content_digest: Sha256Digest
    provisional: Literal[True] = True
    response_free_series_selection: Literal[True] = True
    annotations_select_series: Literal[False] = False
    identity_claimed: Literal[False] = False
    algorithm_version: Literal["catalogue-observability-figures-v1"] = _FIGURE_VERSION


def render_catalogue_observability_figures(
    result: CandidateObservabilityResult,
    *,
    output_directory: Path,
    arc_label: str,
    annotation_catalog_numbers: tuple[int, ...] = (),
    maximum_pair_curves: int = 12,
) -> tuple[
    CatalogueObservabilityFigureReceipt,
    CatalogueObservabilityFigureReceipt,
    CatalogueObservabilityFigureReceipt,
    CatalogueObservabilityFigureReceipt,
]:
    """Render the four fixed C1 panels and return digest-closed receipts."""

    _validate_result(result)
    if not isinstance(arc_label, str) or _SAFE_LABEL.fullmatch(arc_label) is None:
        raise CatalogueObservabilityFigureError("arc label is not a safe bounded file label")
    if (
        not isinstance(maximum_pair_curves, int)
        or isinstance(maximum_pair_curves, bool)
        or not 1 <= maximum_pair_curves <= 64
    ):
        raise CatalogueObservabilityFigureError("maximum pair curves must be from 1 through 64")
    annotations = _canonical_annotations(annotation_catalog_numbers)
    destination = output_directory.resolve()
    try:
        destination.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise CatalogueObservabilityFigureError("figure output directory is unavailable") from error
    if not destination.is_dir():
        raise CatalogueObservabilityFigureError("figure output path is not a directory")

    with plt.rc_context(_RC):
        count_figure, count_series = _candidate_count_figure(result, arc_label)
        pair_figure, pair_series, pair_annotations = _closest_pair_figure(
            result,
            arc_label,
            annotations,
            maximum_pair_curves,
        )
        tau_figure, tau_series, tau_annotations = _tau_envelope_figure(
            result,
            arc_label,
            annotations,
        )
        wrong_figure, wrong_series, wrong_annotations = _wrong_epoch_figure(
            result,
            arc_label,
            annotations,
        )
        return (
            _publish_figure(
                count_figure,
                destination,
                arc_label,
                "candidate-count",
                count_series,
                (),
                result.content_digest,
            ),
            _publish_figure(
                pair_figure,
                destination,
                arc_label,
                "closest-pairs",
                pair_series,
                pair_annotations,
                result.content_digest,
            ),
            _publish_figure(
                tau_figure,
                destination,
                arc_label,
                "tau-envelope",
                tau_series,
                tau_annotations,
                result.content_digest,
            ),
            _publish_figure(
                wrong_figure,
                destination,
                arc_label,
                "wrong-epoch-alternatives",
                wrong_series,
                wrong_annotations,
                result.content_digest,
            ),
        )


def _validate_result(result: CandidateObservabilityResult) -> None:
    try:
        candidate_observability_result_payload(result)
    except (AttributeError, TypeError, ValueError) as error:
        raise CatalogueObservabilityFigureError(
            "candidate-observability result is invalid or digest-open"
        ) from error
    if (
        result.measured_response_accessed is not False
        or result.candidate_universe_selected_from_response is not False
        or result.identity_claimed is not False
        or result.numerical_thresholds_frozen is not False
        or result.wrong_epoch_is_gate is not False
    ):
        raise CatalogueObservabilityFigureError("result exceeds the provisional C1 claim boundary")
    if len(result.nuisance_geometries) != 2:
        raise CatalogueObservabilityFigureError("result must contain both declared nuisance lanes")
    offset_lane, drift_lane = result.nuisance_geometries
    if offset_lane.nuisance_model != "offset-only-v1":
        raise CatalogueObservabilityFigureError("first nuisance lane is not offset-only")
    if drift_lane.nuisance_model != "offset-plus-ridge-drift-v1":
        raise CatalogueObservabilityFigureError(
            "second nuisance lane is not offset plus ridge drift"
        )
    histories = tuple(
        tuple(item.history_ms for item in lane.floor_overlays) for lane in (offset_lane, drift_lane)
    )
    if histories != (_REQUIRED_HISTORIES_MS, _REQUIRED_HISTORIES_MS):
        raise CatalogueObservabilityFigureError(
            "both C1 nuisance lanes require exact 20/125/500 ms overlays"
        )
    if any(
        item.calibrated is not False
        for lane in (offset_lane, drift_lane)
        for item in lane.floor_overlays
    ):
        raise CatalogueObservabilityFigureError("C1 figure floors must remain uncalibrated")
    count = len(result.prefix_duration_s)
    if count < 2 or len(result.prefix_end_utc_ns) != count:
        raise CatalogueObservabilityFigureError("result prefix inventory is incomplete")
    durations = np.asarray(result.prefix_duration_s, dtype=np.float64)
    if (
        not np.all(np.isfinite(durations))
        or durations[0] != 0.0
        or np.any(np.diff(durations) <= 0.0)
    ):
        raise CatalogueObservabilityFigureError("prefix durations are not causal and ordered")
    for geometry in result.nuisance_geometries:
        if len(geometry.prefix_summaries) != count:
            raise CatalogueObservabilityFigureError("nuisance prefix inventory is incomplete")
        for curve in geometry.close_pair_curves:
            if (
                curve.selected_response_free is not True
                or len(curve.projected_rms_hz_by_prefix) != count
            ):
                raise CatalogueObservabilityFigureError("close-pair curve is invalid")
    if len(result.tau_prefix_summaries) != count:
        raise CatalogueObservabilityFigureError("tau prefix inventory is incomplete")
    if tuple(item.field_delta_s for item in result.wrong_field_observability) != (-500, 500):
        raise CatalogueObservabilityFigureError("wrong-epoch inventory is not -500/+500")
    if any(
        item.observe_only is not True
        or item.p_value_computed is not False
        or item.identity_gate_applied is not False
        or len(item.prefix_summaries) != count
        for item in result.wrong_field_observability
    ):
        raise CatalogueObservabilityFigureError("wrong-epoch result exceeds observe-only scope")


def _candidate_count_figure(
    result: CandidateObservabilityResult,
    arc_label: str,
) -> tuple[Figure, tuple[str, ...]]:
    durations = np.asarray(result.prefix_duration_s)
    figure, axis = plt.subplots(figsize=(9.2, 5.4), constrained_layout=True)
    series: list[str] = []
    drift_lane = result.nuisance_geometries[1]
    for overlay in drift_lane.floor_overlays:
        color = _HISTORY_COLORS[overlay.history_ms]
        local = [item.median_local_candidate_count for item in overlay.prefix_summaries]
        soft = [item.median_soft_effective_candidate_count for item in overlay.prefix_summaries]
        label = _history_label(overlay.history_ms)
        axis.plot(durations, local, color=color, label=f"{label} local median")
        axis.plot(
            durations,
            soft,
            color=color,
            linestyle="--",
            label=f"{label} soft median",
        )
        series.extend((f"history-{label}-local", f"history-{label}-soft"))
    axis.set_yscale("log")
    axis.set_ylim(bottom=0.9)
    axis.set_xlabel("Causal prefix duration (s)")
    axis.set_ylabel("Tau=0 drift-aware local / soft-effective candidates")
    axis.set_title(f"{arc_label}: provisional tau=0 drift-aware ambiguity versus duration")
    axis.legend(ncol=2)
    _claim_footer(axis)
    return figure, tuple(series)


def _closest_pair_figure(
    result: CandidateObservabilityResult,
    arc_label: str,
    annotations: tuple[int, ...],
    maximum_pair_curves: int,
) -> tuple[Figure, tuple[str, ...], tuple[int, ...]]:
    durations = np.asarray(result.prefix_duration_s)
    curves = tuple(
        sorted(
            result.nuisance_geometries[1].close_pair_curves,
            key=lambda item: (
                item.projected_rms_hz_by_prefix[-1],
                item.left_catalog_number,
                item.right_catalog_number,
            ),
        )[:maximum_pair_curves]
    )
    if not curves:
        raise CatalogueObservabilityFigureError("closest-pair figure has no response-free curve")
    figure, axis = plt.subplots(figsize=(9.4, 5.6), constrained_layout=True)
    palette = plt.get_cmap("tab20")
    plotted: list[str] = []
    annotated: set[int] = set()
    for index, curve in enumerate(curves):
        color = palette(index % 20)
        pair_id = _pair_id(curve)
        values = np.asarray(curve.projected_rms_hz_by_prefix)
        axis.plot(durations, values, color=color, label=pair_id)
        plotted.append(pair_id)
        endpoints = tuple(
            item
            for item in (curve.left_catalog_number, curve.right_catalog_number)
            if item in annotations
        )
        if endpoints:
            annotated.update(endpoints)
            axis.annotate(
                "/".join(str(item) for item in endpoints),
                xy=(durations[-1], values[-1]),
                xytext=(4, 3 + 5 * (index % 3)),
                textcoords="offset points",
                fontsize=6,
                color=color,
            )
    for overlay in result.nuisance_geometries[1].floor_overlays:
        axis.axhline(
            overlay.floor_hz,
            color=_HISTORY_COLORS[overlay.history_ms],
            alpha=0.38,
            linewidth=0.8,
            linestyle=":",
        )
    axis.set_xlabel("Causal prefix duration (s)")
    axis.set_ylabel("Tau=0 offset-plus-ridge-drift pair separation RMS (Hz)")
    axis.set_title(f"{arc_label}: closest tau=0 drift-aware response-free catalogue pairs")
    axis.legend(ncol=2)
    _claim_footer(axis)
    return figure, tuple(plotted), tuple(sorted(annotated))


def _tau_envelope_figure(
    result: CandidateObservabilityResult,
    arc_label: str,
    annotations: tuple[int, ...],
) -> tuple[Figure, tuple[str, ...], tuple[int, ...]]:
    durations = np.asarray(result.prefix_duration_s)
    minimum = np.asarray(
        [item.minimum_candidate_max_tau_rms_hz for item in result.tau_prefix_summaries]
    )
    median = np.asarray(
        [item.median_candidate_max_tau_rms_hz for item in result.tau_prefix_summaries]
    )
    maximum = np.asarray(
        [item.maximum_candidate_max_tau_rms_hz for item in result.tau_prefix_summaries]
    )
    figure, axis = plt.subplots(figsize=(9.2, 5.4), constrained_layout=True)
    axis.fill_between(
        durations,
        minimum,
        maximum,
        color="#56B4E9",
        alpha=0.24,
        label="candidate min–max envelope",
    )
    axis.plot(durations, median, color="#0072B2", label="candidate median")
    axis.plot(durations, minimum, color="#56B4E9", alpha=0.8, linewidth=0.8)
    axis.plot(durations, maximum, color="#56B4E9", alpha=0.8, linewidth=0.8)
    by_number = {item.catalog_number: item for item in result.tau_sensitivity}
    annotated: list[int] = []
    for annotation_index, catalog_number in enumerate(annotations):
        candidate = by_number.get(catalog_number)
        if candidate is None:
            continue
        final_values = [
            state.nuisance_sensitivities[0].final_projected_rms_hz
            for state in candidate.states_relative_to_tau_zero
        ]
        if not final_values:
            continue
        value = max(final_values)
        axis.scatter((durations[-1],), (value,), color="#000000", s=12, zorder=4)
        axis.annotate(
            str(catalog_number),
            xy=(durations[-1], value),
            xytext=(5, 4 + 6 * (annotation_index % 3)),
            textcoords="offset points",
            fontsize=6,
        )
        annotated.append(catalog_number)
    axis.set_xlabel("Causal prefix duration (s)")
    axis.set_ylabel("Max same-NORAD offset-only tau separation RMS (Hz)")
    axis.set_title(f"{arc_label}: bounded [-5,+5] s tau sensitivity envelope")
    axis.legend()
    _claim_footer(axis)
    return (
        figure,
        ("tau-candidate-minimum", "tau-candidate-median", "tau-candidate-maximum"),
        tuple(annotated),
    )


def _wrong_epoch_figure(
    result: CandidateObservabilityResult,
    arc_label: str,
    annotations: tuple[int, ...],
) -> tuple[Figure, tuple[str, ...], tuple[int, ...]]:
    durations = np.asarray(result.prefix_duration_s)
    figure, axis = plt.subplots(figsize=(9.2, 5.4), constrained_layout=True)
    plotted: list[str] = []
    annotated: set[int] = set()
    for field in result.wrong_field_observability:
        color = _FIELD_COLORS[field.field_delta_s]
        minimum = np.asarray([item.minimum_nearest_any_rms_hz for item in field.prefix_summaries])
        median = np.asarray([item.median_nearest_any_rms_hz for item in field.prefix_summaries])
        maximum = np.asarray([item.maximum_nearest_any_rms_hz for item in field.prefix_summaries])
        label = f"delta {field.field_delta_s:+d} s, tau=0"
        axis.fill_between(durations, minimum, maximum, color=color, alpha=0.16)
        axis.plot(durations, median, color=color, label=f"{label} candidate median")
        plotted.extend(
            (
                f"{field.field_delta_s:+d}-minimum",
                f"{field.field_delta_s:+d}-median",
                f"{field.field_delta_s:+d}-maximum",
            )
        )
        by_number = {
            item.true_field_catalog_number: item for item in field.final_candidate_alternatives
        }
        for annotation_index, catalog_number in enumerate(annotations):
            alternative = by_number.get(catalog_number)
            if alternative is None:
                continue
            value = alternative.nearest_any_final_rms_hz
            axis.scatter((durations[-1],), (value,), color=color, s=12, zorder=4)
            axis.annotate(
                f"{catalog_number} ({field.field_delta_s:+d})",
                xy=(durations[-1], value),
                xytext=(5, 4 + 6 * (annotation_index % 3)),
                textcoords="offset points",
                fontsize=6,
                color=color,
            )
            annotated.add(catalog_number)
    axis.set_xlabel("Causal prefix duration (s)")
    axis.set_ylabel("Nearest full-catalogue alternative RMS (Hz)")
    axis.set_title(f"{arc_label}: fixed-tau wrong-epoch catalogue specificity (observe only)")
    axis.legend()
    _claim_footer(axis)
    return figure, tuple(plotted), tuple(sorted(annotated))


def _publish_figure(
    figure: Figure,
    directory: Path,
    arc_label: str,
    kind: FigureKind,
    plotted_series_ids: tuple[str, ...],
    annotated_catalog_numbers: tuple[int, ...],
    source_result_digest: Sha256Digest,
) -> CatalogueObservabilityFigureReceipt:
    file_name = f"{arc_label}-{kind}.png"
    path = directory / file_name
    if path.exists():
        plt.close(figure)
        raise CatalogueObservabilityFigureError(
            f"exclusive figure output already exists: {file_name}"
        )
    buffer = io.BytesIO()
    try:
        figure.savefig(
            buffer,
            format="png",
            dpi=160,
            metadata={"Software": _FIGURE_VERSION},
        )
    finally:
        plt.close(figure)
    payload = buffer.getvalue()
    try:
        with path.open("xb") as output:
            output.write(payload)
    except OSError as error:
        raise CatalogueObservabilityFigureError(f"could not publish figure: {file_name}") from error
    receipt_body = {
        "figure_kind": kind,
        "file_name": file_name,
        "sha256": sha256_digest(payload),
        "byte_size": len(payload),
        "source_result_digest": source_result_digest,
        "plotted_series_ids": plotted_series_ids,
        "annotated_catalog_numbers": annotated_catalog_numbers,
        "provisional": True,
        "response_free_series_selection": True,
        "annotations_select_series": False,
        "identity_claimed": False,
        "algorithm_version": _FIGURE_VERSION,
    }
    return CatalogueObservabilityFigureReceipt(
        figure_kind=kind,
        file_name=file_name,
        sha256=sha256_digest(payload),
        byte_size=len(payload),
        source_result_digest=source_result_digest,
        plotted_series_ids=plotted_series_ids,
        annotated_catalog_numbers=annotated_catalog_numbers,
        content_digest=canonical_digest(receipt_body),
    )


def _canonical_annotations(values: tuple[int, ...]) -> tuple[int, ...]:
    if any(not isinstance(item, int) or isinstance(item, bool) or item <= 0 for item in values):
        raise CatalogueObservabilityFigureError(
            "annotation catalogue numbers must be positive integers"
        )
    return tuple(sorted(set(values)))


def _pair_id(curve: PairDistanceCurve) -> str:
    return f"NORAD {curve.left_catalog_number}–{curve.right_catalog_number}"


def _history_label(history_ms: float) -> str:
    return str(int(history_ms)) if history_ms.is_integer() else f"{history_ms:g}"


def _claim_footer(axis: Axes) -> None:
    axis.text(
        0.0,
        -0.18,
        "Response-free homoscedastic RMS geometry; floors are uncalibrated; no identity claim.",
        transform=axis.transAxes,
        fontsize=7,
        color="#555555",
    )
