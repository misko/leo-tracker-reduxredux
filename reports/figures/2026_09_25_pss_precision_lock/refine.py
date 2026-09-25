#!/usr/bin/env python3
"""Track-conditioned PSS timing and inter-frame carrier-phase refinement."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from leo.analysis.standard.native_pss import starlink_pss_channel_reference_hz
from leo.analysis.starlink.pss_bandwidth import PssCaptureBand, acquire_pss_band
from leo.storage.adaptive_hop import AdaptiveHopIqStore

BULK_ROOT = Path("/srv/bulk/leo")
SESSION_ID = "scan-fw-d6704a759a9ec176"
INPUT = Path(__file__).resolve().parents[1] / "2026_09_25_five_glrt_tracks_pss"
OUTPUT = Path(__file__).resolve().parent
FRAME_RATE_HZ = 750.0
PSS_BRANCH_SPACING_HZ = 1.0 / (2 * 4.4e-6)


def _mode_id(visit_index: int, receiver: int, frequency: float, candidate) -> str:
    identity = (
        f"pss-10m-band-mode-v1:{SESSION_ID}:{visit_index}:{receiver}:"
        f"{frequency:.9f}:{candidate.global_epoch_device_sample}"
    )
    return "sha256:" + hashlib.sha256(identity.encode()).hexdigest()


def _band(event, geometry) -> PssCaptureBand:
    center = event.actual_lo_frequency_hz + event.actual_if_offset_hz
    reference = starlink_pss_channel_reference_hz(event.target.channel, event.target.edge)
    half = min(geometry.sample_rate_hz, geometry.bandwidth_hz) / 2
    return PssCaptureBand(geometry.sample_rate_hz, center - reference, -half, half)


def _iq(raw: np.ndarray, receiver: int) -> np.ndarray:
    return (
        raw[:, receiver, 0].astype(np.float32)
        + 1j * raw[:, receiver, 1].astype(np.float32)
    ).astype(np.complex64)


def _circular(values: np.ndarray, reference: float, period: float) -> np.ndarray:
    return (values - reference + period / 2) % period - period / 2


def _huber_line(times: np.ndarray, values: np.ndarray):
    center = float(np.mean(times))
    design = np.column_stack((times - center, np.ones(len(times))))
    coefficients, *_ = np.linalg.lstsq(design, values, rcond=None)
    weights = np.ones(len(times))
    for _ in range(20):
        residuals = values - design @ coefficients
        scale = float(np.median(np.abs(residuals - np.median(residuals))) / 0.6744897501960817)
        if not math.isfinite(scale) or scale < 1e-15:
            break
        cutoff = 1.345 * scale
        weights = np.minimum(1.0, cutoff / np.maximum(np.abs(residuals), 1e-30))
        weighted = design * np.sqrt(weights)[:, None]
        target = values * np.sqrt(weights)
        updated, *_ = np.linalg.lstsq(weighted, target, rcond=None)
        if np.max(np.abs(updated - coefficients)) < 1e-12:
            coefficients = updated
            break
        coefficients = updated
    residuals = values - design @ coefficients
    dof = len(times) - 2
    sigma = None
    if dof > 0:
        variance = float(np.sum(weights * residuals**2) / dof)
        covariance = variance * np.linalg.inv(design.T @ (weights[:, None] * design))
        sigma = math.sqrt(float(covariance[0, 0]))
    return float(coefficients[0]), float(coefficients[1]), sigma, residuals


def _visit_timing(windows, rate: float):
    period = rate / FRAME_RATE_HZ
    phases = np.asarray([item.frame_phase_samples for item in windows], dtype=float)
    times = np.asarray([item.fractional_global_device_sample / rate for item in windows])
    reference = float(np.median(phases))
    residual_s = _circular(phases, reference, period) / rate
    slope, intercept, _sigma, fit_residuals = _huber_line(times, residual_s)
    center_phase = (reference + intercept * rate) % period

    split = []
    for parity in (0, 1):
        chosen = np.arange(len(times)) % 2 == parity
        if np.count_nonzero(chosen) < 3:
            split.append(None)
            continue
        _split_slope, split_intercept, _split_sigma, _ = _huber_line(
            times[chosen], residual_s[chosen]
        )
        split.append((reference + split_intercept * rate) % period)
    split_difference_s = None
    if split[0] is not None and split[1] is not None:
        split_difference_s = float(_circular(np.asarray([split[0]]), split[1], period)[0] / rate)
    return {
        "center_phase_samples": float(center_phase),
        "timing_rate_s_s": slope,
        "frame_residual_mad_ns": float(
            np.median(np.abs(fit_residuals - np.median(fit_residuals))) * 1e9
        ),
        "split_even_odd_difference_ns": (
            split_difference_s * 1e9 if split_difference_s is not None else None
        ),
    }


def _phase_cfo(windows, rate: float, coarse_hz: float):
    times = np.asarray([item.fractional_global_device_sample / rate for item in windows])
    phase = np.unwrap(
        2 * np.pi * np.asarray([item.correlation_phase_cycles for item in windows])
    ) / (2 * np.pi)
    slope_modulo_hz, _intercept, sigma_hz, residual_cycles = _huber_line(times, phase)
    return {
        "base_cfo_hz": coarse_hz + slope_modulo_hz,
        "modulo_residual_hz": slope_modulo_hz,
        "slope_sigma_hz": sigma_hz,
        "phase_residual_rms_cycles": float(np.sqrt(np.mean(residual_cycles**2))),
    }


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    prior = json.loads((INPUT / "summary.json").read_text())
    source_rows = list(csv.DictReader((INPUT / "paired-track-points.csv").open()))
    by_track = {
        result["rank"]: [row for row in source_rows if int(row["track_rank"]) == result["rank"]]
        for result in prior["results"]
        if result["pss"]["reconstructed"]
    }
    store = AdaptiveHopIqStore(BULK_ROOT, read_only=True)
    session = store.inspect(SESSION_ID)
    receipt = session.manifest.receipt
    geometry = receipt.plan.geometry
    ordinal_by_visit = {
        retained.event.visit_index: ordinal for ordinal, retained in enumerate(receipt.visits)
    }
    output_rows = []
    with store.reader(SESSION_ID, expected=session) as reader:
        for rank, rows in sorted(by_track.items()):
            rows.sort(key=lambda item: float(item["time_s"]))
            for index, row in enumerate(rows, start=1):
                visit_index = int(row["visit_index"])
                receiver = int(row["receiver_id"])
                coarse = float(row["pss_coarse_cfo_hz"])
                ordinal = ordinal_by_visit[visit_index]
                retained, raw = reader.read_visit_ci16(ordinal)
                event = retained.event
                search = acquire_pss_band(
                    _iq(raw, receiver),
                    _band(event, geometry),
                    device_sample_start=event.valid_start_counter - receipt.terminal.first_counter,
                    continuity_segment_index=ordinal,
                    frequency_offsets_hz=(coarse,),
                )
                matches = []
                for hypothesis in search.hypotheses:
                    for candidate in hypothesis.qualified_candidates:
                        if _mode_id(visit_index, receiver, coarse, candidate) == row["pss_mode_id"]:
                            windows = tuple(
                                item
                                for item in hypothesis.windows
                                if item.candidate_index == candidate.candidate_index
                            )
                            matches.append((candidate, windows))
                if len(matches) != 1:
                    raise ValueError(f"could not reproduce PSS mode {row['pss_mode_id']}")
                candidate, windows = matches[0]
                strong = tuple(item for item in windows if item.peak_to_local_median >= 1.20)
                chosen = strong or windows
                timing = _visit_timing(chosen, geometry.sample_rate_hz)
                carrier = _phase_cfo(chosen, geometry.sample_rate_hz, coarse)
                output_rows.append(
                    {
                        "track_rank": rank,
                        "visit_index": visit_index,
                        "time_s": float(row["time_s"]),
                        "glrt_cfo_hz": float(row["glrt_cfo_hz"]),
                        "prior_pss_cfo_hz": float(row["pss_unwrapped_cfo_hz"]),
                        "pss_coarse_cfo_hz": coarse,
                        "frame_count": len(chosen),
                        "robust_z": candidate.robust_z,
                        **timing,
                        **carrier,
                    }
                )
                print(f"track {rank} precision {index}/{len(rows)}", flush=True)
    store.close()

    track_results = []
    for result in prior["results"]:
        rank = result["rank"]
        rows = [row for row in output_rows if row["track_rank"] == rank]
        if not rows:
            continue
        rows.sort(key=lambda item: item["time_s"])
        times = np.asarray([row["time_s"] for row in rows])
        prior_cfo = np.asarray([row["prior_pss_cfo_hz"] for row in rows])
        prior_rate, prior_center, _prior_sigma, _ = _huber_line(times, prior_cfo)
        time_center = float(np.mean(times))
        predicted = prior_center + prior_rate * (times - time_center)
        precise = np.asarray(
            [
                row["base_cfo_hz"]
                + round((prediction - row["base_cfo_hz"]) / FRAME_RATE_HZ) * FRAME_RATE_HZ
                for row, prediction in zip(rows, predicted, strict=True)
            ]
        )
        glrt = np.asarray([row["glrt_cfo_hz"] for row in rows])
        alignment = float(np.median(glrt - precise))
        residual = precise + alignment - glrt
        precise_rate, _center, precise_sigma, _ = _huber_line(times, precise)
        glrt_rate, _center, _sigma, _ = _huber_line(times, glrt)
        for row, value, error in zip(rows, precise, residual, strict=True):
            row["precise_pss_cfo_hz"] = value
            row["precise_aligned_pss_minus_glrt_hz"] = error
        split = np.asarray(
            [
                row["split_even_odd_difference_ns"]
                for row in rows
                if row["split_even_odd_difference_ns"] is not None
            ]
        )
        track_results.append(
            {
                "track_rank": rank,
                "point_count": len(rows),
                "median_frame_count": float(np.median([row["frame_count"] for row in rows])),
                "timing_split_median_absolute_ns": float(np.median(np.abs(split))),
                "timing_split_rms_ns": float(np.sqrt(np.mean(split**2))),
                "frame_timing_residual_mad_median_ns": float(
                    np.median([row["frame_residual_mad_ns"] for row in rows])
                ),
                "carrier_phase_slope_sigma_median_hz": float(
                    np.median([row["slope_sigma_hz"] for row in rows])
                ),
                "constant_alignment_hz_for_comparison_only": alignment,
                "precise_cfo_median_absolute_error_hz": float(np.median(np.abs(residual))),
                "precise_cfo_rmse_hz": float(np.sqrt(np.mean(residual**2))),
                "glrt_huber_rate_hz_s": glrt_rate,
                "prior_pss_huber_rate_hz_s": prior_rate,
                "precise_pss_huber_rate_hz_s": precise_rate,
                "precise_pss_rate_sigma_hz_s": precise_sigma,
                "precise_pss_minus_glrt_rate_hz_s": precise_rate - glrt_rate,
            }
        )
    fields = sorted({key for row in output_rows for key in row})
    with (OUTPUT / "precision-lock-points.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(output_rows)
    summary = {
        "schema_version": "org.leo.research.pss-track-conditioned-precision-lock/v1",
        "source": {
            "session_id": SESSION_ID,
            "capture_manifest_sha256": session.manifest_sha256,
            "reconstruction_summary_sha256": "sha256:"
            + hashlib.sha256((INPUT / "summary.json").read_bytes()).hexdigest(),
        },
        "method": {
            "timing": "per-visit robust linear fit to fractional PSS frame phases; even/odd frame split repeatability",
            "carrier": "robust inter-frame PSS correlation-phase slope, modulo 750 Hz, lifted by the PSS-only prior trajectory",
            "glrt_use": "comparison only after PSS timing association and PSS-only carrier branch lift",
            "claim_boundary": "template-relative timing and receiver CFO; not calibrated absolute time, satellite identity, or isolated spacecraft Doppler",
        },
        "results": track_results,
    }
    (OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    figure, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    for result, axis in zip(track_results, axes.flat, strict=True):
        rows = [row for row in output_rows if row["track_rank"] == result["track_rank"]]
        times = np.asarray([row["time_s"] for row in rows])
        errors = np.asarray([row["precise_aligned_pss_minus_glrt_hz"] for row in rows])
        split = np.asarray([row["split_even_odd_difference_ns"] for row in rows])
        axis.scatter(times, errors / 1000, s=24, color="#287da1", label="phase-refined CFO error")
        twin = axis.twinx()
        twin.scatter(times, split, s=15, color="#bd3653", alpha=0.55, label="even-odd timing")
        axis.axhline(0, color="#222222", linewidth=1)
        axis.set_title(f"Track {result['track_rank']} · {len(rows)} visits")
        axis.set_xlabel("Device time (s)")
        axis.set_ylabel("PSS - GLRT CFO (kHz)", color="#287da1")
        twin.set_ylabel("even - odd timing (ns)", color="#bd3653")
        axis.grid(alpha=0.2)
    figure.suptitle("Track-conditioned PSS precision lock: carrier error and timing repeatability")
    figure.savefig(OUTPUT / "pss-precision-lock.png", dpi=170)
    plt.close(figure)
    print(json.dumps(track_results, indent=2), flush=True)


if __name__ == "__main__":
    main()
