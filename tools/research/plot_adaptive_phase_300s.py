"""Replay corrected single-source phases and display exact paired-source evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore
from tools.research import replay_adaptive_multiscale_phase_refined as replay

DIRECTORY = replay.ROOT / "reports/figures/2026_09_23_adaptive_phase_300s"


def raw_training_offset(iq, starts, train, fs):
    """Incoherent FFT cross-product peak on whole training frames only."""
    indexes = starts[train, None] + np.arange(2048)[None, :]
    samples = iq[indexes].astype(np.complex128)
    samples -= samples.mean(axis=1, keepdims=True)
    product = samples[:, :, 1] * np.conj(samples[:, :, 0])
    spectrum = np.fft.fft(product * np.hanning(2048)[None, :], n=32768, axis=1)
    power = np.mean(abs(spectrum) ** 2, axis=0)
    peak = int(np.argmax(power))
    y = np.log(np.maximum(power[[(peak - 1) % len(power), peak, (peak + 1) % len(power)]], 1e-30))
    curvature = y[0] - 2 * y[1] + y[2]
    fraction = 0.0 if curvature == 0 else float(np.clip(0.5 * (y[0] - y[2]) / curvature, -0.5, 0.5))
    offset = float(np.fft.fftfreq(len(power), 1 / fs)[peak] + fraction * fs / len(power))
    return offset, float(power[peak] / max(float(np.median(power)), 1e-30))


def run():
    binding_path = DIRECTORY / "binding.json"
    binding = json.loads(binding_path.read_text())
    output = {
        "session_id": binding["session_id"],
        "binding_sha256": hashlib.sha256(binding_path.read_bytes()).hexdigest(),
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "description": "Single-source RX1−RX0 phase; not two-source DD or cross-retune continuity",
        "rows": [],
    }
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    try:
        with AdaptiveHopAnalysisInputStore(store).source(binding["session_id"]) as source:
            if source.input_manifest_sha256 != binding["input_manifest_sha256"]:
                raise ValueError("capture manifest changed")
            for bound in binding["rows"]:
                if not bound["sources"]:
                    continue
                ordinal = bound["iq_ordinal"]
                if source.visits[ordinal].event.visit_index != bound["visit_index"]:
                    raise ValueError("visit binding changed")
                selected = max(bound["sources"], key=lambda item: item["quality"])
                iq = source.read_visit(ordinal)
                fs = bound["sample_rate_hz"]
                replay.frontend.FS = fs
                replay.frontend.EPOCHS = {"A": selected["epoch"]}
                starts = replay.frontend.frame_starts(selected["epoch"], 0, round(0.12 * fs))
                train = replay.frontend.split_frames(len(starts), 126)
                offset, prominence = raw_training_offset(iq, starts, train, fs)
                reference = (selected["epoch"] + selected["fractional_epoch"]) / fs
                replay.frontend.MODELS = {
                    "A": (
                        (reference, 0.0, selected["rx0_acquired_cfo_hz"]),
                        (reference, 0.0, selected["rx0_acquired_cfo_hz"] + offset),
                    )
                }
                phase = replay.source_phase(iq, 120, "A", selected, bound["edge"], False)
                output["rows"].append(
                    {
                        "visit_index": bound["visit_index"],
                        "channel": bound["channel"],
                        "time_s": bound["time_s"] + 0.06,
                        "raw_train_receiver_offset_hz": offset,
                        "raw_peak_to_median_power": prominence,
                        "source": selected,
                        "phase": phase,
                    }
                )
                if len(output["rows"]) % 25 == 0:
                    print(f"Replayed {len(output['rows'])} eligible dwells", flush=True)
    finally:
        store.close()
    (DIRECTORY / "single-source-results.json").write_text(json.dumps(output, indent=2) + "\n")
    render(binding, output)


def render(binding, output):
    cached = json.loads((replay.DIRECTORY / "frame-double-difference.json").read_text())
    by_visit = {row["visit_index"]: row for row in binding["rows"]}
    double = []
    for row in cached["rows"]:
        bound = by_visit[row["visit_index"]]
        held = np.asarray(row["both_held"])
        values = np.asarray(row["before_separate_rate_removal_rad"])[held]
        weights = np.asarray(row["paired_weights"])[held]
        mean = np.average(np.exp(1j * values), weights=weights)
        double.append(
            {
                "visit_index": row["visit_index"],
                "channel": bound["channel"],
                "time_s": bound["time_s"] + float(np.mean(np.asarray(row["time_s"])[held])),
                "phase_deg": float(np.degrees(np.angle(mean))),
                "held_resultant": float(abs(mean)),
            }
        )
    (DIRECTORY / "exact-double-difference-points.json").write_text(
        json.dumps(double, indent=2) + "\n"
    )
    colors = dict(zip(range(1, 5), ("#0072B2", "#E69F00", "#009E73", "#CC79A7"), strict=True))
    fig, axes = plt.subplots(2, 1, figsize=(14, 9), sharex=True, layout="constrained")
    for channel, color in colors.items():
        rows = [r for r in output["rows"] if r["channel"] == channel and r["phase"] is not None]
        axes[0].scatter(
            [r["time_s"] for r in rows],
            [np.degrees(r["phase"]["held_phase_restored_rad"]) for r in rows],
            color=color,
            s=20,
            alpha=0.8,
            label=f"Channel {channel} (n={len(rows)})",
        )
        dd = [r for r in double if r["channel"] == channel]
        axes[1].scatter(
            [r["time_s"] for r in dd],
            [r["phase_deg"] for r in dd],
            color=color,
            s=45,
            label=f"Channel {channel} (n={len(dd)})",
        )
    axes[0].set_title(
        "Single-source RX1−RX0 phase · corrected pilots · train-fitted rate to dwell center"
    )
    axes[1].set_title(
        "Exact two-source difference · before separate source-rate removal · only 5 eligible dwells"
    )
    axes[1].text(
        0.02,
        0.06,
        "Channels 1–3 have no simultaneous two-source bindings.\n"
        "Empty regions mean unavailable measurements, not zero phase.",
        transform=axes[1].transAxes,
        fontsize=10,
    )
    for ax in axes:
        ax.set(
            xlim=(0, 300),
            ylim=(-180, 180),
            yticks=[-180, -90, 0, 90, 180],
            ylabel="Wrapped phase (degrees)",
        )
        ax.grid(alpha=0.2)
        ax.legend(ncol=4, fontsize=9, loc="upper center")
    axes[1].set_xlabel("Elapsed scan time from device sample counter (seconds)")
    fig.suptitle(
        "scan-hop-28d7592ea614f624 · 300-second adaptive scan\n"
        "RF channels 1–4, lower edge · random frame holdouts · no phase unwrapping across retunes"
    )
    fig.savefig(DIRECTORY / "phase-vs-time-300s.png", dpi=170)


if __name__ == "__main__":
    run()
