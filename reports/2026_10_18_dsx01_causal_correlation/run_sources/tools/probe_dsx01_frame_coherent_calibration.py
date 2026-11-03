"""Label-free relative RX calibration from simultaneous coherent frame epochs."""

import json

import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import ROOT, Scan
from profile_dsx01_geographic_calibration import OUTPUT, incumbents
from prototype_dsx01_calibration_modes import choose_pair

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def fit_line(times, values):
    x = np.column_stack((np.ones(len(times)), np.asarray(times) - 150))
    y = np.asarray(values)
    coefficient = np.linalg.lstsq(x, y, rcond=None)[0]
    for _ in range(10):
        r = y - x @ coefficient
        scale = max(75.0, 1.4826 * np.median(abs(r - np.median(r))))
        weight = np.minimum(1, 2.5 * scale / np.maximum(abs(r), 1e-9))
        coefficient = np.linalg.lstsq(
            x * np.sqrt(weight[:, None]), y * np.sqrt(weight), rcond=None
        )[0]
    residual = y - x @ coefficient
    return dict(
        coefficients=coefficient,
        residual_rms_hz=float(np.sqrt(np.mean(residual**2))),
        residual=residual,
    )


def run():
    scores = json.loads(
        (ROOT / "reports/2026_10_18_dsx01_causal_repairs/glrt_scores.json").read_text()
    )
    frames = json.loads((OUTPUT / "frame_epochs.json").read_text())
    result = {}
    for case, data in frames.items():
        scan = Scan(case)
        records = data["epochs"]
        fs = data["sample_rate_hz"]
        period = data["frame_period_s"]
        bywindow = {}
        curved = {oid: i for i in scan.curved for oid in scan.tracks[i]["observation_ids"]}
        for oid, row in scores[case]["scores"].items():
            if row["fractional_margin"] < 0.1:
                continue
            bywindow.setdefault((row["channel"], row["valid_start_counter"]), {})[
                row["receiver"]
            ] = oid
        pairs = []
        for (channel, counter), ids in bywindow.items():
            if set(ids) != {1, 2}:
                continue
            a, b = [records[ids[k]] for k in (1, 2)]
            delay = (
                a["frame_phase_modulo_s"] - b["frame_phase_modulo_s"] + period / 2
            ) % period - period / 2
            pairs.append(
                dict(
                    channel=channel,
                    counter=counter,
                    observation_ids=[ids[1], ids[2]],
                    time_s=float(
                        np.mean([scores[case]["scores"][ids[k]]["context_time_s"] for k in (1, 2)])
                    ),
                    delay_s=float(delay),
                    both_original_curved=ids[1] in curved and ids[2] in curved,
                )
            )
        lag = {}
        for ch in range(1, 9):
            values = np.array([p["delay_s"] for p in pairs if p["channel"] == ch])
            edges = np.arange(-10e-6, 10.0001e-6, 1 / fs)
            hist, _ = np.histogram(values, edges)
            k = int(np.argmax(hist))
            center = float((edges[k] + edges[k + 1]) / 2)
            close = values[abs(values - center) <= 2 / fs]
            lag[ch] = dict(
                lag_s=float(np.median(close)) if len(close) >= 5 else None,
                near_mode_pairs=len(close),
                all_pairs=len(values),
            )
        for pair in pairs:
            offset = lag[pair["channel"]]["lag_s"]
            pair["frame_coherent"] = offset is not None and abs(pair["delay_s"] - offset) <= 2 / fs
            a, b = [scores[case]["scores"][oid] for oid in pair["observation_ids"]]
            raw = a["measured_cfo_hz"] - b["measured_cfo_hz"]
            alias_period = 1 / 4.4e-6
            pair["folded_RX1_minus_RX2_hz"] = float(
                (raw + alias_period / 2) % alias_period - alias_period / 2
            )
        summary = {}
        _, incumbent = choose_pair(incumbents(case, "receiver_smooth"))
        state = incumbent["c0"]["state"]
        for band in (0, 1):
            use = [
                p
                for p in pairs
                if p["frame_coherent"]
                and p["both_original_curved"]
                and int(p["channel"] > 4) == band
            ]
            times = np.array([p["time_s"] for p in use])
            y = np.array([p["folded_RX1_minus_RX2_hz"] for p in use])
            if len(use) < 5:
                summary[band] = dict(points=len(use), supported=False)
                continue
            order = np.argsort(times)
            times, y = times[order], y[order]
            y = np.unwrap(y * (2 * np.pi / alias_period)) * alias_period / (2 * np.pi)
            fitted = fit_line(times, y)
            beta = state["beta"]
            old = np.array([beta[band] - beta[2 + band], (beta[4 + band] - beta[6 + band]) / 150])
            # Offsets are modulo the native alias period; choose the equivalent
            # branch nearest the completed blind incumbent for comparison only.
            old[0] += round((fitted["coefficients"][0] - old[0]) / alias_period) * alias_period
            summary[band] = dict(
                points=len(use),
                span_s=float(np.ptp(times)),
                channels=sorted({p["channel"] for p in use}),
                independent_curved_tracks=len(
                    {curved[oid] for p in use for oid in p["observation_ids"]}
                ),
                relative_offset_hz=float(fitted["coefficients"][0]),
                relative_rate_hz_s=float(fitted["coefficients"][1]),
                fitted_line_rms_hz=fitted["residual_rms_hz"],
                incumbent_linear_offset_hz=float(old[0]),
                incumbent_relative_rate_hz_s=float(old[1]),
                old_minus_new_relative_rate_hz_s=float(old[1] - fitted["coefficients"][1]),
                supported=len(use) >= 20
                and np.ptp(times) >= 60
                and len({p["channel"] for p in use}) >= 2,
            )
        result[case] = dict(
            delay_modes_by_channel=lag,
            relative_calibration_by_band=summary,
            pairs=pairs,
            no_satellite_identity_TLE_or_GPS_used_to_choose_pairs_or_fit_calibration=True,
            minimum_GLRT_margin=0.1,
            delay_mode_search_us=[-10, 10],
            delay_gate_samples=2,
            timing_coherence_is_additional_source_evidence_not_proof_of_satellite_ID=True,
            comparison_radio_state_only_from_completed_blind_incumbent=True,
        )
        print(case, summary, flush=True)
    write(OUTPUT / "frame_coherent_calibration.json", result)
    case = "DSX01-S05"
    fig, axes = plt.subplots(2, 2, figsize=(15, 9), constrained_layout=True)
    data = result[case]
    for p in data["pairs"]:
        color = "tab:blue" if p["frame_coherent"] else "0.7"
        axes[0, 0].plot(p["time_s"], p["delay_s"] * 1e6, ".", color=color, markersize=2)
        if p["frame_coherent"] and p["both_original_curved"]:
            b = int(p["channel"] > 4)
            axes[1, b].plot(p["time_s"], p["folded_RX1_minus_RX2_hz"], ".", markersize=3)
    axes[0, 0].set(
        xlabel="Elapsed time (s)",
        ylabel="RX1 − RX2 frame phase (µs)",
        title="Simultaneous same-channel probe pairs",
        ylim=(-20, 20),
    )
    axes[0, 1].hist([p["delay_s"] * 1e6 for p in data["pairs"]], bins=np.linspace(-10, 10, 101))
    axes[0, 1].set(xlabel="RX1 − RX2 frame phase (µs)", ylabel="Pairs")
    for b in (0, 1):
        axes[1, b].set(
            xlabel="Elapsed time (s)",
            ylabel="Folded CFO RX1 − RX2 (Hz)",
            title=f"Band {b}: coherent frames, both raw-curved",
        )
    fig.savefig(OUTPUT / "frame_coherent_calibration.png", dpi=160)
    plt.close(fig)
    return result


if __name__ == "__main__":
    run()
