#!/usr/bin/env python3
"""Bounded dual-RX 10 MS/s PSS-versus-GLRT replay on frozen adaptive IQ."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

import matplotlib
import numpy as np
import zstandard

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from leo.analysis.standard.native_pss import starlink_pss_channel_reference_hz
from leo.analysis.starlink.pss_bandwidth import PssCaptureBand, acquire_pss_band, band_template
from leo.storage.adaptive_hop import AdaptiveHopIqStore

BULK_ROOT = Path("/srv/bulk/leo")
OUTPUT = Path(__file__).resolve().parent
SESSIONS = (
    ("scan-fw-d6704a759a9ec176", "2026-09-25T13:30:02.110006Z"),
    ("scan-fw-a9d727b5393aa305", "2026-09-25T13:20:01.787787Z"),
    ("scan-fw-7fbd892968965e6d", "2026-09-25T13:00:01.953871Z"),
    ("scan-fw-506bf7282490266d", "2026-09-25T12:50:02.032921Z"),
    ("scan-fw-4ae0a0f741e4a639", "2026-09-25T12:30:02.128506Z"),
    ("scan-fw-256192ae756dc7a1", "2026-09-25T12:10:02.019660Z"),
    ("scan-fw-4a512ac1d5e4faae", "2026-09-25T12:00:01.928162Z"),
    ("scan-fw-54f51a9d98ccdd37", "2026-09-25T11:50:02.065648Z"),
    ("scan-fw-438bc1098ed57bd4", "2026-09-25T11:40:02.253387Z"),
    ("scan-fw-49770ddcd1cb69ad", "2026-09-25T11:20:02.207061Z"),
)
COARSE_BANK_HZ = tuple(float(value) for value in range(-1_200_000, 1_200_001, 200_000))
FINE_RADIUS_HZ = 120_000
FINE_STEP_HZ = 2_000
EPOCH_GATE_S = 2e-6
FRAME_RATE_HZ = 750.0
PSS_SIDELOBE_BRANCH_SPACING_HZ = 1.0 / (2 * 4.4e-6)


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _analysis_directory(session_id: str) -> Path:
    root = BULK_ROOT / "scanner-adaptive-analysis" / session_id
    directories = [path for path in root.iterdir() if path.is_dir()]
    matches = []
    for directory in directories:
        bindings = list(directory.glob("binding.v8.json"))
        manifests = list(directory.glob("metrics-manifest.v8.json"))
        if len(bindings) != 1 or len(manifests) != 1:
            continue
        binding = json.loads(bindings[0].read_text())["document"]
        if binding["configuration"]["probe_stride_ms"] == 120:
            matches.append(directory)
    if len(matches) != 1:
        raise ValueError(f"expected one complete 120 ms analysis for {session_id}")
    return matches[0]


def _strongest_by_receiver(directory: Path) -> tuple[dict, dict, str]:
    manifest_path = directory / "metrics-manifest.v8.json"
    sealed = json.loads(manifest_path.read_text())
    manifest = sealed["document"]
    best: dict[int, dict] = {}
    decompressor = zstandard.ZstdDecompressor()
    for reference in manifest["visits"]:
        if reference["passed_fractional_candidate_count"] == 0:
            continue
        payload = decompressor.decompress(
            (directory / reference["relative_path"]).read_bytes(),
            max_output_size=reference["uncompressed_bytes"],
        )
        visit = json.loads(payload)["document"]
        for probe in visit["probes"]:
            receiver = probe["receiver_id"]
            for candidate in probe["candidates"]:
                if not candidate["passed_fractional_margin_gate"]:
                    continue
                row = {
                    "visit_index": visit["visit_index"],
                    "target_index": visit["target_index"],
                    "probe_index": probe["probe_index"],
                    "receiver_id": receiver,
                    **candidate,
                }
                if receiver not in best or row["fractional_margin"] > best[receiver]["fractional_margin"]:
                    best[receiver] = row
    if set(best) != {0, 1}:
        raise ValueError(f"strong passed GLRT candidates are absent in {directory.parent.name}")
    return best[0], best[1], sealed["sha256"]


def _circular_samples(a: float, b: float, period: float) -> float:
    return (a - b + period / 2) % period - period / 2


def _fine_frequency(
    iq: np.ndarray,
    band: PssCaptureBand,
    *,
    epoch_sample: int,
    coarse_cfo_hz: float,
) -> tuple[float, float, int]:
    rate = band.sample_rate_hz
    template = band_template(band, coarse_cfo_hz).samples
    period = rate / FRAME_RATE_HZ
    count = math.ceil((len(iq) - epoch_sample) / period)
    starts = np.rint(epoch_sample + np.arange(count) * period).astype(np.int64)
    starts = starts[(starts >= 0) & (starts + len(template) <= len(iq))]
    bank = np.arange(
        coarse_cfo_hz - FINE_RADIUS_HZ,
        coarse_cfo_hz + FINE_RADIUS_HZ + FINE_STEP_HZ,
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
    scores_array = np.asarray(scores)
    peak = int(np.argmax(scores_array))
    refined = float(bank[peak])
    if 0 < peak < len(bank) - 1 and np.all(scores_array[peak - 1 : peak + 2] > 0):
        left, center, right = np.log(scores_array[peak - 1 : peak + 2])
        denominator = left - 2 * center + right
        if denominator < 0:
            refined += float(0.5 * (left - right) / denominator * FINE_STEP_HZ)
    peak_to_median = float(scores_array[peak] / max(float(np.median(scores_array)), 1e-30))
    return refined, peak_to_median, len(starts)


def _replay_one(store: AdaptiveHopIqStore, session_id: str, captured_at: str) -> list[dict]:
    directory = _analysis_directory(session_id)
    selected = _strongest_by_receiver(directory)
    session = store.inspect(session_id)
    receipt = session.manifest.receipt
    geometry = receipt.plan.geometry
    if geometry.sample_rate_hz != 10_000_000 or geometry.receiver_ids != (0, 1):
        raise ValueError(f"{session_id} is not dual-RX 10 MS/s")
    ordinal_by_index = {visit.event.visit_index: ordinal for ordinal, visit in enumerate(receipt.visits)}
    rows = []
    with store.reader(session_id, expected=session) as reader:
        for glrt in selected[:2]:
            receiver = glrt["receiver_id"]
            ordinal = ordinal_by_index[glrt["visit_index"]]
            visit, raw = reader.read_visit_ci16(ordinal)
            event = visit.event
            iq = (raw[:, receiver, 0].astype(np.float32) + 1j * raw[:, receiver, 1]).astype(np.complex64)
            actual_center = event.actual_lo_frequency_hz + event.actual_if_offset_hz
            reference = starlink_pss_channel_reference_hz(event.target.channel, event.target.edge)
            half_band = min(geometry.sample_rate_hz, geometry.bandwidth_hz) / 2
            band = PssCaptureBand(
                geometry.sample_rate_hz,
                actual_center - reference,
                -half_band,
                half_band,
            )
            start = event.valid_start_counter - receipt.terminal.first_counter
            search = acquire_pss_band(
                iq,
                band,
                device_sample_start=start,
                continuity_segment_index=ordinal,
                frequency_offsets_hz=COARSE_BANK_HZ,
            )
            period = geometry.sample_rate_hz / FRAME_RATE_HZ
            glrt_sample = float(glrt["integer_session_sample"]) + glrt["fractional_epoch_offset_samples"]
            glrt_phase = glrt_sample % period
            candidates = []
            for hypothesis in search.hypotheses:
                for candidate in hypothesis.qualified_candidates:
                    error = _circular_samples(candidate.frame_phase_samples, glrt_phase, period)
                    if abs(error) <= EPOCH_GATE_S * geometry.sample_rate_hz:
                        candidates.append((candidate.robust_z, abs(error), hypothesis, candidate, error))
            base = {
                "session_id": session_id,
                "captured_at": captured_at,
                "source_manifest_sha256": session.manifest_sha256,
                "analysis_manifest_sha256": selected[2],
                "receiver_id": receiver,
                "retained_ordinal": ordinal,
                "visit_index": event.visit_index,
                "target_index": event.target_index,
                "channel": event.target.channel,
                "edge": str(event.target.edge),
                "valid_visit_ms": round(len(iq) / geometry.sample_rate_hz * 1000),
                "glrt_probe_index": glrt["probe_index"],
                "glrt_margin": glrt["fractional_margin"],
                "glrt_cfo_hz": glrt["fractional_tracking_cfo_hz"],
                "pss_detected": bool(candidates),
                "pss_aligned_mode_count": len(candidates),
            }
            if not candidates:
                rows.append({**base, "pss_cfo_hz": None, "epoch_error_samples": None})
                continue
            _, _, hypothesis, candidate, error = max(candidates, key=lambda item: (item[0], -item[1]))
            pss_cfo, fine_peak_ratio, frame_support = _fine_frequency(
                iq,
                band,
                epoch_sample=candidate.epoch_sample,
                coarse_cfo_hz=hypothesis.nominal_frequency_offset_hz,
            )
            raw_difference = pss_cfo - glrt["fractional_tracking_cfo_hz"]
            branch_lift = round(raw_difference / PSS_SIDELOBE_BRANCH_SPACING_HZ)
            branch_conditioned_difference = (
                raw_difference - branch_lift * PSS_SIDELOBE_BRANCH_SPACING_HZ
            )
            rows.append(
                {
                    **base,
                    "pss_cfo_hz": pss_cfo,
                    "pss_coarse_cfo_hz": hypothesis.nominal_frequency_offset_hz,
                    "pss_robust_z": candidate.robust_z,
                    "pss_peak_to_median": candidate.peak_to_median,
                    "pss_fine_peak_to_median": fine_peak_ratio,
                    "pss_frame_support": frame_support,
                    "epoch_error_samples": error,
                    "epoch_error_us": error / geometry.sample_rate_hz * 1e6,
                    "raw_cfo_difference_hz": raw_difference,
                    "pss_branch_lift": branch_lift,
                    "branch_conditioned_cfo_difference_hz": branch_conditioned_difference,
                }
            )
    return rows


def _write_csv(rows: list[dict]) -> None:
    fields = sorted({field for row in rows for field in row})
    with (OUTPUT / "paired-estimates.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _plots(rows: list[dict]) -> None:
    paired = [row for row in rows if row["pss_cfo_hz"] is not None]
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    colors = {0: "#2d6ea3", 1: "#8d5aa6"}
    for receiver in (0, 1):
        group = [row for row in paired if row["receiver_id"] == receiver]
        axes[0].scatter(
            [row["glrt_cfo_hz"] / 1000 for row in group],
            [row["pss_cfo_hz"] / 1000 for row in group],
            label=f"RX{receiver}", color=colors[receiver], s=48,
        )
        axes[1].scatter(
            [row["glrt_cfo_hz"] / 1000 for row in group],
            [row["raw_cfo_difference_hz"] / 1000 for row in group],
            label=f"RX{receiver}", color=colors[receiver], s=48,
        )
        axes[2].scatter(
            [row["glrt_cfo_hz"] / 1000 for row in group],
            [row["branch_conditioned_cfo_difference_hz"] / 1000 for row in group],
            label=f"RX{receiver}", color=colors[receiver], s=48,
        )
    if paired:
        values = [row["glrt_cfo_hz"] / 1000 for row in paired] + [row["pss_cfo_hz"] / 1000 for row in paired]
        lower, upper = min(values), max(values)
        axes[0].plot([lower, upper], [lower, upper], color="#333333", linewidth=1)
    axes[0].set(xlabel="GLRT CFO (kHz)", ylabel="PSS CFO (kHz)", title="Same-visit frequency estimates")
    axes[1].axhline(0, color="#333333", linewidth=1)
    axes[1].set(xlabel="GLRT CFO (kHz)", ylabel="PSS − GLRT (kHz)", title="Raw estimator difference")
    axes[2].axhline(0, color="#333333", linewidth=1)
    axes[2].set(
        xlabel="GLRT CFO (kHz)",
        ylabel="branch-conditioned PSS − GLRT (kHz)",
        title="After nearest 113.636 kHz branch lift",
    )
    for axis in axes:
        axis.grid(alpha=0.25)
        axis.legend()
    fig.suptitle("Dual-RX 10 MS/s PSS vs fractional GLRT · GLRT-selected strong visits")
    fig.tight_layout()
    fig.savefig(OUTPUT / "pss-vs-glrt-cfo.png", dpi=170)
    plt.close(fig)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    store = AdaptiveHopIqStore(BULK_ROOT, read_only=True)
    try:
        rows = []
        for index, (session_id, captured_at) in enumerate(SESSIONS, start=1):
            rows.extend(_replay_one(store, session_id, captured_at))
            print(f"[{index}/{len(SESSIONS)}] {session_id}", flush=True)
    finally:
        store.close()
    paired = [row for row in rows if row["pss_cfo_hz"] is not None]
    differences = np.asarray([row["raw_cfo_difference_hz"] for row in paired], dtype=float)
    conditioned = np.asarray(
        [row["branch_conditioned_cfo_difference_hz"] for row in paired], dtype=float
    )
    summary = {
        "schema_version": "org.leo.research.dual-rx-10msps-pss-glrt/v1",
        "cohort": {
            "selection": "ten latest figure-ready scans in the frozen 8 h snapshot; strongest passed fractional-GLRT candidate per receiver",
            "sessions": len(SESSIONS),
            "receiver_visits": len(rows),
        },
        "method": {
            "coarse_pss_bank_hz": COARSE_BANK_HZ,
            "fine_pss_radius_hz": FINE_RADIUS_HZ,
            "fine_pss_step_hz": FINE_STEP_HZ,
            "epoch_gate_us": EPOCH_GATE_S * 1e6,
            "pss_template": "published Humphreys equations 35-37, projected to the recorded 10 MHz edge slice",
            "claim_boundary": "post-hoc GLRT-selected candidate comparison; observed receiver CFO, not isolated spacecraft Doppler",
            "pss_sidelobe_branch_spacing_hz": PSS_SIDELOBE_BRANCH_SPACING_HZ,
            "branch_conditioning": "nearest PSS half-symbol-frequency sidelobe branch chosen using GLRT; not an independent absolute-frequency test",
        },
        "results": {
            "pss_epoch_aligned": len(paired),
            "pss_epoch_not_aligned": len(rows) - len(paired),
            "by_receiver": {
                f"rx{receiver}": {
                    "attempted": sum(row["receiver_id"] == receiver for row in rows),
                    "aligned": sum(row["receiver_id"] == receiver and row["pss_cfo_hz"] is not None for row in rows),
                }
                for receiver in (0, 1)
            },
            "raw_cfo_difference_hz": {
                "median_absolute": float(np.median(np.abs(differences))) if len(differences) else None,
                "rmse": float(np.sqrt(np.mean(differences**2))) if len(differences) else None,
                "median_signed": float(np.median(differences)) if len(differences) else None,
            },
            "branch_conditioned_cfo_difference_hz": {
                "median_absolute": float(np.median(np.abs(conditioned))) if len(conditioned) else None,
                "rmse": float(np.sqrt(np.mean(conditioned**2))) if len(conditioned) else None,
                "median_signed": float(np.median(conditioned)) if len(conditioned) else None,
                "maximum_absolute": float(np.max(np.abs(conditioned))) if len(conditioned) else None,
            },
        },
        "rows": rows,
    }
    _write_csv(rows)
    _plots(rows)
    (OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary["results"], indent=2))


if __name__ == "__main__":
    main()
