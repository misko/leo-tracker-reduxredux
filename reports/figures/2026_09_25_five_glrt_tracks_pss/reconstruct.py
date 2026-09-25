#!/usr/bin/env python3
"""Try to reconstruct five GLRT-selected scanner tracks with blind PSS timing."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import asdict
from pathlib import Path

import matplotlib
import numpy as np
import zstandard

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from leo.analysis.standard.native_pss import starlink_pss_channel_reference_hz
from leo.analysis.starlink import PilotMethod, TrajectoryObservation, fit_trajectory_bank
from leo.analysis.starlink.pss_bandwidth import PssCaptureBand, acquire_pss_band, band_template
from leo.analysis.starlink.pss_search import (
    PssBankMode,
    PssSearchOrigin,
    PssTrackAssociationConfig,
    associate_pss_timing_tracks,
)
from leo.presentation.adaptive_hop_analysis import adaptive_trajectory_configuration
from leo.storage.adaptive_hop import AdaptiveHopIqStore

BULK_ROOT = Path("/srv/bulk/leo")
OUTPUT = Path(__file__).resolve().parent
SESSION_ID = "scan-fw-d6704a759a9ec176"
COARSE_BANK_HZ = tuple(float(value) for value in range(-1_200_000, 1_200_001, 200_000))
FINE_RADIUS_HZ = 120_000
FINE_STEP_HZ = 2_000
FRAME_RATE_HZ = 750.0
PSS_BRANCH_SPACING_HZ = 1.0 / (2 * 4.4e-6)
STRONG_WINDOW_THRESHOLD = 1.20


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _analysis_directory() -> Path:
    root = BULK_ROOT / "scanner-adaptive-analysis" / SESSION_ID
    matches = []
    for directory in root.iterdir():
        paths = list(directory.glob("binding.v8.json"))
        if not paths:
            continue
        binding = json.loads(paths[0].read_text())["document"]
        if binding["configuration"]["probe_stride_ms"] == 120:
            matches.append(directory)
    if len(matches) != 1:
        raise ValueError("expected exactly one sealed 120 ms analysis")
    return matches[0]


def _load_glrt_tracks(directory: Path):
    manifest_path = directory / "metrics-manifest.v8.json"
    sealed_manifest = json.loads(manifest_path.read_text())
    manifest = sealed_manifest["document"]
    decompressor = zstandard.ZstdDecompressor()
    groups: dict[tuple[int, int], list[TrajectoryObservation]] = {}
    source: dict[str, dict] = {}
    visit_products: dict[int, dict] = {}
    for reference in manifest["visits"]:
        if reference["passed_fractional_candidate_count"] == 0:
            continue
        payload = decompressor.decompress(
            (directory / reference["relative_path"]).read_bytes(),
            max_output_size=reference["uncompressed_bytes"],
        )
        visit = json.loads(payload)["document"]
        visit_products[visit["visit_index"]] = visit
        strongest: dict[int, tuple[dict, dict]] = {}
        for probe in visit["probes"]:
            for candidate in probe["candidates"]:
                if not candidate["passed_fractional_margin_gate"]:
                    continue
                previous = strongest.get(probe["receiver_id"])
                if previous is None or candidate["fractional_margin"] > previous[1]["fractional_margin"]:
                    strongest[probe["receiver_id"]] = (probe, candidate)
        for receiver, (probe, candidate) in strongest.items():
            observation_id = (
                f"{SESSION_ID}:visit:{visit['visit_index']}:rx:{receiver}:"
                f"probe:{probe['probe_index']}:candidate:{candidate['candidate_rank']}"
            )
            observation = TrajectoryObservation(
                observation_id=observation_id,
                method=PilotMethod.GLRT64,
                sample_start=int(candidate["integer_session_sample"]),
                time_s=candidate["fractional_time_s"],
                tracking_cfo_hz=candidate["fractional_tracking_cfo_hz"],
                score=candidate["fractional_exact_score"],
                control_score=candidate["fractional_control_score"],
                margin=candidate["fractional_margin"],
            )
            groups.setdefault((visit["target_index"], receiver), []).append(observation)
            source[observation_id] = {
                "visit_index": visit["visit_index"],
                "target_index": visit["target_index"],
                "receiver_id": receiver,
                "probe_index": probe["probe_index"],
                "candidate_rank": candidate["candidate_rank"],
                "time_s": candidate["fractional_time_s"],
                "cfo_hz": candidate["fractional_tracking_cfo_hz"],
                "margin": candidate["fractional_margin"],
            }
    configuration = adaptive_trajectory_configuration(0.025)
    representatives = []
    for key, observations in groups.items():
        bank = fit_trajectory_bank(tuple(observations), configuration)
        by_id = {item.trajectory_id: item for item in bank.trajectories}
        for family in bank.families:
            track = by_id[family.representative_trajectory_id]
            margins = [source[item]["margin"] for item in track.observation_ids]
            representatives.append(
                {
                    "key": key,
                    "track": track,
                    "mean_margin": float(np.mean(margins)),
                }
            )
    representatives.sort(
        key=lambda item: (
            -item["track"].point_count,
            -(item["track"].end_s - item["track"].start_s),
            item["track"].residual_rms_hz,
            item["track"].trajectory_id,
        )
    )
    selected = representatives[:5]
    return selected, source, visit_products, sealed_manifest["sha256"], configuration.digest


def _mode_id(visit_index: int, receiver: int, frequency: float, candidate) -> str:
    identity = (
        f"pss-10m-band-mode-v1:{SESSION_ID}:{visit_index}:{receiver}:"
        f"{frequency:.9f}:{candidate.global_epoch_device_sample}"
    )
    return "sha256:" + hashlib.sha256(identity.encode()).hexdigest()


def _modes_from_search(search, *, block_index: int, center_time_s: float, receiver: int):
    modes = []
    period_s = 1.0 / FRAME_RATE_HZ
    for hypothesis in search.hypotheses:
        for candidate in hypothesis.qualified_candidates:
            windows = tuple(
                item
                for item in hypothesis.windows
                if item.candidate_index == candidate.candidate_index
            )
            strong = tuple(
                item for item in windows if item.peak_to_local_median >= STRONG_WINDOW_THRESHOLD
            )
            chosen = strong or windows
            if not chosen:
                continue
            phases = np.asarray(
                [item.frame_phase_samples / search.band.sample_rate_hz for item in chosen]
            )
            median_phase = float(np.median(phases)) % period_s
            modes.append(
                PssBankMode(
                    mode_id=_mode_id(
                        block_index,
                        receiver,
                        hypothesis.nominal_frequency_offset_hz,
                        candidate,
                    ),
                    block_index=block_index,
                    continuity_segment_index=search.continuity_segment_index,
                    projection_id=(
                        f"10m-band:{search.band.center_offset_hz:.3f}:"
                        f"{search.band.sample_rate_hz:.0f}"
                    ),
                    origin=PssSearchOrigin.INDEPENDENT_BLIND,
                    source_digest=None,
                    center_time_s=center_time_s,
                    nominal_frequency_offset_hz=hypothesis.nominal_frequency_offset_hz,
                    candidate=candidate,
                    median_frame_phase_s=median_phase,
                    window_count=len(windows),
                    strong_window_count=len(strong),
                    windows=windows,
                )
            )
    return modes


def _band(event, geometry) -> PssCaptureBand:
    actual_center = event.actual_lo_frequency_hz + event.actual_if_offset_hz
    reference = starlink_pss_channel_reference_hz(event.target.channel, event.target.edge)
    half_band = min(geometry.sample_rate_hz, geometry.bandwidth_hz) / 2
    return PssCaptureBand(
        geometry.sample_rate_hz,
        actual_center - reference,
        -half_band,
        half_band,
    )


def _iq(raw: np.ndarray, receiver: int) -> np.ndarray:
    return (
        raw[:, receiver, 0].astype(np.float32)
        + 1j * raw[:, receiver, 1].astype(np.float32)
    ).astype(np.complex64)


def _fine_frequency(iq: np.ndarray, band: PssCaptureBand, mode: PssBankMode):
    rate = band.sample_rate_hz
    template = band_template(band, mode.nominal_frequency_offset_hz).samples
    period = rate / FRAME_RATE_HZ
    epoch = mode.candidate.epoch_sample
    count = math.ceil((len(iq) - epoch) / period)
    starts = np.rint(epoch + np.arange(count) * period).astype(np.int64)
    starts = starts[(starts >= 0) & (starts + len(template) <= len(iq))]
    bank = np.arange(
        mode.nominal_frequency_offset_hz - FINE_RADIUS_HZ,
        mode.nominal_frequency_offset_hz + FINE_RADIUS_HZ + FINE_STEP_HZ,
        FINE_STEP_HZ,
    )
    times = np.arange(len(template), dtype=float) / rate
    windows = np.asarray([iq[start : start + len(template)] for start in starts])
    energy = np.sum(np.abs(windows) ** 2, axis=1)
    scores = []
    for frequency in bank:
        conditioned = template * np.exp(2j * np.pi * frequency * times)
        correlations = windows @ np.conj(conditioned)
        scores.append(float(np.mean(np.abs(correlations) ** 2 / np.maximum(energy, 1e-30))))
    scores = np.asarray(scores)
    peak = int(np.argmax(scores))
    refined = float(bank[peak])
    if 0 < peak < len(bank) - 1 and np.all(scores[peak - 1 : peak + 2] > 0):
        left, center, right = np.log(scores[peak - 1 : peak + 2])
        denominator = left - 2 * center + right
        if denominator < 0:
            refined += float(0.5 * (left - right) / denominator * FINE_STEP_HZ)
    return refined, float(scores[peak] / max(float(np.median(scores)), 1e-30))


def _unwrap_branch(times: np.ndarray, values: np.ndarray) -> np.ndarray:
    """Lift the PSS branch using only its own recent temporal trajectory.

    A one-step nearest-neighbour unwrap can cascade after one noisy PSS CFO.
    Once three points are available, predict from a bounded twelve-point local
    linear history and choose the branch nearest that prediction instead.
    """
    if not len(values):
        return values.copy()
    output = np.empty_like(values)
    output[0] = values[0]
    for index in range(1, len(values)):
        if index >= 3:
            first = max(0, index - 12)
            local_times = times[first:index]
            local_values = output[first:index]
            center = float(np.mean(local_times))
            slope, intercept = np.polyfit(local_times - center, local_values, 1)
            predicted = float(intercept + slope * (times[index] - center))
        else:
            predicted = output[index - 1]
        output[index] = values[index] + round(
            (predicted - values[index]) / PSS_BRANCH_SPACING_HZ
        ) * PSS_BRANCH_SPACING_HZ
    return output


def _linear_fit(times: np.ndarray, values: np.ndarray):
    center = float(np.mean(times))
    design = np.column_stack((times - center, np.ones(len(times))))
    coefficients, *_ = np.linalg.lstsq(design, values, rcond=None)
    weights = np.ones(len(times))
    for _ in range(20):
        residuals = values - design @ coefficients
        scale = float(np.median(np.abs(residuals - np.median(residuals))) / 0.6744897501960817)
        if not math.isfinite(scale) or scale < 1e-9:
            break
        cutoff = 1.345 * scale
        weights = np.minimum(1.0, cutoff / np.maximum(np.abs(residuals), 1e-30))
        weighted = design * np.sqrt(weights)[:, None]
        target = values * np.sqrt(weights)
        updated, *_ = np.linalg.lstsq(weighted, target, rcond=None)
        if np.max(np.abs(updated - coefficients)) < 1e-9:
            coefficients = updated
            break
        coefficients = updated
    fitted = design @ coefficients
    residuals = values - fitted
    dof = len(times) - 2
    slope_sigma = None
    if dof > 0:
        variance = float(np.sum(weights * residuals**2) / dof)
        covariance = variance * np.linalg.inv(design.T @ (weights[:, None] * design))
        slope_sigma = math.sqrt(float(covariance[0, 0]))
    return float(coefficients[0]), float(coefficients[1]), slope_sigma, residuals


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    directory = _analysis_directory()
    selected, glrt_by_id, _visits, analysis_sha256, trajectory_config_sha256 = (
        _load_glrt_tracks(directory)
    )
    store = AdaptiveHopIqStore(BULK_ROOT, read_only=True)
    session = store.inspect(SESSION_ID)
    receipt = session.manifest.receipt
    geometry = receipt.plan.geometry
    if geometry.sample_rate_hz != 10_000_000 or geometry.receiver_ids != (0, 1):
        raise ValueError("frozen source is not dual-RX 10 MS/s")
    ordinal_by_visit = {
        retained.event.visit_index: ordinal for ordinal, retained in enumerate(receipt.visits)
    }
    results = []
    point_rows = []
    with store.reader(SESSION_ID, expected=session) as reader:
        for rank, selected_track in enumerate(selected, start=1):
            glrt = selected_track["track"]
            target_index, receiver = selected_track["key"]
            observation_ids = set(glrt.observation_ids)
            glrt_rows = sorted(
                (glrt_by_id[item] for item in observation_ids), key=lambda item: item["time_s"]
            )
            all_modes = []
            mode_context = {}
            for index, row in enumerate(glrt_rows, start=1):
                ordinal = ordinal_by_visit[row["visit_index"]]
                retained, raw = reader.read_visit_ci16(ordinal)
                event = retained.event
                values = _iq(raw, receiver)
                band = _band(event, geometry)
                search = acquire_pss_band(
                    values,
                    band,
                    device_sample_start=event.valid_start_counter - receipt.terminal.first_counter,
                    continuity_segment_index=ordinal,
                    frequency_offsets_hz=COARSE_BANK_HZ,
                )
                center_time = (
                    event.valid_start_counter
                    - receipt.terminal.first_counter
                    + len(values) / 2
                ) / geometry.sample_rate_hz
                modes = _modes_from_search(
                    search,
                    block_index=row["visit_index"],
                    center_time_s=center_time,
                    receiver=receiver,
                )
                for mode in modes:
                    mode_context[mode.mode_id] = (row, ordinal, band)
                all_modes.extend(modes)
                print(
                    f"track {rank}/5 search {index}/{len(glrt_rows)} "
                    f"visit {row['visit_index']} modes {len(modes)}",
                    flush=True,
                )
            pss_tracks = associate_pss_timing_tracks(
                tuple(all_modes),
                config=PssTrackAssociationConfig(
                    minimum_block_count=6,
                    minimum_span_s=2.0,
                    maximum_tracks=8,
                    phase_inlier_radius_s=2e-6,
                    maximum_cfo_deviation_hz=150_000.0,
                    maximum_seed_modes=96,
                ),
            )
            reconstructed = sorted(
                pss_tracks,
                key=lambda item: (
                    -len(item.mode_ids),
                    -(item.time_stop_s - item.time_start_s),
                    item.rms_residual_s,
                    item.track_id,
                ),
            )
            best = reconstructed[0] if reconstructed else None
            paired = []
            if best is not None:
                for mode_id in best.mode_ids:
                    mode = next(item for item in all_modes if item.mode_id == mode_id)
                    row, ordinal, band = mode_context[mode_id]
                    _retained, raw = reader.read_visit_ci16(ordinal)
                    frequency, peak_ratio = _fine_frequency(_iq(raw, receiver), band, mode)
                    paired.append((mode, row, frequency, peak_ratio))
            paired.sort(key=lambda item: item[0].center_time_s)
            times = np.asarray([item[0].center_time_s for item in paired], dtype=float)
            raw_pss = np.asarray([item[2] for item in paired], dtype=float)
            glrt_values = np.asarray([item[1]["cfo_hz"] for item in paired], dtype=float)
            unwrapped = _unwrap_branch(times, raw_pss)
            alignment = float(np.median(glrt_values - unwrapped)) if len(paired) else None
            aligned = unwrapped + alignment if alignment is not None else unwrapped
            glrt_rate = pss_rate = pss_rate_sigma = None
            residuals = np.asarray([], dtype=float)
            if len(paired) >= 3:
                glrt_rate, _glrt_center, _glrt_sigma, _ = _linear_fit(times, glrt_values)
                pss_rate, _pss_center, pss_rate_sigma, _ = _linear_fit(times, unwrapped)
                residuals = aligned - glrt_values
            for item_index, (mode, row, frequency, peak_ratio) in enumerate(paired):
                point_rows.append(
                    {
                        "track_rank": rank,
                        "glrt_trajectory_id": glrt.trajectory_id,
                        "target_index": target_index,
                        "receiver_id": receiver,
                        "visit_index": row["visit_index"],
                        "time_s": mode.center_time_s,
                        "glrt_cfo_hz": row["cfo_hz"],
                        "glrt_margin": row["margin"],
                        "pss_mode_id": mode.mode_id,
                        "pss_coarse_cfo_hz": mode.nominal_frequency_offset_hz,
                        "pss_fine_cfo_hz": frequency,
                        "pss_unwrapped_cfo_hz": unwrapped[item_index],
                        "pss_aligned_cfo_hz": aligned[item_index],
                        "pss_minus_glrt_hz": residuals[item_index] if len(residuals) else None,
                        "pss_robust_z": mode.candidate.robust_z,
                        "pss_fine_peak_to_median": peak_ratio,
                        "pss_timing_track_residual_us": best.residuals_s[item_index] * 1e6,
                    }
                )
            results.append(
                {
                    "rank": rank,
                    "target_index": target_index,
                    "channel": target_index % 4 + 1,
                    "edge": "lower" if target_index < 4 else "upper",
                    "receiver_id": receiver,
                    "glrt": {
                        **asdict(glrt),
                        "mean_margin": selected_track["mean_margin"],
                        "span_s": glrt.end_s - glrt.start_s,
                    },
                    "pss": {
                        "qualified_mode_count": len(all_modes),
                        "associated_track_count": len(pss_tracks),
                        "reconstructed": best is not None,
                        "track_id": best.track_id if best else None,
                        "point_count": len(paired),
                        "span_s": best.time_stop_s - best.time_start_s if best else None,
                        "coverage_fraction": len(paired) / glrt.point_count,
                        "timing_rms_us": best.rms_residual_s * 1e6 if best else None,
                        "timing_max_us": best.maximum_absolute_residual_s * 1e6 if best else None,
                        "branch_alignment_hz_for_comparison_only": alignment,
                        "cfo_median_absolute_error_hz": (
                            float(np.median(np.abs(residuals))) if len(residuals) else None
                        ),
                        "cfo_rmse_hz": (
                            float(np.sqrt(np.mean(residuals**2))) if len(residuals) else None
                        ),
                        "huber_linear_cfo_rate_hz_s": pss_rate,
                        "huber_linear_cfo_rate_sigma_hz_s": pss_rate_sigma,
                    },
                    "comparison": {
                        "matched_support_glrt_huber_linear_cfo_rate_hz_s": glrt_rate,
                        "pss_minus_glrt_huber_linear_rate_hz_s": (
                            pss_rate - glrt_rate
                            if pss_rate is not None and glrt_rate is not None
                            else None
                        ),
                    },
                }
            )
            print(
                f"track {rank}/5 result: {len(paired)}/{glrt.point_count} points, "
                f"{len(pss_tracks)} PSS track(s)",
                flush=True,
            )
    store.close()
    fields = sorted({key for row in point_rows for key in row})
    with (OUTPUT / "paired-track-points.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(point_rows)
    summary = {
        "schema_version": "org.leo.research.five-glrt-tracks-pss-reconstruction/v1",
        "source": {
            "session_id": SESSION_ID,
            "capture_manifest_sha256": session.manifest_sha256,
            "analysis_manifest_sha256": analysis_sha256,
            "glrt_trajectory_configuration_sha256": trajectory_config_sha256,
        },
        "selection": {
            "policy": "top five GLRT-only trajectory-family representatives by point count, then span, then residual RMS",
            "pss_used_for_selection": False,
            "selected_track_count": 5,
        },
        "method": {
            "pss_search": "blind -1.2 to +1.2 MHz bank in 200 kHz steps on every GLRT-track support visit",
            "pss_association": "PSS-only circular frame-phase quadratic association; >=6 blocks, >=2 s, <=2 us maximum residual",
            "fine_frequency": "+/-120 kHz in 2 kHz steps around the associated PSS coarse mode",
            "frequency_branch": "PSS series unwrapped by its own rolling linear temporal continuity at 113.636 kHz spacing; one constant offset aligned to GLRT only after track reconstruction",
            "rate_fit": "separate MAD-scaled Huber linear fits on matched PSS support",
            "claim_boundary": "GLRT selects support visits; PSS independently associates timing modes within that support. Receiver CFO, not isolated spacecraft Doppler or identity.",
        },
        "results": results,
    }
    (OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    figure, axes = plt.subplots(5, 1, figsize=(13, 14), constrained_layout=True)
    for result, axis in zip(results, axes, strict=True):
        rows = [row for row in point_rows if row["track_rank"] == result["rank"]]
        glrt_track = result["glrt"]
        grid = np.linspace(glrt_track["start_s"], glrt_track["end_s"], 200)
        model = np.polyval(
            glrt_track["coefficients_hz"], grid - glrt_track["reference_time_s"]
        )
        axis.plot(grid, model / 1000, color="#222222", linewidth=1.3, label="GLRT track")
        if rows:
            axis.scatter(
                [row["time_s"] for row in rows],
                [row["pss_aligned_cfo_hz"] / 1000 for row in rows],
                color="#bd3653",
                s=25,
                label="PSS-only timing track; constant CFO offset aligned after fit",
            )
        axis.grid(alpha=0.25)
        axis.set_ylabel("CFO (kHz)")
        axis.set_title(
            f"Track {result['rank']} · CH{result['channel']}{result['edge'][0].upper()} RX{result['receiver_id']} · "
            f"PSS {result['pss']['point_count']}/{glrt_track['point_count']} points"
        )
        axis.legend(loc="best", fontsize=8)
    axes[-1].set_xlabel("Device time since capture start (s)")
    figure.suptitle(
        "Five strongest GLRT tracks: blind PSS timing reconstruction on frozen support visits"
    )
    figure.savefig(OUTPUT / "five-track-pss-reconstruction.png", dpi=170)
    plt.close(figure)
    print(json.dumps(results, indent=2), flush=True)


if __name__ == "__main__":
    main()
