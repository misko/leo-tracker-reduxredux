#!/usr/bin/env python3
"""Render four receiver-path GLRT64 feedback results on one recorded clock."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from leo.storage import PinnedLocalRoot, RecordingStore  # type: ignore[import-untyped]

DEFAULT_SESSION = "production-24h-20260819-01-trial-00000132"
DEFAULT_OUTPUT = Path(
    "artifacts/production-24h-20260819-01-trial-00000132-"
    "four-path-glrt64-trajectory-feedback.png"
)
PATHS = (("stream-0", 0), ("stream-0", 1), ("stream-1", 0), ("stream-1", 1))


@dataclass(frozen=True, slots=True)
class ReceiverPathEvidence:
    stream_id: str
    receiver_id: int
    radio_id: str
    first_sample_estimate_utc_ns: int
    last_sample_estimate_utc_ns: int
    baseline_time_s: np.ndarray
    baseline_margin: np.ndarray
    baseline_cfo_hz: np.ndarray
    corrected_records: tuple[dict[str, Any], ...]
    trajectory_table: tuple[dict[str, Any], ...]
    pilot_csv: Path
    pilot_csv_sha256: str
    feedback_json: Path
    feedback_json_sha256: str


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_id", nargs="?", default=DEFAULT_SESSION)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--artifacts-root", type=Path, default=Path("artifacts"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def aligned_time_s(local_time_s: float, first_utc_ns: int, origin_utc_ns: int) -> float:
    """Map stream-local time to seconds since the earliest stream estimate."""

    return (first_utc_ns - origin_utc_ns) / 1_000_000_000.0 + local_time_s


def evaluate_trajectory_hz(fit: dict[str, Any], local_time_s: np.ndarray) -> np.ndarray:
    """Evaluate a persisted highest-power-first CFO polynomial."""

    return np.polyval(
        np.asarray(fit["coefficients_hz"], dtype=float),
        local_time_s - float(fit["reference_time_s"]),
    )


def _read_path(
    artifacts_root: Path,
    session_id: str,
    stream_id: str,
    receiver_id: int,
    radio_id: str,
    first_utc_ns: int,
    last_utc_ns: int,
    manifest_digest: str,
) -> ReceiverPathEvidence:
    stem = f"{session_id}-{stream_id}-rx{receiver_id}"
    pilot_csv = artifacts_root / f"{stem}-pilot-methods.csv"
    feedback_json = artifacts_root / f"{stem}-trajectory-redetection.json"
    with pilot_csv.open(newline="") as handle:
        rows = tuple(csv.DictReader(handle))
    document = json.loads(feedback_json.read_text())
    if document["session_id"] != session_id:
        raise ValueError(f"feedback session mismatch for {stream_id}/RX{receiver_id}")
    if document["stream_id"] != stream_id or document["receiver_id"] != receiver_id:
        raise ValueError(f"feedback path mismatch for {stream_id}/RX{receiver_id}")
    if document["manifest_digest"] != manifest_digest:
        raise ValueError(f"feedback manifest mismatch for {stream_id}/RX{receiver_id}")
    pilot_digest = _sha256(pilot_csv)
    if document["input_sha256"] != pilot_digest:
        raise ValueError(f"pilot CSV digest mismatch for {stream_id}/RX{receiver_id}")
    baseline_time = np.asarray([float(row["time_s"]) for row in rows], dtype=float)
    baseline_margin = np.asarray([float(row["glrt64_margin"]) for row in rows], dtype=float)
    baseline_cfo = np.asarray(
        [
            float(row["acquired_cfo_hz"]) + float(row["glrt64_residual_cfo_hz"])
            for row in rows
        ],
        dtype=float,
    )
    corrected = tuple(
        row for row in document["timeline_records"] if row["method"] == "glrt64"
    )
    return ReceiverPathEvidence(
        stream_id=stream_id,
        receiver_id=receiver_id,
        radio_id=radio_id,
        first_sample_estimate_utc_ns=first_utc_ns,
        last_sample_estimate_utc_ns=last_utc_ns,
        baseline_time_s=baseline_time,
        baseline_margin=baseline_margin,
        baseline_cfo_hz=baseline_cfo,
        corrected_records=corrected,
        trajectory_table=tuple(document["glrt64_trajectory_table"]),
        pilot_csv=pilot_csv.resolve(),
        pilot_csv_sha256=pilot_digest,
        feedback_json=feedback_json.resolve(),
        feedback_json_sha256=_sha256(feedback_json),
    )


def _render(
    paths: tuple[ReceiverPathEvidence, ...],
    *,
    session_id: str,
    origin_utc_ns: int,
    union_end_s: float,
) -> bytes:
    family_colors = ("#00a6d6", "#f28e2b", "#8e5bb7", "#59a14f", "#e15759")
    degree_styles = {1: "--", 2: "-.", 3: "-"}
    margin_arrays = [
        values
        for path in paths
        for values in (
            path.baseline_margin,
            np.asarray([row["corrected_margin"] for row in path.corrected_records]),
        )
    ]
    all_margins = np.concatenate(margin_arrays)
    response_min = float(np.nanmin(all_margins))
    response_max = float(np.nanmax(all_margins))
    response_pad = max((response_max - response_min) * 0.06, 0.01)

    cfo_values: list[np.ndarray] = []
    for path in paths:
        cfo_values.append(path.baseline_cfo_hz)
        for fit in path.trajectory_table:
            times = np.linspace(float(fit["start_s"]), float(fit["end_s"]), 100)
            cfo_values.append(evaluate_trajectory_hz(fit, times))
    all_cfo = np.concatenate(cfo_values) / 1_000.0
    cfo_min = float(np.nanmin(all_cfo))
    cfo_max = float(np.nanmax(all_cfo))
    cfo_pad = max((cfo_max - cfo_min) * 0.05, 2.0)

    figure, axes = plt.subplots(4, 1, figsize=(17, 14), sharex=True)
    for row_index, (axis, path) in enumerate(zip(axes, paths, strict=True)):
        stream_offset = (path.first_sample_estimate_utc_ns - origin_utc_ns) / 1e9
        x_baseline = path.baseline_time_s + stream_offset
        axis.scatter(
            x_baseline,
            path.baseline_margin,
            s=5,
            color="#8b949e",
            alpha=0.38,
            label="initial GLRT64 margin" if row_index == 0 else None,
            rasterized=True,
        )
        family_ids = sorted({row["family_id"] for row in path.corrected_records})
        for family_index, family_id in enumerate(family_ids):
            color = family_colors[family_index % len(family_colors)]
            records = sorted(
                (row for row in path.corrected_records if row["family_id"] == family_id),
                key=lambda row: row["time_s"],
            )
            axis.plot(
                [
                    aligned_time_s(
                        row["time_s"], path.first_sample_estimate_utc_ns, origin_utc_ns
                    )
                    for row in records
                ],
                [row["corrected_margin"] for row in records],
                color=color,
                linewidth=0.9,
                alpha=0.72,
                label=(
                    "trajectory-corrected GLRT64"
                    if row_index == 0 and family_index == 0
                    else None
                ),
            )
        gates = [float(fit["high_gate"]) for fit in path.trajectory_table]
        if gates:
            axis.axhline(
                gates[0], color="#d62728", linewidth=0.8, alpha=0.55, linestyle=":"
            )
        axis.set_ylim(response_min - response_pad, response_max + response_pad)
        axis.set_ylabel("GLRT64\nmargin")
        axis.grid(True, axis="x", color="#d0d7de", linewidth=0.5, alpha=0.55)
        axis.set_title(
            f"{path.radio_id} · {path.stream_id} / RX{path.receiver_id} · "
            f"UTC offset +{stream_offset * 1_000:.6f} ms",
            loc="left",
            fontsize=10,
            fontweight="bold",
        )

        cfo_axis = axis.twinx()
        cfo_axis.scatter(
            x_baseline,
            path.baseline_cfo_hz / 1_000.0,
            s=3,
            color="#111827",
            alpha=0.12,
            rasterized=True,
        )
        fits_by_family: dict[str, list[dict[str, Any]]] = {}
        for fit in path.trajectory_table:
            if fit["fit_matches_well"]:
                fits_by_family.setdefault(fit["family_id"], []).append(fit)
        for family_index, family_id in enumerate(sorted(fits_by_family)):
            color = family_colors[family_index % len(family_colors)]
            for fit in fits_by_family[family_id]:
                local = np.linspace(float(fit["start_s"]), float(fit["end_s"]), 240)
                model = str(fit["model"])
                selected = bool(fit["selected_for_correction"])
                cfo_axis.plot(
                    local + stream_offset,
                    evaluate_trajectory_hz(fit, local) / 1_000.0,
                    color=color,
                    linestyle=degree_styles[int(fit["polynomial_degree"])],
                    linewidth=2.6 if selected else 0.85,
                    alpha=0.96 if selected else 0.38,
                    label=(f"{model} CFO fit" if row_index == 0 and family_index == 0 else None),
                )
        cfo_axis.set_ylim(cfo_min - cfo_pad, cfo_max + cfo_pad)
        cfo_axis.set_ylabel("CFO (kHz)", color="#374151")
        cfo_axis.tick_params(axis="y", labelcolor="#374151")

    origin_iso = datetime.fromtimestamp(origin_utc_ns / 1e9, tz=UTC).isoformat()
    axes[-1].set_xlim(0.0, union_end_s)
    axes[-1].set_xlabel(
        f"Seconds since earliest first-sample estimate ({origin_iso}; UTC ns {origin_utc_ns})"
    )
    handles = [
        plt.Line2D(
            [], [], marker="o", linestyle="", color="#8b949e", markersize=4,
            label="initial GLRT64 response",
        ),
        plt.Line2D(
            [], [], color="#00a6d6", linewidth=1.2,
            label="trajectory-corrected GLRT64 response",
        ),
        plt.Line2D(
            [], [], color="#111827", linewidth=1.5, linestyle="--",
            label="linear CFO fit",
        ),
        plt.Line2D(
            [], [], color="#111827", linewidth=1.5, linestyle="-.",
            label="quadratic CFO fit",
        ),
        plt.Line2D(
            [], [], color="#111827", linewidth=2.6, linestyle="-",
            label="cubic CFO fit",
        ),
        plt.Line2D(
            [], [], color="#111827", linewidth=3.2, linestyle="-",
            label="selected for replay (thick)",
        ),
    ]
    figure.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.958),
        ncol=6,
        fontsize=9,
        frameon=False,
    )
    figure.suptitle(
        "Four-path GLRT64 trajectory feedback on one dual-radio recording\n"
        f"{session_id} · candidate-only · no payload decoding",
        y=0.995,
        fontsize=15,
        fontweight="bold",
    )
    figure.tight_layout(rect=(0.02, 0.02, 0.98, 0.91))
    from io import BytesIO

    output = BytesIO()
    figure.savefig(output, format="png", dpi=170, metadata={"Software": "leo-tracker-reduxredux"})
    plt.close(figure)
    return output.getvalue()


def main() -> None:
    args = _arguments()
    pin = PinnedLocalRoot(args.bulk_root)
    store = RecordingStore.open_pinned(pin)
    try:
        bundle = store.inspect(args.session_id)
        streams = {stream.stream_id: stream for stream in bundle.manifest.streams}
        observed_paths = tuple(sorted(
            (stream.stream_id, receiver)
            for stream in bundle.manifest.streams
            for receiver in stream.applied_settings.receiver_ids
        ))
        if observed_paths != PATHS:
            raise ValueError("recording must contain exact stream-0/1 x RX0/1 path geometry")
        manifest_digest = bundle.manifest_sha256
        origin_utc_ns = min(
            stream.timing.first_sample.estimate_utc_ns for stream in bundle.manifest.streams
        )
        union_end_ns = max(
            stream.timing.last_sample.estimate_utc_ns for stream in bundle.manifest.streams
        )
        paths = tuple(
            _read_path(
                args.artifacts_root,
                args.session_id,
                stream_id,
                receiver_id,
                streams[stream_id].radio.radio_id,
                streams[stream_id].timing.first_sample.estimate_utc_ns,
                streams[stream_id].timing.last_sample.estimate_utc_ns,
                manifest_digest,
            )
            for stream_id, receiver_id in PATHS
        )
        png = _render(
            paths,
            session_id=args.session_id,
            origin_utc_ns=origin_utc_ns,
            union_end_s=(union_end_ns - origin_utc_ns) / 1e9,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(png)
        metadata_path = args.output.with_suffix(".json")
        document = {
            "session_id": args.session_id,
            "manifest_digest": manifest_digest,
            "candidate_only": True,
            "payload_decoded": False,
            "time_axis": {
                "kind": "estimated_utc_union",
                "origin_utc_ns": origin_utc_ns,
                "end_utc_ns": union_end_ns,
                "duration_s": (union_end_ns - origin_utc_ns) / 1e9,
                "phase_coherent": bundle.manifest.synchronization.phase_coherent,
                "estimated_start_skew_ns": bundle.manifest.synchronization.estimated_start_skew_ns,
            },
            "paths": [
                {
                    "stream_id": path.stream_id,
                    "receiver_id": path.receiver_id,
                    "radio_id": path.radio_id,
                    "first_sample_estimate_utc_ns": path.first_sample_estimate_utc_ns,
                    "last_sample_estimate_utc_ns": path.last_sample_estimate_utc_ns,
                    "first_sample_offset_s": (
                        path.first_sample_estimate_utc_ns - origin_utc_ns
                    )
                    / 1e9,
                    "baseline_probe_count": len(path.baseline_time_s),
                    "corrected_probe_result_count": len(path.corrected_records),
                    "trajectory_fit_count": len(path.trajectory_table),
                    "selected_trajectory_count": sum(
                        bool(fit["selected_for_correction"]) for fit in path.trajectory_table
                    ),
                    "pilot_csv": str(path.pilot_csv),
                    "pilot_csv_sha256": path.pilot_csv_sha256,
                    "feedback_json": str(path.feedback_json),
                    "feedback_json_sha256": path.feedback_json_sha256,
                }
                for path in paths
            ],
            "png": str(args.output.resolve()),
            "png_sha256": f"sha256:{hashlib.sha256(png).hexdigest()}",
        }
        metadata_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
        print(
            json.dumps(
                {
                    "png": str(args.output.resolve()),
                    "metadata": str(metadata_path.resolve()),
                    **document["time_axis"],
                }
            )
        )
    finally:
        store.close()
        pin.close()


if __name__ == "__main__":
    main()
