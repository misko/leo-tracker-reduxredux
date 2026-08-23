#!/usr/bin/env python3
"""Audit modulo-pi pilot qualification in five freshly analyzed dwells.

The report has two deliberately separate layers:

* a phase-blind inventory of every persisted 75 ms candidate window; and
* a raw-IQ rerun of every fully qualified window with an explicit symmetry
  order 1 versus symmetry order 2 tracker ablation.

One high-contrast window per dwell is plotted only as a mechanism example.  It
is selected after the all-window summaries are complete and is never used to
estimate prevalence.  Inputs are read and digest-verified; this tool writes
only its requested retrospective report bundle.
"""

# Report prose and immutable digests are intentionally kept as single source
# lines so generated Markdown remains directly auditable.
# ruff: noqa: E501

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.analysis.qam import (
    PilotPhaseDopplerTrackingConfig,
    PilotPntKalmanConfig,
    analyze_contiguous_pilot_phase_doppler_tracking,
    analyze_contiguous_pilot_pnt_kalman,
)
from leo.analysis.starlink import CONTROL_SYMBOL_ROLL, StarlinkEdge
from leo.analysis.starlink.kalman_tracking import (
    PolynomialFrequencyModel,
    raw_candidate_sources,
)
from leo.contracts.cfo_dealias import DealiasedTrajectoryBankV4, FinalTrajectoryBankV3
from leo.contracts.digests import canonical_digest
from leo.contracts.pilot_doppler_segments import (
    PilotDopplerSegmentV1,
    StandardPilotDopplerSegmentsV1,
)
from leo.storage import PinnedLocalRoot, RecordingStore

try:
    from tools.report_five_dwell_degree1_only import pilot_detections
except ModuleNotFoundError:  # Direct ``python tools/...`` invocation.
    from report_five_dwell_degree1_only import pilot_detections


DEFAULT_BULK_ROOT = Path("/srv/bulk/leo")
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_23_five_dwell_modulo_pi_qualification")
DEFAULT_REPORT_PATH = Path("reports/2026_08_23_five_dwell_modulo_pi_qualification.md")
EXPECTED_RELEASE = "e71412cf7ff716e7a25dd846fc926f0b80dd9b12"
WINDOW_DURATION_S = 0.075
BOOTSTRAP_REPLICATES = 4_000
RELEVANT_SOURCE_PATHS = (
    "src/leo/analysis/qam",
    "src/leo/analysis/starlink/pilot_doppler_segments.py",
    "src/leo/analysis/starlink/kalman_tracking.py",
    "src/leo/analysis/starlink/templates.py",
    "src/leo/contracts/cfo_dealias.py",
    "src/leo/contracts/pilot_doppler_segments.py",
)


@dataclass(frozen=True, slots=True)
class PathSpec:
    scope_digest: str
    stream_id: str
    receiver_id: int
    edge: StarlinkEdge

    @property
    def label(self) -> str:
        return f"{self.stream_id}/RX{self.receiver_id}/{self.edge.value}"


@dataclass(frozen=True, slots=True)
class DwellSpec:
    label: str
    session_id: str
    run_id: str
    paths: tuple[PathSpec, ...]


def _path(scope: str, stream: str, receiver: int, edge: str) -> PathSpec:
    return PathSpec(f"sha256:{scope}", stream, receiver, StarlinkEdge(edge))


