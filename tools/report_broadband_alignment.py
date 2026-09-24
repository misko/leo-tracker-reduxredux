#!/usr/bin/env python3
"""Reproduce full captured-band RX alignment on bounded immutable saved visits."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np
from broadband_alignment_synthetic_cases import make_case

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.analysis.starlink.broadband_alignment import estimate_broadband_alignment  # noqa: E402
from leo.analysis.starlink.broadband_phase_tracking import frequency_held_out_tracking  # noqa: E402
from leo.contracts.digests import canonical_json_bytes, sha256_digest  # noqa: E402
from leo.storage.adaptive_hop import AdaptiveHopIqStore  # noqa: E402
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIGURES = ROOT / "reports/figures"
SELECTION = (
    ("6adcb067e2dbce43", (1354, 1461, 1713)),
    ("e46d3aba244cf641", (376, 588)),
    ("34c0b0e1ae062f97", (678,)),
)


def implementation_digests():
    paths = (
        "src/leo/analysis/starlink/broadband_alignment.py",
        "src/leo/analysis/starlink/broadband_phase_tracking.py",
        "tools/report_broadband_alignment.py",
        "tools/broadband_alignment_synthetic_cases.py",
    )
    return {
        path: "sha256:" + hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths
    }


def serializable(value):
    if dataclasses.is_dataclass(value):
        return serializable(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {str(k): serializable(v) for k, v in value.items()}
    if isinstance(value, (tuple, list, np.ndarray)):
        return [serializable(v) for v in value]
    if isinstance(value, (complex, np.complexfloating)):
        return {"real": float(value.real), "imag": float(value.imag)}
    if isinstance(value, np.generic):
        return serializable(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def frozen_edge_evidence(suffix):
    if suffix == "6adcb067e2dbce43":
        path = (
            FIGURES
            / "2026_09_21_recent6ad_dual_rx_phase"
            / (f"scan-hop-{suffix}-raw-phase20-v1.json")
        )
    else:
        path = (
            FIGURES / "2026_09_21_recent8h_phase_replay" / (f"scan-hop-{suffix}.raw-coherence.json")
        )
    document = json.loads(path.read_text())
    body = {k: v for k, v in document.items() if k != "evidence_sha256"}
    if sha256_digest(canonical_json_bytes(body)) != document["evidence_sha256"]:
        raise ValueError("frozen edge evidence digest mismatch")
    return document


def run(bulk_root, output):
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for suffix, indexes in SELECTION:
        session = f"scan-hop-{suffix}"
        edge = frozen_edge_evidence(suffix)
        by_visit = {r["visit_index"]: r for r in edge["visits"]}
        store = AdaptiveHopIqStore(bulk_root, read_only=True)
        try:
            capture = store.inspect(session)
            with AdaptiveHopAnalysisInputStore(store).source(session) as source:
                rate = source.receipt.plan.geometry.sample_rate_hz
                for index in indexes:
                    iq = source.read_visit(index)
                    seed = by_visit[index]["train_peak"]["frequency_hz"]
                    try:
                        fitted = estimate_broadband_alignment(
                            iq,
                            rate,
                            receiver_cfo_seed_hz=seed,
                            cfo_search_half_width_hz=2_000,
                        )
                        result = serializable(fitted)
                        try:
                            result["frequency_held_out_tracking"] = frequency_held_out_tracking(
                                iq, rate, fitted.model
                            )
                        except ValueError as error:
                            result["frequency_held_out_tracking"] = {
                                "state": "unavailable",
                                "reason": str(error),
                            }
                    except ValueError as error:
                        result = {"state": "unavailable", "reason": str(error)}
                    comparisons = []
                    if "model" in result:
                        model = result["model"]
                        for pair in by_visit[index]["corrected_pairs"]:
                            predicted = (
                                model["relative_cfo_hz"]
                                + model["relative_cfo_rate_hz_s"]
                                * (pair["center_sample"] - model["reference_sample"])
                                / rate
                            )
                            comparisons.append(
                                {
                                    "edge_center_sample": pair["center_sample"],
                                    "edge_relative_frequency_hz": pair["relative_frequency_hz"],
                                    "broadband_frequency_at_edge_center_hz": predicted,
                                    "broadband_minus_edge_frequency_hz": predicted
                                    - pair["relative_frequency_hz"],
                                    "edge_pilot_resultant_not_broadband_coherence": pair[
                                        "resultant_length"
                                    ],
                                    "edge_conditional_phase_standard_error_deg": pair[
                                        "phase_standard_error_deg"
                                    ],
                                    "phase_comparison": (
                                        "not equated: pilot source-specific phase and composite "
                                        "broadband transfer have different frequency support"
                                    ),
                                }
                            )
                    row = {
                        "session_id": session,
                        "visit_index": index,
                        "input_manifest_sha256": capture.manifest_sha256,
                        "edge_evidence_sha256": edge["evidence_sha256"],
                        "sample_rate_hz": rate,
                        "sample_count": len(iq),
                        "training_seed_source": "frozen first-half broadband cross ambiguity",
                        "edge_pilot_comparison": by_visit[index]["corrected_pairs"],
                        "frequency_comparison_at_same_sample": comparisons,
                        "alignment": result,
                    }
                    local_rows = []
                    window_samples = round(0.020 * rate)
                    for start in range(0, len(iq) - window_samples + 1, window_samples):
                        try:
                            local = serializable(
                                estimate_broadband_alignment(
                                    iq[start : start + window_samples],
                                    rate,
                                    receiver_cfo_seed_hz=seed,
                                    cfo_search_half_width_hz=2_000,
                                    block_samples=1024,
                                )
                            )
                        except ValueError as error:
                            local = {"state": "unavailable", "reason": str(error)}
                        local_rows.append({"start_sample": start, "alignment": local})
                    row["local_tracking"] = {
                        "window_ms": 20,
                        "training_ms": 10,
                        "held_out_ms": 10,
                        "interpretation": (
                            "refits each local first half; this is short-horizon tracking, "
                            "not the globally held-out second half experiment"
                        ),
                        "rows": local_rows,
                    }
                    rows.append(row)
                    print(json.dumps({"session": session, "visit": index}), flush=True)
        finally:
            store.close()
    document = {
        "schema_version": 1,
        "kind": "full_captured_bandwidth_relative_alignment_research",
        "selection": (
            "three lower-edge longest-track visits, two upper-edge visits, "
            "one two-source candidate; selected before broadband outcomes"
        ),
        "geometric_phase_claimed": False,
        "implementation_sha256": implementation_digests(),
        "configuration": {
            "training_fraction": 0.5,
            "global_fft_samples": 4096,
            "local_window_ms": 20,
            "local_fft_samples": 1024,
            "cfo_search_half_width_hz": 2000,
            "maximum_delay_samples": 8,
            "channel_smoothing_bins": 31,
            "temporal_model_selection": "quadratic only if internal forecast RMS improves 20%",
            "tracking_frequency_groups_bins": 64,
            "tracking_group_guard_bins": 4,
        },
        "rows": rows,
    }
    document["evidence_sha256"] = sha256_digest(canonical_json_bytes(document))
    (output / "recorded-alignment.json").write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n"
    )
    return document


def synthetic(output):
    rows = []
    for name, options in (
        ("known_delay_phase_chirp", {}),
        ("colored_response", {"response": True}),
        ("independent_interference", {"interference": True}),
        ("noise_only", {"noise_only": True}),
    ):
        iq, rate, truth = make_case(**options)
        try:
            result = serializable(
                estimate_broadband_alignment(
                    iq,
                    rate,
                    receiver_cfo_seed_hz=truth["cfo_at_visit_start_hz"],
                    cfo_search_half_width_hz=2_000,
                )
            )
        except ValueError as error:
            result = {"state": "unavailable", "reason": str(error)}
        recovery = None
        if "model" in result:
            model = result["model"]
            t = model["reference_sample"] / rate
            expected_cfo = truth["cfo_at_visit_start_hz"] + truth["cfo_rate_hz_s"] * t
            expected_phase = (
                truth["phase_at_visit_start_rad"]
                + 2
                * np.pi
                * (truth["cfo_at_visit_start_hz"] * t + truth["cfo_rate_hz_s"] * t**2 / 2)
                - 2 * np.pi * model["frequency_reference_hz"] * truth["rx1_delay_samples"] / rate
            )
            recovery = {
                "delay_error_samples": model["fractional_delay_samples"]
                - truth["rx1_delay_samples"],
                "frequency_error_hz": model["relative_cfo_hz"] - expected_cfo,
                "drift_error_hz_s": model["relative_cfo_rate_hz_s"] - truth["cfo_rate_hz_s"],
                "wrapped_phase_error_deg": float(
                    np.degrees(np.angle(np.exp(1j * (model["phase_rad"] - expected_phase))))
                ),
                "phase_error_interpretation": (
                    "relative to injected delay/carrier phase; nonlinear channel projection "
                    "also contributes in the colored-response case"
                ),
            }
        rows.append({"case": name, "truth": truth, "alignment": result, "recovery": recovery})
    document = {
        "schema_version": 1,
        "implementation_sha256": implementation_digests(),
        "rows": rows,
    }
    document["evidence_sha256"] = sha256_digest(canonical_json_bytes(document))
    (output / "synthetic-alignment.json").write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n"
    )
    return document


def render(document, output, prefix):
    usable = [r for r in document["rows"] if "model" in r["alignment"]]
    if not usable:
        return
    figure, axes = plt.subplots(len(usable), 3, figsize=(17, 3.4 * len(usable)), squeeze=False)
    for row, panels in zip(usable, axes, strict=True):
        alignment = row["alignment"]
        model = alignment["model"]
        label = row.get("case", f"{row.get('session_id', '')[-16:]} / {row.get('visit_index', '')}")
        freq = np.array(alignment["training_frequency_hz"])
        coherence = np.array(alignment["training_bin_coherence"])
        physical = np.array(alignment["training_physical_overlap_mask"], dtype=bool)
        selected = np.isin(freq, model["frequency_hz"])
        panels[0].plot(freq / 1e6, coherence, lw=0.5, color="0.6", label="all bins")
        panels[0].scatter(freq[selected] / 1e6, coherence[selected], s=2, label="training-selected")
        panels[0].fill_between(
            freq / 1e6,
            0,
            1,
            where=~physical,
            color="red",
            alpha=0.1,
            label="outside recorded overlap",
        )
        panels[0].set(
            title=label,
            xlabel="RX0 baseband frequency (MHz)",
            ylabel="Training coherence",
            ylim=(0, 1),
        )
        phase = np.array(alignment["training_cross_phase_rad"])
        panels[1].scatter(freq[selected] / 1e6, np.degrees(phase[selected]), s=2)
        line = model["phase_rad"] - 2 * np.pi * (freq - model["frequency_reference_hz"]) * model[
            "fractional_delay_samples"
        ] / row.get("sample_rate_hz", row.get("truth", {}).get("sample_rate_hz", 2_500_000))
        panels[1].plot(
            freq[physical] / 1e6,
            np.degrees(np.angle(np.exp(1j * line[physical]))),
            lw=0.8,
            color="orange",
            label="effective delay + phase",
        )
        panels[1].set(
            xlabel="RX0 baseband frequency (MHz)",
            ylabel="Cross-spectrum phase (degrees)",
            ylim=(-185, 185),
        )
        names = ["Raw", "Train aligned", "Held aligned", "Held wrong-time"]
        vals = [
            alignment["held_out"]["raw_coherence"],
            alignment["training"]["corrected_coherence"],
            alignment["held_out"]["corrected_coherence"],
            alignment["held_out"]["wrong_time_coherence"],
        ]
        panels[2].bar(names, vals, color=["gray", "steelblue", "seagreen", "indianred"])
        panels[2].tick_params(axis="x", rotation=20)
        panels[2].set(ylabel="Normalized complex coherence", ylim=(0, 1))
        held_phase = np.degrees(alignment["held_out"]["corrected_cross_phase_rad"])
        panels[2].set_title(f"Held residual phase {held_phase:.1f}°")
        for panel in panels:
            panel.grid(alpha=0.15)
    axes[0, 0].legend(fontsize=7)
    axes[0, 1].legend(fontsize=7)
    figure.suptitle(
        "Full captured-bandwidth RX alignment — training model frozen before held-out evaluation"
    )
    figure.tight_layout(rect=(0, 0, 1, 0.98))
    figure.savefig(output / f"{prefix}-alignment.png", dpi=140)
    plt.close(figure)


def render_tracking(document, output):
    rows = [
        r
        for r in document["rows"]
        if "tracked" in r["alignment"].get("frequency_held_out_tracking", {})
    ]
    figure, axes = plt.subplots(len(rows), 2, figsize=(13, 3 * len(rows)), squeeze=False)
    for row, panels in zip(rows, axes, strict=True):
        tracker = row["alignment"]["frequency_held_out_tracking"]
        time = np.asarray([b["center_sample"] for b in tracker["rows"]]) / row["sample_rate_hz"]
        phase = np.degrees([b["held_band_residual_phase_rad"] for b in tracker["rows"]])
        panels[0].scatter(1000 * time, phase, s=15)
        panels[0].axhline(0, color="gray", lw=1)
        panels[0].set(
            title=f"{row['session_id'][-16:]} / {row['visit_index']}",
            xlabel="Visit time (ms), held temporal half",
            ylabel="Held B-band residual phase (°)",
            ylim=(-180, 180),
        )
        vals = [tracker[name]["coherence"] for name in ("forecast", "tracked", "wrong_time")]
        panels[1].bar(
            ["Frozen forecast", "A-band tracked / B tested", "Wrong time"],
            vals,
            color=["gray", "seagreen", "indianred"],
        )
        panels[1].set(ylabel="B-band normalized coherence", ylim=(0, max(0.25, max(vals) * 1.2)))
        panels[1].set_title(
            f"Aggregate B phase: {np.degrees(tracker['tracked']['phase_rad']):.1f}°"
        )
        for panel in panels:
            panel.grid(alpha=0.2)
    figure.suptitle(
        "Online common-phase tracking: learn from A frequencies, test disjoint B frequencies"
    )
    figure.tight_layout(rect=(0, 0, 1, 0.98))
    figure.savefig(output / "frequency-held-tracking.png", dpi=140)
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    recorded = run(args.bulk_root, args.output)
    generated = synthetic(args.output)
    render(recorded, args.output, "recorded")
    render(generated, args.output, "synthetic")
    render_tracking(recorded, args.output)


if __name__ == "__main__":
    main()
