#!/usr/bin/env python3
"""Bounded saved-IQ replay with frame-bootstrap GLRT frequency guidance."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from report_broadband_alignment import SELECTION, frozen_edge_evidence, serializable

from leo.analysis.starlink.pilot_methods import _conditioned_correlation_workspace
from leo.application.adaptive_dual_rx_phase_v2 import _phase_blind_pairs
from leo.scanner.adaptive_hop_analysis import (
    AdaptiveHopAnalysisConfigurationV1,
    analyze_adaptive_hop_visit,
)
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore


def provenance():
    root = Path(__file__).resolve().parents[1]
    files = (
        "tools/report_glrt_guided_broadband_phase.py",
        "src/leo/analysis/starlink/glrt_guided_broadband_phase.py",
        "src/leo/analysis/starlink/broadband_alignment.py",
        "src/leo/analysis/starlink/pilot_methods.py",
    )
    return {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in files}


def render(output):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = [
        json.loads(p.read_text())
        for p in sorted(output.glob("*-*.json"))
        if "synthetic" not in p.name
    ]
    fig, axes = plt.subplots(3, 2, figsize=(13, 10))
    for ax, row in zip(axes.flat, rows, strict=True):
        result = row["result"]
        model = result["map_model"]
        base = model["relative_cfo_hz"]
        guide = row["guides"]
        alias = 1 / 4.4e-6
        freq = np.array([g["relative_frequency_hz"] for g in guide])
        freq += np.round((base - freq) / alias) * alias
        times = np.array([g["sample"] / row["sample_rate_hz"] for g in guide])
        ax.errorbar(
            times * 1000,
            freq - base,
            yerr=[g["sigma_hz"] for g in guide],
            fmt="o",
            label="GLRT ±1 bootstrap SE",
        )
        t = np.linspace(0, 0.12, 121)
        for key, label in (("data_only", "Broadband"), ("map_model", "GLRT-guided")):
            m = result[key]
            ax.plot(
                t * 1000,
                m["relative_cfo_hz"]
                + m["relative_cfo_rate_hz_s"] * (t - m["reference_sample"] / row["sample_rate_hz"])
                - base,
                label=label,
            )
        if "evolution_result" in row:
            m = row["evolution_result"]["map_model"]
            ax.plot(
                t * 1000,
                m["relative_cfo_hz"]
                + m["relative_cfo_rate_hz_s"] * (t - m["reference_sample"] / row["sample_rate_hz"])
                - base,
                linestyle="--",
                label="GLRT changes + bias",
            )
        ax.axvspan(60, 120, alpha=0.1, color="grey", label="Held-out")
        ax.set(
            title=f"{row['session_id'][-6:]} / visit {row['visit_index']}",
            xlabel="Visit time (ms)",
            ylabel=f"Relative frequency − ({base:.1f} Hz)",
        )
        ax.grid(alpha=0.2)
    axes.flat[0].legend(fontsize=8)
    fig.suptitle("GLRT frequency evolution versus broadband alignment; held-out guides never fit")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(output / "glrt-frequency-guidance.png", dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    x = np.arange(len(rows))
    modes = (
        ("data_only", "Broadband", -0.18),
        ("map_model", "GLRT absolute", 0),
        ("evolution", "GLRT changes + bias", 0.18),
    )
    for key, label, offset in modes:
        models = [
            (r["evolution_result"]["map_model"] if key == "evolution" else r["result"][key])
            for r in rows
        ]
        axes[0].errorbar(
            x + offset,
            [np.degrees(m["observed_phase_rad"]) for m in models],
            yerr=[np.degrees(m["conditional_phase_standard_error_rad"]) for m in models],
            fmt="o",
            label=label,
        )
        held = [
            (
                r["evolution_result"]["held_out"]
                if key == "evolution"
                else r["result"]["data_only_held_out" if key == "data_only" else "held_out"]
            )
            for r in rows
        ]
        axes[1].plot(x + offset, [h["coherence"] for h in held], "o", label=label)
    for ax in axes:
        ax.set_xticks(x, [str(r["visit_index"]) for r in rows])
        ax.set_xlabel("Saved visit index (scan IDs in JSON)")
        ax.grid(alpha=0.2)
    axes[0].set_ylabel("RX1 − RX0 phase (degrees), conditional ±1 SE")
    axes[0].set_title("At sample 75,000; each visit's declared frequency")
    axes[1].set(title="Frozen forecast on the unseen second half", ylabel="Amplitude coherence")
    axes[1].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(output / "observed-phase-comparison.png", dpi=160)
    plt.close(fig)


def synthetic(output):
    from broadband_alignment_synthetic_cases import make_case

    from leo.analysis.starlink.glrt_guided_broadband_phase import (
        GuidePoint,
        estimate_glrt_guided_broadband_phase,
    )

    rows = []
    for name, options, bias in (
        ("clean", {}, 0),
        ("colored", {"response": True}, 0),
        ("interference", {"interference": True}, 0),
        ("biased_guide", {}, 1000),
        ("noise", {"noise_only": True}, 0),
    ):
        iq, rate, truth = make_case(**options)
        rng = np.random.default_rng(913)
        guides = [
            GuidePoint(
                t * rate,
                truth["cfo_at_visit_start_hz"]
                + truth["cfo_rate_hz_s"] * t
                + rng.normal(0, 80)
                + bias,
                80,
            )
            for t in (0.01, 0.03, 0.05)
        ]
        row = {"case": name, "truth": truth, "guide_bias_hz": bias}
        try:
            result = estimate_glrt_guided_broadband_phase(
                iq,
                rate,
                guides,
                broadband_cfo_seed_hz=truth["cfo_at_visit_start_hz"],
                reference_sample=75000,
            )
            row["result"] = serializable(result)
            m = result.map_model
            t = m.reference_sample / rate
            expected = (
                truth["phase_at_visit_start_rad"]
                + 2
                * np.pi
                * (truth["cfo_at_visit_start_hz"] * t + truth["cfo_rate_hz_s"] * t * t / 2)
                - (2 * np.pi * m.frequency_reference_hz * truth["rx1_delay_samples"] / rate)
            )
            row["phase_error_deg"] = float(
                np.degrees(np.angle(np.exp(1j * (m.observed_phase_rad - expected))))
            )
            row["delay_error_samples"] = m.effective_delay_samples - truth["rx1_delay_samples"]
            row["frequency_error_hz"] = m.relative_cfo_hz - (
                truth["cfo_at_visit_start_hz"] + truth["cfo_rate_hz_s"] * t
            )
        except ValueError as error:
            row["error"] = str(error)
        rows.append(row)
    (output / "synthetic.json").write_text(
        json.dumps({"implementation_sha256": provenance(), "cases": rows}, indent=2) + "\n"
    )


def bootstrap_frequency(correlations, acquired, seed=816):
    """Resample whole frames, retaining within-frame symbol correlation.

    Conditional on acquisition/timing/source association; uncertainty does not
    cover a wrong acquisition basin. FFT grid floor prevents zero bootstrap SE.
    """
    values = correlations.values
    if len(values) < 4:
        raise ValueError("fewer than four complete pilot frames")
    size = 16384
    grid = np.fft.fftfreq(size, correlations.symbol_step_s)
    power = abs(np.fft.fft(values, n=size, axis=1)) ** 2
    best = int(np.argmax(power.sum(axis=0)))
    period = 1 / correlations.symbol_step_s
    rng = np.random.default_rng(seed)
    peaks = np.array(
        [
            grid[np.argmax(power[rng.integers(0, len(values), len(values))].sum(axis=0))]
            for _ in range(128)
        ]
    )
    differences = (peaks - grid[best] + period / 2) % period - period / 2
    return {
        "frequency_hz": float(acquired + grid[best]),
        "sigma_hz": float(max(np.std(differences, ddof=1), period / size / np.sqrt(12))),
        "frame_count": len(values),
        "bootstrap_error_quantiles_hz": np.quantile(differences, [0.025, 0.975]).tolist(),
    }


def extract_guides(source, index, iq):
    rate = source.receipt.plan.geometry.sample_rate_hz
    visit = analyze_adaptive_hop_visit(
        source,
        index,
        configuration=AdaptiveHopAnalysisConfigurationV1(sample_rate_hz=rate, probe_stride_ms=20),
    )
    rows = []
    # Pair separately within each probe: the general helper otherwise deduplicates
    # sources across time, which would discard the requested frequency evolution.
    for probe_index in sorted({p.probe_index for p in visit.probes}):
        subset = visit.model_copy(
            update={"probes": tuple(p for p in visit.probes if p.probe_index == probe_index)}
        )
        pairs = _phase_blind_pairs(subset)
        if not pairs:
            continue
        # One strongest phase-blind shared candidate per disjoint probe.
        left, right, _, start = pairs[0]
        stop = start + rate * 20 // 1000
        estimates = []
        for receiver, candidate in enumerate((left, right)):
            workspace = _conditioned_correlation_workspace(
                iq[start:stop, receiver],
                rate,
                candidate.integer_epoch_sample,
                candidate.acquired_cfo_hz,
                edge=visit.target.edge,
                selected_symbols=np.arange(2, 66),
                fractional_epoch_offset_samples=candidate.fractional_epoch_offset_samples,
            )
            estimates.append(
                bootstrap_frequency(
                    workspace.select(np.arange(2, 66)),
                    candidate.acquired_cfo_hz,
                    seed=816 + receiver + probe_index * 2,
                )
            )
        rows.append(
            {
                "sample": (start + stop) / 2,
                "relative_frequency_hz": estimates[1]["frequency_hz"]
                - estimates[0]["frequency_hz"],
                "sigma_hz": float(np.hypot(*(e["sigma_hz"] for e in estimates))),
                "support_start_sample": start,
                "support_stop_sample": stop,
                "receivers": estimates,
                "source_association": "strongest phase-blind timing/frequency pair per probe",
            }
        )
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bulk-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--guides-only", action="store_true")
    parser.add_argument("--render-only", action="store_true")
    parser.add_argument("--synthetic-only", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.render_only:
        render(args.output)
        return
    if args.synthetic_only:
        synthetic(args.output)
        return
    store = AdaptiveHopIqStore(args.bulk_root, read_only=True)
    for suffix, indexes in SELECTION:
        edge = frozen_edge_evidence(suffix)
        by_visit = {r["visit_index"]: r for r in edge["visits"]}
        with AdaptiveHopAnalysisInputStore(store).source(f"scan-hop-{suffix}") as source:
            rate = source.receipt.plan.geometry.sample_rate_hz
            for index in indexes:
                path = args.output / f"{suffix}-{index}.json"
                iq = source.read_visit(index)
                guides = extract_guides(source, index, iq)
                row = {
                    "session_id": f"scan-hop-{suffix}",
                    "visit_index": index,
                    "input_manifest_sha256": source.input_manifest_sha256,
                    "sample_rate_hz": rate,
                    "guides": guides,
                    "implementation_sha256": provenance(),
                    "edge_pilot_comparison": by_visit[index]["corrected_pairs"],
                }
                if not args.guides_only:
                    from leo.analysis.starlink.glrt_guided_broadband_phase import (
                        GuidePoint,
                        estimate_glrt_guided_broadband_phase,
                    )

                    try:
                        row["result"] = serializable(
                            estimate_glrt_guided_broadband_phase(
                                iq,
                                rate,
                                [
                                    GuidePoint(
                                        g["sample"], g["relative_frequency_hz"], g["sigma_hz"]
                                    )
                                    for g in guides
                                    if g["support_stop_sample"] <= len(iq) // 2
                                ],
                                broadband_cfo_seed_hz=by_visit[index]["train_peak"]["frequency_hz"],
                                reference_sample=75000,
                            )
                        )
                        row["evolution_result"] = serializable(
                            estimate_glrt_guided_broadband_phase(
                                iq,
                                rate,
                                [
                                    GuidePoint(
                                        g["sample"], g["relative_frequency_hz"], g["sigma_hz"]
                                    )
                                    for g in guides
                                    if g["support_stop_sample"] <= len(iq) // 2
                                ],
                                broadband_cfo_seed_hz=by_visit[index]["train_peak"]["frequency_hz"],
                                reference_sample=75000,
                                fit_guide_bias=True,
                            )
                        )
                    except ValueError as error:
                        row["error"] = str(error)
                path.write_text(json.dumps(row, indent=2) + "\n")
                print(path, flush=True)


if __name__ == "__main__":
    main()
