#!/usr/bin/env python3
"""Audit five additional dwells with sealed current-pipeline Standard products.

The tool refuses unsealed, incomplete, mismatched, or duplicate-release inputs.  For
each explicitly named run it derives the reversible receiver-path scope identities,
selects the strongest supported degree-one trajectory without looking at phase quality,
returns to digest-verified raw IQ, and audits one complete 80 ms frame lattice.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from report_subsecond_pilot_structure import (
    _audit_dwell,
    _frequency_mode_metrics,
    _local_rate_metrics,
    _select_carrier_and_anchor,
    _state_period_metrics,
)

from leo.analysis.starlink import StarlinkEdge
from leo.pipeline.contracts import StageOutcome
from leo.pipeline.scopes import ScopeIdentityV1
from leo.storage import PinnedLocalRoot, RecordingStore

DEFAULT_INPUTS = Path("reports/figures/2026_08_23_additional_subsecond_pilot_dwells/inputs.json")
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_23_additional_subsecond_pilot_dwells")
BLUE = "#2678a8"
GREEN = "#4f9b66"
AMBER = "#d28a29"
RED = "#c44e52"
INK = "#193549"
GRAY = "#728694"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--inputs", type=Path, default=DEFAULT_INPUTS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--interval-ms", type=float, default=80.0)
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _validated_inputs(path: Path) -> tuple[str, tuple[dict[str, str], ...]]:
    document = _load_json(path)
    if document.get("schema") != "org.leo.research.additional-subsecond-pilot-inputs/v1":
        raise ValueError("unsupported additional-dwell input schema")
    release = document.get("pipeline_release_id")
    if not isinstance(release, str) or len(release) != 40:
        raise ValueError("inputs require one exact 40-character pipeline release")
    rows = document.get("dwells")
    if not isinstance(rows, list) or len(rows) != 5:
        raise ValueError("additional-dwell audit requires exactly five dwells")
    normalized = tuple(
        {"session_id": str(item["session_id"]), "run_id": str(item["run_id"])} for item in rows
    )
    sessions = [item["session_id"] for item in normalized]
    runs = [item["run_id"] for item in normalized]
    if len(set(sessions)) != 5 or len(set(runs)) != 5:
        raise ValueError("additional-dwell inputs contain duplicate sessions or runs")
    return release, normalized


def _validated_run_root(
    bulk_root: Path,
    *,
    session_id: str,
    run_id: str,
    release: str,
) -> tuple[Path, dict[str, Any], str]:
    root = bulk_root / "analysis" / session_id / run_id
    manifest_path = root / "manifest.json"
    document = _load_json(manifest_path)
    if document.get("session_id") != session_id:
        raise ValueError(f"analysis manifest session mismatch: {run_id}")
    if document.get("run_id") != run_id:
        raise ValueError(f"analysis manifest run mismatch: {run_id}")
    if document.get("pipeline_lane") != "standard":
        raise ValueError(f"analysis run is not Standard: {run_id}")
    if document.get("pipeline_release_id") != release:
        raise ValueError(f"analysis run is not from the declared release: {run_id}")
    jobs = document.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        raise ValueError(f"sealed analysis manifest has no jobs: {run_id}")
    successful_outcomes = {outcome.value for outcome in StageOutcome}
    invalid_outcomes = [
        item.get("outcome") for item in jobs if item.get("outcome") not in successful_outcomes
    ]
    if invalid_outcomes:
        raise ValueError(
            f"analysis run contains a non-successful job outcome {invalid_outcomes!r}: {run_id}"
        )
    return root, document, _digest(manifest_path)


def _edge_for_stream(tags: tuple[str, ...], stream_id: str) -> StarlinkEdge:
    prefix = f"tuning:{stream_id}:"
    matches = [item for item in tags if item.startswith(prefix)]
    if len(matches) != 1:
        raise ValueError(f"recording does not declare one tuning tag for {stream_id}")
    try:
        return StarlinkEdge(matches[0].rsplit(":", maxsplit=1)[-1])
    except ValueError as error:
        raise ValueError(f"invalid Starlink edge in tuning tag: {matches[0]}") from error


def _analysis_choices(
    run_root: Path,
    *,
    session_id: str,
) -> list[tuple[float, int, int, str, int, Path]]:
    choices = []
    for stream_id in ("stream-0", "stream-1"):
        for receiver_id in (0, 1):
            scope = ScopeIdentityV1.receiver_path(
                session_id=session_id,
                stream_id=stream_id,
                receiver_id=receiver_id,
            ).canonical_digest
            analysis_root = run_root / "scientific" / "path-standard" / scope
            if not analysis_root.is_dir():
                continue
            try:
                _trajectory, anchor, scan = _select_carrier_and_anchor(analysis_root)
            except (FileNotFoundError, ValueError):
                continue
            choices.append(
                (
                    float(anchor["margin"]),
                    int(anchor["neighbor_count_200ms"]),
                    len(scan["detections"]),
                    stream_id,
                    receiver_id,
                    analysis_root,
                )
            )
    return choices


def _qualify(result: dict[str, Any]) -> None:
    result["binary_state"] = _state_period_metrics(result["frames"])
    result["frequency_modes"] = _frequency_mode_metrics(result["frames"])
    result["local_rate"] = _local_rate_metrics(result["frames"])
    local_rate = result["local_rate"]
    result["phase_rate_qualified"] = bool(
        local_rate["quality_fraction"] >= 0.75
        and local_rate["reconstructed_phase_residual_rms_rad"] is not None
        and local_rate["reconstructed_phase_residual_rms_rad"] <= 0.35
        and max(
            result["even_to_odd_heldout_phase_residual_rms_rad"],
            result["odd_to_even_heldout_phase_residual_rms_rad"],
        )
        <= 0.35
    )


def _summary(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": result["session_id"],
        "analysis_run_id": result["analysis_run_id"],
        "pipeline_release_id": result["pipeline_release_id"],
        "stream_id": result["stream_id"],
        "receiver_id": result["receiver_id"],
        "edge": result["edge"],
        "anchor_time_s": result["anchor"]["time_s"],
        "anchor_margin": result["anchor"]["margin"],
        "quality_frame_count": result["quality_frame_count"],
        "inferred_frame_count": result["inferred_frame_count"],
        "ordinary_phase_rms_rad": result["cubic_batch_phase_residual_rms_rad"],
        "pi_aware_phase_rms_rad": result["pi_ambiguity_batch_phase_residual_rms_rad"],
        "pi_aware_stack_efficiency": result["pi_ambiguity_batch_stack_efficiency"],
        "even_to_odd_heldout_rms_rad": result["even_to_odd_heldout_phase_residual_rms_rad"],
        "odd_to_even_heldout_rms_rad": result["odd_to_even_heldout_phase_residual_rms_rad"],
        "state_transition_fraction": result["binary_state"]["transition_fraction"],
        "pi_corrected_adjacent_cfo_rms_hz": result["frequency_modes"]["pi_corrected_rms_hz"],
        "frozen_rate_hz_s": result["local_rate"]["frozen_model_rate_hz_s"],
        "local_cfo_rate_hz_s": result["local_rate"]["within_frame_cfo_rate_hz_s"],
        "phase_supported_rate_hz_s": result["local_rate"]["phase_supported_rate_hz_s"],
        "phase_rate_qualified": result["phase_rate_qualified"],
    }


def _labels(results: list[dict[str, Any]]) -> list[str]:
    return [item["session_id"].split("-")[-1][:8] for item in results]


def _plot_summary(results: list[dict[str, Any]], output: Path) -> None:
    labels = _labels(results)
    x = np.arange(len(results))
    quality = np.asarray(
        [item["quality_frame_count"] / item["inferred_frame_count"] for item in results]
    )
    ordinary = np.asarray([item["cubic_batch_phase_residual_rms_rad"] for item in results])
    pi_aware = np.asarray([item["pi_ambiguity_batch_phase_residual_rms_rad"] for item in results])
    even_odd = np.asarray([item["even_to_odd_heldout_phase_residual_rms_rad"] for item in results])
    odd_even = np.asarray([item["odd_to_even_heldout_phase_residual_rms_rad"] for item in results])
    frozen = np.asarray([item["local_rate"]["frozen_model_rate_hz_s"] for item in results])
    local = np.asarray([item["local_rate"]["within_frame_cfo_rate_hz_s"] for item in results])
    phase = np.asarray(
        [
            np.nan
            if item["local_rate"]["phase_supported_rate_hz_s"] is None
            else item["local_rate"]["phase_supported_rate_hz_s"]
            for item in results
        ]
    )
    with plt.rc_context({"font.size": 10, "axes.titlesize": 12, "figure.dpi": 180}):
        figure, axes = plt.subplots(2, 2, figsize=(14.2, 9.0), constrained_layout=True)
        axes[0, 0].bar(x, quality, color=np.where(quality >= 0.75, GREEN, GRAY))
        axes[0, 0].axhline(0.75, color=RED, linestyle="--", label="qualification gate")
        axes[0, 0].set_ylim(0, 1.05)
        axes[0, 0].set_ylabel("quality fraction of 60-frame lattice")
        axes[0, 0].set_title("A · Raw-lattice pilot availability", loc="left", fontweight="bold")
        axes[0, 0].legend(fontsize=8.5)

        axes[0, 1].bar(x - 0.18, ordinary, width=0.36, color=GRAY, label="ordinary phase")
        axes[0, 1].bar(x + 0.18, pi_aware, width=0.36, color=GREEN, label="π-aware phase")
        axes[0, 1].axhline(0.35, color=RED, linestyle="--", label="phase gate")
        axes[0, 1].set_ylabel("batch phase residual RMS (rad)")
        axes[0, 1].set_title(
            "B · Binary-π modeling helps, but does not guarantee lock",
            loc="left",
            fontweight="bold",
        )
        axes[0, 1].legend(fontsize=8.5)

        axes[1, 0].plot(x, even_odd, marker="o", color=BLUE, label="even pilots → odd")
        axes[1, 0].plot(x, odd_even, marker="s", color=AMBER, label="odd pilots → even")
        axes[1, 0].axhline(0.35, color=RED, linestyle="--", label="held-out gate")
        axes[1, 0].set_ylabel("held-out phase residual RMS (rad)")
        axes[1, 0].set_title(
            "C · Bidirectional held-out prediction is the decisive gate",
            loc="left",
            fontweight="bold",
        )
        axes[1, 0].legend(fontsize=8.5)

        axes[1, 1].plot(x, frozen / 1_000, marker="o", color=INK, label="frozen rate")
        axes[1, 1].plot(x, local / 1_000, marker="o", color=BLUE, label="80 ms CFO rate")
        axes[1, 1].plot(
            x,
            phase / 1_000,
            marker="x",
            linestyle="none",
            color=GREEN,
            label="π-aware phase-supported rate",
        )
        axes[1, 1].set_ylabel("CFO rate (kHz/s)")
        axes[1, 1].set_title(
            "D · Short-interval rate is not the multi-second line",
            loc="left",
            fontweight="bold",
        )
        axes[1, 1].legend(fontsize=8.5)

        for axis in axes.flat:
            axis.set_xticks(x, labels, rotation=25, ha="right")
            axis.grid(True, axis="y", alpha=0.3)
        figure.suptitle(
            "Five additional dwells · exact current-pipeline reprocessing",
            fontsize=15,
            fontweight="bold",
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output, bbox_inches="tight")
        plt.close(figure)


def _quality_mask(frames: list[dict[str, Any]]) -> np.ndarray:
    return np.asarray(
        [item["exact_coherence"] >= 0.02 and item["coherence_margin"] >= 0 for item in frames]
    )


def _plot_detail(results: list[dict[str, Any]], output: Path) -> None:
    with plt.rc_context({"font.size": 9, "axes.titlesize": 10, "figure.dpi": 180}):
        figure, axes = plt.subplots(5, 2, figsize=(14.2, 15.0), constrained_layout=True)
        for row, result in enumerate(results):
            frames = result["frames"]
            times = np.asarray([item["reference_time_s"] for item in frames])
            elapsed = (times - times[0]) * 1_000
            quality = _quality_mask(frames)
            measured = np.asarray([item["frequency_fit_cfo_hz"] for item in frames])
            model = np.asarray([item["model_cfo_hz"] for item in frames])
            residual = measured - model
            fit = (
                np.polyval(np.polyfit(elapsed[quality], residual[quality], 2), elapsed)
                if np.count_nonzero(quality) >= 3
                else np.full_like(elapsed, np.nan)
            )
            ordinary_phase = np.asarray([item["cubic_batch_phase_residual_rad"] for item in frames])
            pi_phase = np.asarray(
                [item["pi_ambiguity_batch_phase_residual_rad"] for item in frames]
            )
            label = _labels([result])[0]

            axes[row, 0].scatter(elapsed[~quality], residual[~quality], s=15, color=GRAY, alpha=0.4)
            axes[row, 0].scatter(elapsed[quality], residual[quality], s=17, color=BLUE)
            axes[row, 0].plot(elapsed, fit, color=AMBER, linewidth=1.2)
            axes[row, 0].set_ylabel("CFO residual (Hz)")
            axes[row, 0].set_title(
                f"{label} · {result['stream_id']}/RX{result['receiver_id']} · {result['edge']}",
                loc="left",
                fontweight="bold",
            )

            axes[row, 1].scatter(
                elapsed[quality],
                ordinary_phase[quality],
                s=14,
                color=GRAY,
                alpha=0.55,
                label="ordinary" if row == 0 else None,
            )
            axes[row, 1].plot(
                elapsed[quality],
                pi_phase[quality],
                marker="o",
                markersize=2.5,
                linewidth=0.8,
                color=GREEN,
                label="π-aware" if row == 0 else None,
            )
            axes[row, 1].axhline(0, color=INK, linewidth=0.7)
            axes[row, 1].axhline(0.35, color=RED, linewidth=0.7, linestyle="--")
            axes[row, 1].axhline(-0.35, color=RED, linewidth=0.7, linestyle="--")
            axes[row, 1].set_ylabel("batch phase residual (rad)")
            axes[row, 1].set_title(
                f"π-aware RMS {result['pi_ambiguity_batch_phase_residual_rms_rad']:.3f} rad",
                loc="left",
                fontweight="bold",
            )
            for axis in axes[row]:
                axis.grid(True, alpha=0.25)
                if row == len(results) - 1:
                    axis.set_xlabel("time from selected anchor (ms)")
        axes[0, 1].legend(fontsize=8.5)
        figure.suptitle(
            "Complete 80 ms raw-IQ lattice in each additional dwell",
            fontsize=15,
            fontweight="bold",
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output, bbox_inches="tight")
        plt.close(figure)


def _plot_binary_state(results: list[dict[str, Any]], output: Path) -> None:
    bits = np.asarray(
        [[int(frame["pi_ambiguity_state"]) for frame in item["frames"]] for item in results]
    )
    quality = np.asarray([_quality_mask(item["frames"]) for item in results])
    corrected_rms = np.asarray([item["frequency_modes"]["pi_corrected_rms_hz"] for item in results])
    transitions = np.asarray([item["binary_state"]["transition_fraction"] for item in results])
    labels = _labels(results)
    masked = np.ma.masked_where(~quality, bits)
    with plt.rc_context({"font.size": 10, "axes.titlesize": 12, "figure.dpi": 180}):
        figure, axes = plt.subplots(
            2,
            1,
            figsize=(14.2, 7.8),
            gridspec_kw={"height_ratios": (1.15, 1)},
            constrained_layout=True,
        )
        axes[0].imshow(masked, aspect="auto", interpolation="nearest", cmap="BrBG", vmin=0, vmax=1)
        axes[0].set_yticks(np.arange(5), labels)
        axes[0].set_xlabel("frame index at 750 frames/s")
        axes[0].set_ylabel("session suffix")
        axes[0].set_title(
            "A · Binary π state has no common cadence across the five dwells",
            loc="left",
            fontweight="bold",
        )
        axes[0].text(59.5, 4.8, "blank = pilot-quality failure", ha="right", va="bottom", color=INK)

        x = np.arange(5)
        axes[1].bar(x - 0.18, transitions, width=0.36, color=AMBER, label="state transitions")
        second = axes[1].twinx()
        second.bar(
            x + 0.18,
            corrected_rms,
            width=0.36,
            color=GREEN,
            label="π-corrected adjacent CFO RMS",
        )
        axes[1].set_xticks(x, labels)
        axes[1].set_ylim(0, 1)
        axes[1].set_ylabel("adjacent-frame state transition fraction")
        second.set_ylabel("π-corrected adjacent CFO RMS (Hz)")
        axes[1].set_title(
            "B · State cadence and corrected CFO quality are separate observables",
            loc="left",
            fontweight="bold",
        )
        handles_a, labels_a = axes[1].get_legend_handles_labels()
        handles_b, labels_b = second.get_legend_handles_labels()
        axes[1].legend(handles_a + handles_b, labels_a + labels_b, fontsize=8.5)
        axes[1].grid(True, axis="y", alpha=0.3)
        figure.suptitle(
            "Binary-π structure in five additional current-pipeline dwells",
            fontsize=15,
            fontweight="bold",
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output, bbox_inches="tight")
        plt.close(figure)


def main() -> int:
    args = _arguments()
    if not math.isfinite(args.interval_ms) or not 40 <= args.interval_ms <= 250:
        raise ValueError("interval-ms must be finite and between 40 and 250")
    release, requested = _validated_inputs(args.inputs)
    pinned = PinnedLocalRoot(args.bulk_root)
    store: RecordingStore | None = None
    results: list[dict[str, Any]] = []
    try:
        store = RecordingStore.open_pinned(pinned)
        for item in requested:
            run_root, manifest, manifest_digest = _validated_run_root(
                args.bulk_root,
                session_id=item["session_id"],
                run_id=item["run_id"],
                release=release,
            )
            choices = _analysis_choices(run_root, session_id=item["session_id"])
            if not choices:
                raise ValueError(f"no supported degree-one path in {item['run_id']}")
            _margin, _neighbors, _detections, stream_id, receiver_id, analysis_root = max(choices)
            bundle = store.inspect(item["session_id"])
            edge = _edge_for_stream(bundle.manifest.tags, stream_id)
            result = _audit_dwell(
                store,
                session_id=item["session_id"],
                stream_id=stream_id,
                receiver_id=receiver_id,
                edge=edge,
                analysis_root=analysis_root,
                interval_s=args.interval_ms / 1_000,
            )
            result.update(
                {
                    "analysis_run_id": item["run_id"],
                    "pipeline_release_id": release,
                    "analysis_manifest_digest": manifest_digest,
                    "analysis_input_manifest_digest": manifest["input_manifest_digest"],
                    "path_choice_count": len(choices),
                }
            )
            _qualify(result)
            results.append(result)
    finally:
        if store is not None:
            store.close()
    document = {
        "schema": "org.leo.research.additional-subsecond-pilot-results/v1",
        "candidate_only": True,
        "payload_decoded": False,
        "pipeline_release_id": release,
        "interval_ms": args.interval_ms,
        "dwell_count": len(results),
        "phase_rate_qualified_count": sum(item["phase_rate_qualified"] for item in results),
        "summaries": [_summary(item) for item in results],
        "results": results,
    }
    args.output_root.mkdir(parents=True, exist_ok=True)
    (args.output_root / "additional-dwell-results.json").write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _plot_summary(results, args.output_root / "additional-dwell-summary.png")
    _plot_detail(results, args.output_root / "additional-dwell-detail.png")
    _plot_binary_state(results, args.output_root / "additional-dwell-binary-state.png")
    print(
        json.dumps(
            {
                "dwell_count": len(results),
                "phase_rate_qualified_count": document["phase_rate_qualified_count"],
                "output_root": str(args.output_root),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