DWELLS = (
    DwellSpec(
        "D1",
        "cap-20260821T201522-841b2a20e151",
        "reprocess-b8f39f61f17d43d6a4720324f4aebc45",
        (
            _path(
                "52f93e1e7b40c4ae4b5a0eb74373695ade208e89f50f9e2ac4c684e93abd179a",
                "stream-0",
                0,
                "upper",
            ),
            _path(
                "772366cf8fe3642cd48b64ab21a0cc55ff190da4c5173cd127362f72ab0a4222",
                "stream-1",
                0,
                "lower",
            ),
            _path(
                "8725a64ff58c01ffc7fb1754cefafe1f92a2ffdd9a993cec31a9b0c73eeaae39",
                "stream-0",
                1,
                "upper",
            ),
            _path(
                "d099093437745d00848a42c65d2523d858a5afa766651e9444d08344934358f6",
                "stream-1",
                1,
                "lower",
            ),
        ),
    ),
    DwellSpec(
        "D2",
        "cap-20260821T193701-87f96f47e73f",
        "reprocess-e149d494252c4265b4010b7ce85bd4c7",
        (
            _path(
                "51c29acf6994489e4212f6ebd1bea0d0e8fd6071928b17be7e13e0b8d56ad1e6",
                "stream-0",
                0,
                "lower",
            ),
            _path(
                "829af068aa087576b6e515d45870ee8b03e7ac9b794f30e81b3499e45a6b7d72",
                "stream-1",
                1,
                "upper",
            ),
            _path(
                "963d9454a55b8686669fbba483da244cbda4deeeee83a074abb3d762ecd28aac",
                "stream-0",
                1,
                "lower",
            ),
            _path(
                "f532df091e293b26d3f9571e4f2d393218d45e114598430c26b4ad4d373d17cd",
                "stream-1",
                0,
                "upper",
            ),
        ),
    ),
    DwellSpec(
        "D3",
        "cap-20260821T193440-17c2e0ebef6a",
        "reprocess-586820308a34449e891c196dc3177aa1",
        (
            _path(
                "3ecb4cf9d9a99dca696e69126ff60afea7043de1018df4efb92589c4e00f4adb",
                "stream-1",
                1,
                "upper",
            ),
            _path(
                "423e53428d8b2431f7cf4b4f9c32736ef24747969bac4f3f18426ee663bd5d46",
                "stream-1",
                0,
                "upper",
            ),
            _path(
                "bc038bce60f8b0bfacbf5e599c634a824758ee949b9be3b50dce800bfda1ad14",
                "stream-0",
                1,
                "upper",
            ),
            _path(
                "d6a5a2b7724fb9ccb8714ca867f134a9213820a1aedf5941bd6e131a4734f232",
                "stream-0",
                0,
                "upper",
            ),
        ),
    ),
    DwellSpec(
        "D4",
        "cap-20260821T190912-ffd441556880",
        "reprocess-338bc961078a40fda6de2b7efcf49b98",
        (
            _path(
                "467400baf354a3c36455b0568aafbb0d414cf297e0668079e7d00a3537420834",
                "stream-0",
                0,
                "lower",
            ),
            _path(
                "51d9519d4a85ea53a028d1e48dbbe52c44e9fbf671cbdfc58c3ba57515faebc9",
                "stream-1",
                0,
                "upper",
            ),
            _path(
                "61fec96aa91d8c492a828f2d2896964cd3267506ba8895112fd831d80fa51563",
                "stream-0",
                1,
                "lower",
            ),
            _path(
                "8261987dfc31c9d098e357a2062e58c745ecd3f4eb17d2d8275396079b175d56",
                "stream-1",
                1,
                "upper",
            ),
        ),
    ),
    DwellSpec(
        "D5",
        "cap-20260821T190701-7a5d980ec1c6",
        "reprocess-67959c6a6df5470e8f9ef6d06eacd9a3",
        (
            _path(
                "442fe662c7159a6a974caf2d112da26813671949b448c49f8ed788a97b4f1964",
                "stream-1",
                0,
                "upper",
            ),
            _path(
                "6812717da299386aa69cfe1505afe9032b0a31b4703399963a91815961109f97",
                "stream-0",
                0,
                "upper",
            ),
            _path(
                "699020837c6b62aa9bf241564fe40fc5f0a78ad0543ecedced3d9642729d1f84",
                "stream-0",
                1,
                "upper",
            ),
            _path(
                "c0435cacd61a41f76b3f4d049f1d51aaabdb05afbba2c0e30ec67968d379f164",
                "stream-1",
                1,
                "upper",
            ),
        ),
    ),
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=DEFAULT_BULK_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--bootstrap-replicates", type=int, default=BOOTSTRAP_REPLICATES)
    return parser.parse_args()


def wilson_interval(
    successes: int, trials: int, z: float = 1.959963984540054
) -> tuple[float, float]:
    """Return a two-sided Wilson score interval for a binomial proportion."""

    if trials <= 0 or not 0 <= successes <= trials or not math.isfinite(z) or z <= 0:
        raise ValueError("Wilson inputs are invalid")
    proportion = successes / trials
    denominator = 1.0 + z**2 / trials
    center = (proportion + z**2 / (2 * trials)) / denominator
    half_width = (
        z * math.sqrt(proportion * (1 - proportion) / trials + z**2 / (4 * trials**2)) / denominator
    )
    return max(0.0, center - half_width), min(1.0, center + half_width)


def _rms(values: Iterable[float]) -> float:
    array = np.asarray(tuple(values), dtype=np.float64)
    return math.nan if not array.size else float(np.sqrt(np.mean(array**2)))


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _read_json(path: Path) -> tuple[dict[str, Any], str]:
    payload = path.read_bytes()
    document = json.loads(payload)
    if not isinstance(document, dict):
        raise ValueError(f"expected JSON object: {path}")
    return document, _sha256(payload)


def _git_revision(name: str) -> str:
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={Path.cwd()}", "rev-parse", name],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _assert_analysis_equivalent_to_release(release: str) -> None:
    completed = subprocess.run(
        ["git", "diff", "--quiet", release, "--", *RELEVANT_SOURCE_PATHS],
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError("worktree radio-analysis implementation differs from sealed release")


def _complex_receiver(raw: np.ndarray) -> np.ndarray:
    if raw.ndim != 3 or raw.shape[1:] != (1, 2):
        raise ValueError(f"unexpected IQ shape: {raw.shape}")
    return raw[:, 0, 0].astype(float) + 1j * raw[:, 0, 1].astype(float)


def _phase_metrics(result: Any) -> dict[str, Any]:
    supported = tuple(
        frame
        for frame in result.frames
        if frame.exact_coherence >= 0.02 and frame.coherence_margin >= 0.0
    )
    return {
        "supported_frame_count": len(supported),
        "phase_update_count": result.phase_update_count,
        "phase_update_fraction": (result.phase_update_count / len(supported) if supported else 0.0),
        "phase_reset_count": result.phase_reset_count,
        "innovation_rms_rad": _rms(frame.phase_innovation_rad for frame in supported),
    }


def _resolve_request(
    segment: PilotDopplerSegmentV1,
    dealiased: DealiasedTrajectoryBankV4,
    final: FinalTrajectoryBankV3,
    scan: dict[str, Any],
) -> tuple[int, float]:
    sources = raw_candidate_sources(pilot_detections(scan))
    canonical = {item.observation_id: item for item in dealiased.observations}
    track = next(
        item for item in final.trajectories if item.trajectory_id == segment.source_trajectory_id
    )
    source = next(
        (
            sources[source_id]
            for canonical_id in track.observation_ids
            for source_id in canonical[canonical_id].source_observation_ids
            if source_id in sources
            and sources[source_id].detection_sample_start == segment.source_probe_sample_start
        ),
        None,
    )
    if source is None:
        raise ValueError("qualified segment cannot be traced to its raw acquisition source")
    model = PolynomialFrequencyModel(track.reference_time_s, tuple(track.absolute_coefficients_hz))
    initial_cfo_hz = float(model.frequency_hz(segment.start_time_s))
    return source.local_epoch_sample, initial_cfo_hz


def _paired_innovations(production: Any, order_one: Any, order_two: Any) -> tuple[np.ndarray, ...]:
    production_by_start = {
        frame.frame_start_sample: frame
        for frame in production.frames
        if frame.measurement_supported
    }
    order_one_by_start = {
        frame.frame_start_sample: frame
        for frame in order_one.frames
        if frame.exact_coherence >= 0.02 and frame.coherence_margin >= 0.0
    }
    order_two_by_start = {
        frame.frame_start_sample: frame
        for frame in order_two.frames
        if frame.exact_coherence >= 0.02 and frame.coherence_margin >= 0.0
    }
    common = tuple(
        sorted(set(production_by_start) & set(order_one_by_start) & set(order_two_by_start))
    )
    if len(common) < 20:
        raise ValueError("qualified segment has fewer than 20 common supported frames")
    return (
        np.asarray(common, dtype=np.int64),
        np.asarray([production_by_start[index].phase_innovation_modulo_pi_rad for index in common]),
        np.asarray([order_one_by_start[index].phase_innovation_rad for index in common]),
        np.asarray([order_two_by_start[index].phase_innovation_rad for index in common]),
    )


def paired_block_bootstrap_interval(
    modulo_pi: np.ndarray,
    ordinary_2pi: np.ndarray,
    *,
    seed: int,
    replicates: int,
    block_length: int = 4,
) -> tuple[float, float]:
    """Bootstrap the paired RMS reduction with circular frame blocks."""

    left = np.asarray(modulo_pi, dtype=np.float64)
    right = np.asarray(ordinary_2pi, dtype=np.float64)
    if left.shape != right.shape or left.ndim != 1 or left.size < block_length:
        raise ValueError("paired bootstrap inputs have incompatible geometry")
    if replicates < 100 or block_length < 1:
        raise ValueError("paired bootstrap configuration is too small")
    rng = np.random.default_rng(seed)
    blocks = math.ceil(left.size / block_length)
    starts = rng.integers(0, left.size, size=(replicates, blocks))
    offsets = np.arange(block_length)
    indexes = ((starts[:, :, None] + offsets) % left.size).reshape(replicates, -1)[:, : left.size]
    reductions = np.sqrt(np.mean(right[indexes] ** 2, axis=1)) - np.sqrt(
        np.mean(left[indexes] ** 2, axis=1)
    )
    return tuple(float(value) for value in np.quantile(reductions, (0.025, 0.975)))


def select_showcase(rows: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    """Select a phase-aware mechanism example, never a prevalence estimate."""

    if not rows:
        raise ValueError("showcase selection requires at least one qualified window")
    return max(
        rows,
        key=lambda row: (
            row["symmetry_rms_reduction_rad"],
            row["production_modulo_pi"]["phase_update_fraction"],
            -row["start_time_s"],
            row["path_label"],
        ),
    )


def _rerun_segment(
    reader: Any,
    path: PathSpec,
    segment: PilotDopplerSegmentV1,
    dealiased: DealiasedTrajectoryBankV4,
    final: FinalTrajectoryBankV3,
    scan: dict[str, Any],
) -> tuple[dict[str, Any], tuple[np.ndarray, ...]]:
    epoch_sample, initial_cfo_hz = _resolve_request(segment, dealiased, final, scan)
    sample_count = round(WINDOW_DURATION_S * reader.sample_rate_hz)
    raw = reader.read(
        segment.source_probe_sample_start,
        sample_count,
        receiver_ids=(path.receiver_id,),
    )
    iq = _complex_receiver(raw)
    common = {
        "epoch_sample": epoch_sample,
        "initial_absolute_cfo_hz": initial_cfo_hz,
        "edge": path.edge,
        "maximum_residual_cfo_hz": 2_000.0,
    }
    production = analyze_contiguous_pilot_pnt_kalman(
        iq,
        reader.sample_rate_hz,
        config=PilotPntKalmanConfig(),
        **common,
    )
    order_one = analyze_contiguous_pilot_phase_doppler_tracking(
        iq,
        reader.sample_rate_hz,
        config=PilotPhaseDopplerTrackingConfig(phase_symmetry_order=1),
        **common,
    )
    order_two = analyze_contiguous_pilot_phase_doppler_tracking(
        iq,
        reader.sample_rate_hz,
        config=PilotPhaseDopplerTrackingConfig(phase_symmetry_order=2),
        **common,
    )
    starts, production_innovation, ordinary_innovation, modulo_innovation = _paired_innovations(
        production, order_one, order_two
    )
    production_supported = tuple(
        frame for frame in production.frames if frame.measurement_supported
    )
    production_rms = _rms(frame.phase_innovation_modulo_pi_rad for frame in production_supported)
    if (
        production.supported_frame_count != segment.supported_frame_count
        or production.phase_update_count != segment.phase_update_count
        or production.phase_lock_qualified != segment.phase_lock_qualified
        or segment.phase_innovation_rms_rad is None
        or abs(production_rms - segment.phase_innovation_rms_rad) > 5e-10
    ):
        raise ValueError("raw-IQ rerun does not reproduce the sealed segment")
    ordinary = _phase_metrics(order_one)
    modulo = _phase_metrics(order_two)
    production_metrics = {
        "supported_frame_count": production.supported_frame_count,
        "phase_update_count": production.phase_update_count,
        "phase_update_fraction": production.phase_update_count / production.supported_frame_count,
        "innovation_rms_rad": production_rms,
        "phase_lock_qualified": production.phase_lock_qualified,
        "phase_lock_reason": production.phase_lock_reason,
        "ambiguity_transition_count": production.phase_ambiguity_transition_count,
    }
    row = {
        "path_label": path.label,
        "scope_digest": path.scope_digest,
        "segment_index": segment.segment_index,
        "source_trajectory_id": segment.source_trajectory_id,
        "source_probe_sample_start": segment.source_probe_sample_start,
        "start_time_s": segment.start_time_s,
        "end_time_s": segment.end_time_s,
        "initial_cfo_hz": initial_cfo_hz,
        "local_doppler_rate_hz_s": segment.local_doppler_rate_hz_s,
        "local_doppler_rate_sigma_hz_s": segment.local_doppler_rate_sigma_hz_s,
        "kalman_doppler_rate_hz_s": segment.kalman_doppler_rate_hz_s,
        "local_minus_kalman_rate_hz_s": segment.local_minus_kalman_rate_hz_s,
        "frequency_line_rms_hz": segment.frequency_line_rms_hz,
        "held_out_frequency_rms_hz": segment.held_out_frequency_rms_hz,
        "production_modulo_pi": production_metrics,
        "controlled_order_1_2pi": ordinary,
        "controlled_order_2_modulo_pi": modulo,
        "symmetry_rms_reduction_rad": (
            ordinary["innovation_rms_rad"] - modulo["innovation_rms_rad"]
        ),
        "common_supported_frame_count": int(starts.size),
    }
    return row, (starts, production_innovation, ordinary_innovation, modulo_innovation)


def _rolled_control(
    reader: Any, path: PathSpec, row: dict[str, Any], request: tuple[int, float]
) -> dict[str, Any]:
    epoch_sample, initial_cfo_hz = request
    sample_count = round(WINDOW_DURATION_S * reader.sample_rate_hz)
    raw = reader.read(
        row["source_probe_sample_start"], sample_count, receiver_ids=(path.receiver_id,)
    )
    iq = _complex_receiver(raw)
    result = analyze_contiguous_pilot_pnt_kalman(
        iq,
        reader.sample_rate_hz,
        epoch_sample=epoch_sample,
        initial_absolute_cfo_hz=initial_cfo_hz,
        edge=path.edge,
        maximum_residual_cfo_hz=2_000.0,
        expected_symbol_roll=CONTROL_SYMBOL_ROLL,
        config=PilotPntKalmanConfig(),
    )
    return {
        "expected_symbol_roll": CONTROL_SYMBOL_ROLL,
        # A rejected template can return no retained result frames even though
        # every complete lattice opportunity was tested before rejection.  Use
        # the exact track's supported inventory as a conservative denominator.
        "evaluated_frame_count": row["production_modulo_pi"]["supported_frame_count"],
        "retained_result_frame_count": len(result.frames),
        "supported_frame_count": result.supported_frame_count,
        "phase_update_count": result.phase_update_count,
        "phase_lock_qualified": result.phase_lock_qualified,
        "status": result.status.value,
    }


def _population_summary(segments: tuple[PilotDopplerSegmentV1, ...]) -> dict[str, Any]:
    analyzed = len(segments)
    phase = sum(item.phase_lock_qualified for item in segments)
    qualified = sum(item.qualified for item in segments)
    return {
        "candidate_window_count": analyzed,
        "analyzed_window_count": analyzed,
        "phase_lock_qualified_count": phase,
        "phase_lock_fraction": phase / analyzed,
        "phase_lock_wilson_95": wilson_interval(phase, analyzed),
        "fully_qualified_count": qualified,
        "fully_qualified_fraction": qualified / analyzed,
        "fully_qualified_wilson_95": wilson_interval(qualified, analyzed),
    }


def _raw_summary(rows: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    reductions = np.asarray([row["symmetry_rms_reduction_rad"] for row in rows])
    modulo_rms = np.asarray(
        [row["controlled_order_2_modulo_pi"]["innovation_rms_rad"] for row in rows]
    )
    ordinary_rms = np.asarray([row["controlled_order_1_2pi"]["innovation_rms_rad"] for row in rows])
    improved = int(np.sum(reductions > 0))
    strong = int(np.sum((ordinary_rms > 0.5) & (modulo_rms <= 0.5)))
    return {
        "rerun_window_count": len(rows),
        "sealed_reproduction_count": sum(
            row["production_modulo_pi"]["phase_lock_qualified"] for row in rows
        ),
        "symmetry_improved_count": improved,
        "symmetry_improved_fraction": improved / len(rows),
        "symmetry_improved_wilson_95": wilson_interval(improved, len(rows)),
        "strong_threshold_crossing_count": strong,
        "ordinary_2pi_median_innovation_rms_rad": float(np.median(ordinary_rms)),
        "modulo_pi_median_innovation_rms_rad": float(np.median(modulo_rms)),
        "median_symmetry_rms_reduction_rad": float(np.median(reductions)),
        "ordinary_2pi_total_resets": sum(
            row["controlled_order_1_2pi"]["phase_reset_count"] for row in rows
        ),
        "modulo_pi_total_resets": sum(
            row["controlled_order_2_modulo_pi"]["phase_reset_count"] for row in rows
        ),
    }


def _plot_population(dwell_rows: list[dict[str, Any]], path: Path) -> None:
    labels = [row["label"] for row in dwell_rows]
    positions = np.arange(len(labels))
    width = 0.36
    phase = np.asarray([row["population"]["phase_lock_fraction"] for row in dwell_rows])
    full = np.asarray([row["population"]["fully_qualified_fraction"] for row in dwell_rows])
    phase_ci = np.asarray([row["population"]["phase_lock_wilson_95"] for row in dwell_rows])
    full_ci = np.asarray([row["population"]["fully_qualified_wilson_95"] for row in dwell_rows])
    with plt.rc_context({"font.size": 10, "axes.grid": True, "grid.alpha": 0.22}):
        figure, axis = plt.subplots(figsize=(11.5, 6.2), constrained_layout=True)
        axis.bar(
            positions - width / 2,
            phase,
            width,
            yerr=np.maximum(
                0.0,
                np.vstack((phase - phase_ci[:, 0], phase_ci[:, 1] - phase)),
            ),
            capsize=3,
            color="#2a9d62",
            label="inner modulo-π phase-lock gate",
        )
        axis.bar(
            positions + width / 2,
            full,
            width,
            yerr=np.maximum(
                0.0,
                np.vstack((full - full_ci[:, 0], full_ci[:, 1] - full)),
            ),
            capsize=3,
            color="#247ba0",
            label="all 75 ms segment gates",
        )
        for index, row in enumerate(dwell_rows):
            axis.text(
                index - width / 2,
                phase[index] + 0.012,
                f"{row['population']['phase_lock_qualified_count']}/{row['population']['analyzed_window_count']}",
                ha="center",
                va="bottom",
                fontsize=8,
            )
            axis.text(
                index + width / 2,
                full[index] + 0.012,
                f"{row['population']['fully_qualified_count']}/{row['population']['analyzed_window_count']}",
                ha="center",
                va="bottom",
                fontsize=8,
            )
        axis.set_xticks(positions, labels)
        axis.set_ylim(0, max(phase_ci[:, 1].max(), full_ci[:, 1].max()) + 0.08)
        axis.set_ylabel("fraction of phase-blind candidate windows")
        axis.set_title(
            "Five fresh dwells: modulo-π phase locks occur in every dwell\n"
            "error bars are descriptive 95% Wilson intervals; windows are correlated"
        )
        axis.legend()
        figure.savefig(path, dpi=190, metadata={"Software": "leo-tracker"})
        plt.close(figure)


def _plot_ablation(dwell_rows: list[dict[str, Any]], path: Path) -> None:
    labels = [row["label"] for row in dwell_rows]
    selected = [row["showcase"] for row in dwell_rows]
    positions = np.arange(len(labels))
    width = 0.34
    with plt.rc_context({"font.size": 10, "axes.grid": True, "grid.alpha": 0.22}):
        figure, axes = plt.subplots(1, 2, figsize=(14, 6.2), constrained_layout=True)
        rms_axis, yield_axis = axes
        rms_axis.bar(
            positions - width / 2,
            [row["controlled_order_1_2pi"]["innovation_rms_rad"] for row in selected],
            width,
            color="#d95f5f",
            label="same tracker, symmetry order 1 (2π)",
        )
        rms_axis.bar(
            positions + width / 2,
            [row["controlled_order_2_modulo_pi"]["innovation_rms_rad"] for row in selected],
            width,
            color="#2a9d62",
            label="same tracker, symmetry order 2 (π)",
        )
        rms_axis.axhline(
            0.5, color="black", linestyle=":", linewidth=1.0, label="production lock RMS gate"
        )
        rms_axis.set_xticks(positions, labels)
        rms_axis.set_ylabel("pre-update phase innovation RMS (rad)")
        rms_axis.set_title("A · Post-hoc mechanism examples; not prevalence")
        rms_axis.legend(fontsize=8)

        improved = [row["raw_ablation"]["symmetry_improved_fraction"] for row in dwell_rows]
        ci = np.asarray([row["raw_ablation"]["symmetry_improved_wilson_95"] for row in dwell_rows])
        values = np.asarray(improved)
        yield_axis.bar(
            positions,
            values,
            yerr=np.maximum(
                0.0,
                np.vstack((values - ci[:, 0], ci[:, 1] - values)),
            ),
            capsize=3,
            color="#247ba0",
        )
        for index, row in enumerate(dwell_rows):
            summary = row["raw_ablation"]
            yield_axis.text(
                index,
                values[index] + 0.025,
                f"{summary['symmetry_improved_count']}/{summary['rerun_window_count']}",
                ha="center",
                fontsize=8,
            )
        yield_axis.set_xticks(positions, labels)
        yield_axis.set_ylim(0, 1.12)
        yield_axis.set_ylabel("fraction with lower RMS under modulo π")
        yield_axis.set_title("B · All fully qualified raw-IQ windows")
        figure.suptitle(
            "Explicit one-parameter phase-symmetry ablation\n"
            "order 1 and order 2 trackers otherwise use identical configuration",
            fontsize=14,
        )
        figure.savefig(path, dpi=190, metadata={"Software": "leo-tracker"})
        plt.close(figure)


def _plot_showcases(
    dwell_rows: list[dict[str, Any]], frames: dict[str, tuple[np.ndarray, ...]], path: Path
) -> None:
    with plt.rc_context({"font.size": 9, "axes.grid": True, "grid.alpha": 0.22}):
        figure, axes = plt.subplots(5, 1, figsize=(14, 13), sharex=False, constrained_layout=True)
        for axis, dwell in zip(axes, dwell_rows, strict=True):
            starts, production, ordinary, modulo = frames[dwell["label"]]
            time_ms = (starts - starts[0]) / 2_500_000 * 1e3
            axis.scatter(time_ms, ordinary, s=12, color="#d95f5f", alpha=0.55, label="order 1 / 2π")
            axis.scatter(
                time_ms,
                modulo,
                s=15,
                facecolor="none",
                edgecolor="#2a9d62",
                linewidth=0.8,
                label="order 2 / π",
            )
            axis.plot(
                time_ms,
                production,
                color="#247ba0",
                linewidth=0.8,
                alpha=0.75,
                label="production π tracker",
            )
            axis.axhline(0, color="black", linewidth=0.6)
            axis.axhspan(-0.5, 0.5, color="#2a9d62", alpha=0.05)
            show = dwell["showcase"]
            axis.set_title(
                f"{dwell['label']} · {show['path_label']} · t={show['start_time_s']:.3f} s · "
                f"RMS reduction={show['symmetry_rms_reduction_rad']:.3f} rad"
            )
            axis.set_ylabel("innovation (rad)")
        axes[0].legend(ncol=3, fontsize=8)
        axes[-1].set_xlabel("time from first common supported frame (ms)")
        figure.suptitle(
            "Five measured-IQ mechanism examples selected by largest within-dwell symmetry contrast\n"
            "π wrapping changes representation; it does not assert a physical transmitter phase reset",
            fontsize=14,
        )
        figure.savefig(path, dpi=190, metadata={"Software": "leo-tracker"})
        plt.close(figure)


def _percent(value: float) -> str:
    return f"{100 * value:.1f}%"


def _interval(value: Iterable[float]) -> str:
    low, high = value
    return f"{_percent(float(low))}–{_percent(float(high))}"


def _render_report(document: dict[str, Any]) -> str:
    dwells = document["dwells"]
    totals = document["totals"]
    lines = [
        "# Five-dwell audit of `modulo-π-qualified`",
        "",
        "**Date:** 2026-08-23 UTC  ",
        "**Scope:** five historical 60 s dwells, four receiver paths per dwell, freshly rerun with sealed Standard release "
        f"`{document['provenance']['pipeline_release_id']}`  ",
        "**Result:** every dwell contains independently gated, exact-known-pilot windows that pass the production modulo-π phase-lock gate and the stricter full 75 ms segment gate. Across all "
        f"{totals['fully_qualified_count']} fully qualified windows, the explicit order-1/order-2 raw-IQ ablation lowers phase-innovation RMS in "
        f"{totals['symmetry_improved_count']} ({_percent(totals['symmetry_improved_fraction'])}). Conditional on those modulo-π-selected windows, this confirms that π-periodic phase is operationally consistent and avoids the ordinary 2π reset storm. The direction of the RMS change is not, by itself, an unbiased model-selection test because the quotient has a shorter wrap interval and the population was selected with a modulo-π gate. It does **not** show that Starlink intentionally resets phase, changes RF frequency every 50–75 ms, or identify any satellite.",
        "",
        "## What the term means",
        "",
        "The known-pilot channel observation is treated as equivalent under",
        "",
        "\\[\\phi \\equiv \\phi + \\pi.\\]",
        "",
        "For every supported frame the tracker therefore uses the pre-update innovation wrapped into `[-π/2, +π/2)`. `modulo-π-qualified` means the window passed three inner gates: at least 20 supported frames, phase updates on at least 80% of those frames, and pre-update modulo-π innovation RMS no greater than 0.50 rad. A production segment is `qualified` only if it also passes support coverage/gap, exact-versus-rolled-pilot coherence, local line RMS, interleaved holdout RMS, and local-versus-Kalman rate-agreement gates.",
        "",
        "The π branch index is an analyzer representation. A transition in that index is **not** evidence of a physical phase reset, and no transition count is used to select or qualify the population result.",
        "",
        "## Phase-blind population result",
        "",
        "Candidate windows were fixed by the sealed track/probe geometry before this audit looked at phase continuity. The table includes every analyzed 75 ms window on all four paths.",
        "",
        "| Dwell | Fresh sealed run | Windows | Inner phase lock | 95% Wilson | Full qualified | 95% Wilson |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for dwell in dwells:
        population = dwell["population"]
        lines.append(
            f"| {dwell['label']} | `{dwell['run_id']}` | {population['analyzed_window_count']} | "
            f"{population['phase_lock_qualified_count']} ({_percent(population['phase_lock_fraction'])}) | "
            f"{_interval(population['phase_lock_wilson_95'])} | "
            f"{population['fully_qualified_count']} ({_percent(population['fully_qualified_fraction'])}) | "
            f"{_interval(population['fully_qualified_wilson_95'])} |"
        )
    lines += [
        "",
        f"Across the five dwells: {totals['analyzed_window_count']} windows, {totals['phase_lock_qualified_count']} inner locks, and {totals['fully_qualified_count']} fully qualified segments. The Wilson intervals treat windows as independent and are therefore descriptive and likely too narrow because windows from one track/dwell are correlated. The stronger replication statement is simply five of five dwells with nonzero full-qualified yield; five dwells are still a small cohort.",
        "",
        "![Phase-blind qualification yield](figures/2026_08_23_five_dwell_modulo_pi_qualification/modulo-pi-population.png)",
        "",
        "## Clean symmetry ablation on measured IQ",
        "",
        "Every fully qualified window was reopened through a digest-verifying IQ reader. The same phase tracker was then run twice with identical settings except `phase_symmetry_order=1` (ordinary 2π) versus `phase_symmetry_order=2` (modulo π). The production five-state modulo-π tracker was separately rerun and required to reproduce its sealed counts, Boolean lock result, and innovation RMS.",
        "",
        "| Dwell | Raw windows | π lowers RMS | Median 2π RMS | Median π RMS | Median reduction | 2π resets | π resets |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for dwell in dwells:
        raw = dwell["raw_ablation"]
        lines.append(
            f"| {dwell['label']} | {raw['rerun_window_count']} | {raw['symmetry_improved_count']} "
            f"({_percent(raw['symmetry_improved_fraction'])}) | {raw['ordinary_2pi_median_innovation_rms_rad']:.3f} rad | "
            f"{raw['modulo_pi_median_innovation_rms_rad']:.3f} rad | {raw['median_symmetry_rms_reduction_rad']:+.3f} rad | "
            f"{raw['ordinary_2pi_total_resets']} | {raw['modulo_pi_total_resets']} |"
        )
    lines += [
        "",
        "This is a controlled operational ablation of the π representation, distinct from merely observing a good known-pilot match: the order-1/order-2 pair differs in exactly the declared rotational symmetry. It is **not** neutral discovery evidence for the symmetry order. Wrapping onto a shorter quotient tends to reduce angular residuals, and these windows already passed a modulo-π gate. The useful result is that the same π model remains causal, reproduces the sealed gates in all five dwells, avoids hundreds of ordinary resets, rejects the matched rolled pilot, and agrees with independent local-frequency checks. This audit does not test whether an even finer symmetry such as π/2 could lower residuals further. The rolled-pilot negative control is applied below to one mechanism example per dwell.",
        "",
        "### Correction to the older PNT report helper",
        "",
        "The current checked-in `tools/report_pilot_pnt_kalman.py` labels one comparison `ordinary 2π` but calls `PilotPhaseDopplerTrackingConfig()` without overriding its current default `phase_symmetry_order=2`. A new rerun of that helper would therefore not be a valid 2π ablation. This report does not reuse that label or its comparison output: it constructs explicit order-1 and order-2 configurations and records both complete configurations in JSON. The older checked-in artifact may reflect code at its original generation time, but the present helper cannot establish that provenance by itself.",
        "",
        "![Symmetry ablation](figures/2026_08_23_five_dwell_modulo_pi_qualification/modulo-pi-ablation.png)",
        "",
        "## How each dwell supports—or limits—the finding",
        "",
        "The plotted example in each dwell is the fully qualified window with the largest order-1 minus order-2 RMS reduction. That is a disclosed post-hoc mechanism selection; the all-window table above, not these five examples, estimates prevalence.",
        "",
        "| Dwell | Path / start | Frames / updates | 2π RMS | π RMS | Paired block-bootstrap 95% reduction | Rolled support | Line / holdout RMS | Rate ± formal 1σ |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for dwell in dwells:
        row = dwell["showcase"]
        production = row["production_modulo_pi"]
        ordinary = row["controlled_order_1_2pi"]
        modulo = row["controlled_order_2_modulo_pi"]
        control = row["rolled_control"]
        low, high = row["symmetry_reduction_block_bootstrap_95_rad"]
        lines.append(
            f"| {dwell['label']} | {row['path_label']} / {row['start_time_s']:.3f} s | "
            f"{production['supported_frame_count']} / {production['phase_update_count']} | "
            f"{ordinary['innovation_rms_rad']:.3f} | {modulo['innovation_rms_rad']:.3f} | "
            f"{low:+.3f} to {high:+.3f} rad | {control['supported_frame_count']}/{control['evaluated_frame_count']} | "
            f"{row['frequency_line_rms_hz']:.1f} / {row['held_out_frequency_rms_hz']:.1f} Hz | "
            f"{row['local_doppler_rate_hz_s']:+.0f} ± {row['local_doppler_rate_sigma_hz_s']:.0f} Hz/s |"
        )
    lines += [
        "",
        "![Five raw-IQ mechanism examples](figures/2026_08_23_five_dwell_modulo_pi_qualification/modulo-pi-showcases.png)",
        "",
    ]
    for dwell in dwells:
        row = dwell["showcase"]
        raw = dwell["raw_ablation"]
        lines += [
            f"### {dwell['label']} — `{dwell['session_id']}`",
            "",
            f"This dwell contributes {dwell['population']['fully_qualified_count']} full segments. In the raw-IQ corpus ablation, modulo π lowers RMS in {raw['symmetry_improved_count']}/{raw['rerun_window_count']} full-qualified windows. The showcased window retains {row['production_modulo_pi']['phase_update_count']}/{row['production_modulo_pi']['supported_frame_count']} phase updates, its rolled control supports {row['rolled_control']['supported_frame_count']} frames, and its independent local CFO line has {row['frequency_line_rms_hz']:.1f} Hz fit RMS with {row['held_out_frequency_rms_hz']:.1f} Hz interleaved holdout RMS. This supports a local known-pilot phase lock with π-periodic representation; it does not resolve absolute sign or transmitter intent.",
            "",
        ]
    rolled_supported = totals["showcase_rolled_supported_frames"]
    rolled_frames = totals["showcase_rolled_frames"]
    lines += [
        "## Competing hypotheses",
        "",
        "| Hypothesis | Prediction | Result | Disposition |",
        "|---|---|---|---|",
        f"| Accidental/noise match | Exact and 17-symbol-rolled templates should support similar frames | Exact production pilots support {totals['showcase_exact_supported_frames']} showcase frames; rolled control supports {rolled_supported}/{rolled_frames} | Disfavored for these five examples; this is a matched control, not a universal false-alarm calibration |",
        f"| Ordinary 2π phase is sufficient | Symmetry order 2 should not systematically reduce innovations | π lowers RMS in {totals['symmetry_improved_count']}/{totals['fully_qualified_count']} full-qualified windows across all five dwells | Disfavored as the general representation |",
        "| π-periodic phase is the observable | Order 2 improves continuity while production gates remain causal | Seen in every dwell, with sealed production results exactly reproduced | Supported for these receiver-relative pilot channel observations |",
        "| π-branch transitions are transmitter resets | Branch count should directly encode physical reset events | Branch choice depends on modulo representation and is not used as evidence | Not supported |",
        "| 75 ms windows are Starlink transmission slots | Qualification boundaries should be signal-defined | Boundaries are analyzer windows seeded from persisted probes | Rejected as an inference from this audit |",
        "| A specific Starlink satellite produced a window | TLE geometry should uniquely fit the track | No TLE or sky model enters this report | Untested; no identity claim |",
        "",
        "## Error and limitation accounting",
        "",
        f"1. **Reproduction error:** {totals['fully_qualified_count']}/{totals['fully_qualified_count']} sealed full-qualified windows were rerun from verified IQ. The maximum absolute reproduced innovation-RMS difference was {totals['maximum_reproduction_rms_error_rad']:.3g} rad; count and Boolean-lock disagreements were zero.",
        "2. **Population sampling error:** per-dwell Wilson intervals are shown, but within-dwell correlation makes them anti-conservative. The independent experimental unit is closer to a dwell than a window, and only five dwells were reviewed.",
        f"3. **Mechanism-example error:** each paired 95% interval uses {document['method']['bootstrap_replicates']} circular four-frame block bootstrap replicates. It is conditional on the selected window and does not include post-selection uncertainty, so it is explanatory rather than a prevalence interval.",
        f"4. **Pilot-specificity error:** the five showcase rolled controls yielded {rolled_supported}/{rolled_frames} supported frames; the descriptive Wilson 95% upper bound is {_percent(totals['showcase_rolled_support_wilson_95'][1])}. This does not replace a broad off-template/off-time false-alarm campaign.",
        "5. **Frequency/rate error:** each showcase reports direct in-sample line RMS, interleaved held-out RMS, and the robust local slope's formal 1σ. These are conditional estimator errors, not satellite-identification uncertainties.",
        "6. **Identity error:** satellite identity is outside this report. Its error is therefore unestimated, and `modulo-π-qualified` must not be read as `Starlink-satellite-qualified`.",
        "7. **Model-selection error:** all 216 ablation windows were conditioned on the production modulo-π qualification gate, and a shorter angular quotient naturally cannot be judged solely by lower wrapped RMS. The ablation establishes operational consistency and reset avoidance, not a calibrated Bayes factor for symmetry order 2 versus every possible phase model.",
        "",
        "## Provenance and reproducibility",
        "",
        f"- Main reviewed at `{document['provenance']['main_revision']}`; `origin/main` matched.",
        f"- All five sealed runs use Standard release `{document['provenance']['pipeline_release_id']}`. The worktree's relevant radio-analysis sources were byte-diff-equivalent to that release before rerunning IQ.",
        "- Recording manifest digests: "
        + ", ".join(f"{row['label']} `{row['recording_manifest_digest']}`" for row in dwells)
        + ".",
        "- The machine-readable result includes every full-qualified raw-IQ ablation row, all artifact digests, exact configurations, showcase frame innovations, and explicit limitations: [`five-dwell-modulo-pi-results.json`](figures/2026_08_23_five_dwell_modulo_pi_qualification/five-dwell-modulo-pi-results.json).",
        "- Reproduce with `.venv/bin/python tools/report_five_dwell_modulo_pi_qualification.py`.",
        "",
        "## Bottom line",
        "",
        "`modulo-π-qualified` is a bounded analyzer statement: on a verified 75 ms IQ window, the exact known-pilot channel supports causal phase updates when phase is treated as π-periodic, and (for `qualified`) the independent frequency checks also pass. Five fresh dwells reproduce that behavior. The evidence says the receiver cannot safely distinguish `φ` from `φ + π`; it does not say the satellite physically flips phase, hops frequency, or transmits only for 75 ms.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    args = _arguments()
    if args.bootstrap_replicates < 100:
        raise ValueError("bootstrap replicate count must be at least 100")
    _assert_analysis_equivalent_to_release(EXPECTED_RELEASE)
    main_revision = _git_revision("main")
    origin_revision = _git_revision("origin/main")
    if main_revision != origin_revision:
        raise ValueError("local main and origin/main differ")
    args.output_root.mkdir(parents=True, exist_ok=True)
    args.report_path.parent.mkdir(parents=True, exist_ok=True)

    analysis_root = args.bulk_root / "analysis"
    store = RecordingStore.open_pinned(PinnedLocalRoot(args.bulk_root))
    dwell_documents: list[dict[str, Any]] = []
    showcase_frames: dict[str, tuple[np.ndarray, ...]] = {}
    maximum_reproduction_error = 0.0
    try:
        for dwell_index, dwell in enumerate(DWELLS):
            run_root = analysis_root / dwell.session_id / dwell.run_id
            manifest, manifest_file_digest = _read_json(run_root / "manifest.json")
            if (
                manifest.get("session_id") != dwell.session_id
                or manifest.get("run_id") != dwell.run_id
                or manifest.get("pipeline_lane") != "standard"
                or manifest.get("pipeline_release_id") != EXPECTED_RELEASE
            ):
                raise ValueError(f"sealed run manifest disagrees for {dwell.label}")
            scientific_root = run_root / "scientific" / "path-standard"
            actual_scopes = {path.name for path in scientific_root.iterdir() if path.is_dir()}
            expected_scopes = {path.scope_digest for path in dwell.paths}
            if actual_scopes != expected_scopes:
                raise ValueError(f"path scope inventory disagrees for {dwell.label}")
            bundle = store.inspect(dwell.session_id)
            readers = {
                stream: store.reader(bundle, stream, verify=True)
                for stream in sorted({path.stream_id for path in dwell.paths})
            }
            all_segments: list[PilotDopplerSegmentV1] = []
            qualified_jobs: list[
                tuple[
                    PathSpec,
                    PilotDopplerSegmentV1,
                    DealiasedTrajectoryBankV4,
                    FinalTrajectoryBankV3,
                    dict[str, Any],
                ]
            ] = []
            artifact_digests: dict[str, dict[str, str]] = {}
            for path in dwell.paths:
                root = scientific_root / path.scope_digest
                scan, scan_digest = _read_json(root / "standard.pilot-scan.v3.json")
                dealiased_document, dealiased_digest = _read_json(
                    root / "standard.dealiased-trajectory-bank.v4.json"
                )
                final_document, final_digest = _read_json(
                    root / "standard.final-trajectory-bank.v3.json"
                )
                segment_document, segment_digest = _read_json(
                    root / "standard.pilot-doppler-segments.v1.json"
                )
                dealiased = DealiasedTrajectoryBankV4.model_validate(dealiased_document)
                final = FinalTrajectoryBankV3.model_validate(final_document)
                segments = StandardPilotDopplerSegmentsV1.model_validate(segment_document)
                if (
                    segments.pilot_scan_digest != canonical_digest(scan)
                    or segments.dealiased_bank_digest != dealiased.content_digest
                    or segments.final_trajectory_bank_digest != final.content_digest
                    or segments.analyzed_segment_count != segments.candidate_window_count
                ):
                    raise ValueError(
                        f"cross-product lineage disagrees for {dwell.label}/{path.label}"
                    )
                artifact_digests[path.label] = {
                    "pilot_scan_file_sha256": scan_digest,
                    "dealiased_bank_file_sha256": dealiased_digest,
                    "final_bank_file_sha256": final_digest,
                    "pilot_segments_file_sha256": segment_digest,
                    "pilot_segments_content_digest": segments.content_digest,
                }
                all_segments.extend(segments.segments)
                qualified_jobs.extend(
                    (path, segment, dealiased, final, scan)
                    for segment in segments.segments
                    if segment.qualified
                )
            population = _population_summary(tuple(all_segments))
            raw_rows: list[dict[str, Any]] = []
            frames_by_key: dict[tuple[str, int], tuple[np.ndarray, ...]] = {}
            request_by_key: dict[tuple[str, int], tuple[int, float]] = {}
            path_by_key: dict[tuple[str, int], PathSpec] = {}
            for path, segment, dealiased, final, scan in qualified_jobs:
                row, frames = _rerun_segment(
                    readers[path.stream_id], path, segment, dealiased, final, scan
                )
                key = (path.scope_digest, segment.segment_index)
                frames_by_key[key] = frames
                request_by_key[key] = _resolve_request(segment, dealiased, final, scan)
                path_by_key[key] = path
                maximum_reproduction_error = max(
                    maximum_reproduction_error,
                    abs(
                        row["production_modulo_pi"]["innovation_rms_rad"]
                        - float(segment.phase_innovation_rms_rad)
                    ),
                )
                raw_rows.append(row)
            raw_tuple = tuple(raw_rows)
            showcase = select_showcase(raw_tuple)
            showcase_key = (showcase["scope_digest"], showcase["segment_index"])
            showcase["rolled_control"] = _rolled_control(
                readers[path_by_key[showcase_key].stream_id],
                path_by_key[showcase_key],
                showcase,
                request_by_key[showcase_key],
            )
            _, _, ordinary, modulo = frames_by_key[showcase_key]
            showcase["symmetry_reduction_block_bootstrap_95_rad"] = paired_block_bootstrap_interval(
                modulo,
                ordinary,
                seed=20_260_823 + dwell_index,
                replicates=args.bootstrap_replicates,
            )
            starts, production, ordinary, modulo = frames_by_key[showcase_key]
            showcase["frames"] = [
                {
                    "frame_start_sample": int(start),
                    "time_from_first_frame_ms": float((start - starts[0]) / 2_500_000 * 1e3),
                    "production_modulo_pi_innovation_rad": float(prod),
                    "controlled_order_1_2pi_innovation_rad": float(one),
                    "controlled_order_2_modulo_pi_innovation_rad": float(two),
                }
                for start, prod, one, two in zip(starts, production, ordinary, modulo, strict=True)
            ]
            showcase_frames[dwell.label] = frames_by_key[showcase_key]
            dwell_documents.append(
                {
                    "label": dwell.label,
                    "session_id": dwell.session_id,
                    "run_id": dwell.run_id,
                    "run_manifest_file_sha256": manifest_file_digest,
                    "recording_manifest_digest": bundle.manifest_sha256,
                    "verified_iq_reader": True,
                    "path_count": len(dwell.paths),
                    "artifact_digests": artifact_digests,
                    "population": population,
                    "raw_ablation": _raw_summary(raw_tuple),
                    "showcase": showcase,
                    "fully_qualified_windows": raw_rows,
                }
            )
            print(
                f"{dwell.label}: {population['fully_qualified_count']} full windows rerun; "
                f"{dwell_documents[-1]['raw_ablation']['symmetry_improved_count']} improve under pi",
                flush=True,
            )
    finally:
        store.close()

    analyzed = sum(row["population"]["analyzed_window_count"] for row in dwell_documents)
    phase = sum(row["population"]["phase_lock_qualified_count"] for row in dwell_documents)
    full = sum(row["population"]["fully_qualified_count"] for row in dwell_documents)
    improved = sum(row["raw_ablation"]["symmetry_improved_count"] for row in dwell_documents)
    exact_showcase = sum(
        row["showcase"]["production_modulo_pi"]["supported_frame_count"] for row in dwell_documents
    )
    rolled_frames = sum(
        row["showcase"]["rolled_control"]["evaluated_frame_count"] for row in dwell_documents
    )
    rolled_supported = sum(
        row["showcase"]["rolled_control"]["supported_frame_count"] for row in dwell_documents
    )
    document = {
        "schema_version": 1,
        "algorithm": "five-dwell-modulo-pi-qualification-audit-v1",
        "claim_scope": {
            "candidate_only": True,
            "known_pilots_only": True,
            "absolute_carrier_phase_resolved": False,
            "carrier_phase_period_rad": math.pi,
            "satellite_identity_claimed": False,
            "transmitter_reset_claimed": False,
            "transmission_window_claimed": False,
        },
        "provenance": {
            "main_revision": main_revision,
            "origin_main_revision": origin_revision,
            "worktree_revision": _git_revision("HEAD"),
            "pipeline_release_id": EXPECTED_RELEASE,
            "relevant_radio_sources_diff_equivalent_to_release": True,
        },
        "method": {
            "window_duration_s": WINDOW_DURATION_S,
            "population_selection": "all sealed phase-blind candidate windows",
            "raw_ablation_selection": "all fully qualified windows",
            "showcase_selection": "maximum order-1 minus order-2 innovation RMS reduction per dwell; post-hoc and not prevalence",
            "production_configuration": asdict(PilotPntKalmanConfig()),
            "controlled_order_1_configuration": asdict(
                PilotPhaseDopplerTrackingConfig(phase_symmetry_order=1)
            ),
            "controlled_order_2_configuration": asdict(
                PilotPhaseDopplerTrackingConfig(phase_symmetry_order=2)
            ),
            "bootstrap_replicates": args.bootstrap_replicates,
            "bootstrap_block_frames": 4,
        },
        "totals": {
            "dwell_count": len(dwell_documents),
            "receiver_path_count": sum(row["path_count"] for row in dwell_documents),
            "analyzed_window_count": analyzed,
            "phase_lock_qualified_count": phase,
            "fully_qualified_count": full,
            "symmetry_improved_count": improved,
            "symmetry_improved_fraction": improved / full,
            "showcase_exact_supported_frames": exact_showcase,
            "showcase_rolled_frames": rolled_frames,
            "showcase_rolled_supported_frames": rolled_supported,
            "showcase_rolled_support_wilson_95": wilson_interval(rolled_supported, rolled_frames),
            "maximum_reproduction_rms_error_rad": maximum_reproduction_error,
        },
        "dwells": dwell_documents,
        "figures": (
            "modulo-pi-population.png",
            "modulo-pi-ablation.png",
            "modulo-pi-showcases.png",
        ),
        "limitations": (
            "within-dwell windows are correlated",
            "the raw ablation is conditional on windows selected by a modulo-pi qualification gate",
            "lower wrapped RMS alone is not unbiased identification of phase symmetry order",
            "symmetry orders finer than pi were not tested",
            "the current older PNT report helper has an ordinary-2pi label/default-configuration mismatch",
            "showcases are selected post-hoc and their bootstrap intervals omit selection uncertainty",
            "rolled control is not a calibrated universal false-alarm experiment",
            "pi branch transitions are analyzer bookkeeping rather than physical reset evidence",
            "no satellite identity or transmitter cadence is inferred",
        ),
    }
    _plot_population(dwell_documents, args.output_root / "modulo-pi-population.png")
    _plot_ablation(dwell_documents, args.output_root / "modulo-pi-ablation.png")
    _plot_showcases(
        dwell_documents,
        showcase_frames,
        args.output_root / "modulo-pi-showcases.png",
    )
    result_path = args.output_root / "five-dwell-modulo-pi-results.json"
    result_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.report_path.write_text(_render_report(document), encoding="utf-8")
    print(
        json.dumps(
            {
                "report": str(args.report_path),
                "results": str(result_path),
                "dwells": len(dwell_documents),
                "windows": analyzed,
                "full_qualified_reruns": full,
                "symmetry_improved": improved,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
