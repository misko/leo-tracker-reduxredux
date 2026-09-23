"""Audit every published GLRT candidate, before dual-receiver phase matching."""

import gzip
import json
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt

from leo.application.adaptive_dual_rx_phase_v2 import _phase_blind_pairs
from leo.scanner.host_adaptive_products import bind_actual_visit_analysis
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore

SESSION = "scan-hop-28d7592ea614f624"
OUT = Path("reports/figures/2026_09_23_scan_glrt_multiplicity")
COLORS = {1: "#0072B2", 2: "#E69F00", 3: "#009E73", 4: "#CC79A7"}


def main():
    root = Path("/srv/bulk/leo")
    captures = AdaptiveHopIqStore(root, read_only=True)
    analyses = AdaptiveHopAnalysisStore(root, read_only=True)
    visits, candidates = [], []
    try:
        publication = captures.inspect(SESSION)
        binding = bind_actual_visit_analysis(
            publication.manifest.receipt,
            input_manifest_sha256=publication.manifest_sha256,
            probe_stride_ms=120,
        )
        with analyses.job(binding) as job:
            manifest = job.manifest()
            if manifest is None:
                raise ValueError("missing published GLRT analysis")
            for visit in job.published_visits():
                time = (
                    visit.valid_start_counter - visit.source_origin_counter
                ) / visit.configuration.sample_rate_hz
                row = {
                    "visit_index": visit.visit_index,
                    "time_s": time,
                    "channel": visit.target.channel,
                    "receivers": {},
                    "matched_pairs": len(_phase_blind_pairs(visit)),
                }
                for receiver in (0, 1):
                    probes = [p for p in visit.probes if p.receiver_id == receiver]
                    available = [c for p in probes for c in p.candidates]
                    passed = [c for c in available if c.passed_fractional_margin_gate]
                    row["receivers"][str(receiver)] = {
                        "candidate_count": sum(p.candidate_count for p in probes),
                        "available_count": len(available),
                        "passed_count": len(passed),
                        "unavailable_count": sum(len(p.unavailable_candidates) for p in probes),
                    }
                    for probe in probes:
                        for c in probe.candidates:
                            candidates.append(
                                {
                                    "visit_index": visit.visit_index,
                                    "receiver": receiver,
                                    "channel": visit.target.channel,
                                    "time_s": time + probe.probe_start_ms / 1000,
                                    "rank": c.candidate_rank,
                                    "exact_score": c.fractional_exact_score,
                                    "control_score": c.fractional_control_score,
                                    "margin": c.fractional_margin,
                                    "passed": c.passed_fractional_margin_gate,
                                    "cfo_hz": c.fractional_tracking_cfo_hz,
                                    "epoch_samples": c.integer_epoch_sample
                                    + c.fractional_epoch_offset_samples,
                                }
                            )
                visits.append(row)
        summary = {
            "session_id": SESSION,
            "input_manifest_sha256": publication.manifest_sha256,
            "analysis_binding_sha256": binding.sha256,
            "visits": len(visits),
            "receivers": {},
        }
        for receiver in (0, 1):
            counts = [r["receivers"][str(receiver)]["passed_count"] for r in visits]
            summary["receivers"][str(receiver)] = {
                "passed_candidate_records": sum(counts),
                "dwells_with_one_or_more": sum(n >= 1 for n in counts),
                "dwells_with_two_or_more": sum(n >= 2 for n in counts),
                "count_histogram": dict(sorted(Counter(counts).items())),
            }
        summary["both_receivers_two_or_more"] = sum(
            all(r["receivers"][str(rx)]["passed_count"] >= 2 for rx in (0, 1)) for r in visits
        )
        summary["either_receiver_two_or_more"] = sum(
            any(r["receivers"][str(rx)]["passed_count"] >= 2 for rx in (0, 1)) for r in visits
        )
        summary["matched_pair_histogram"] = dict(
            sorted(Counter(r["matched_pairs"] for r in visits).items())
        )
        summary["configuration"] = manifest.model_dump(mode="json").get("configuration")
    finally:
        analyses.close()
        captures.close()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    with gzip.open(OUT / "all-candidates.json.gz", "wt") as target:
        json.dump({"visits": visits, "candidates": candidates}, target)
    fig, axes = plt.subplots(3, 2, figsize=(15, 11), sharex=True, layout="constrained")
    for receiver in (0, 1):
        values = [r for r in candidates if r["receiver"] == receiver]
        failed = [r for r in values if not r["passed"]]
        axes[0, receiver].scatter(
            [r["time_s"] for r in failed],
            [r["margin"] for r in failed],
            s=3,
            color="0.75",
            alpha=0.3,
            rasterized=True,
            label="Below gate",
        )
        for channel, color in COLORS.items():
            passed = [r for r in values if r["passed"] and r["channel"] == channel]
            axes[0, receiver].scatter(
                [r["time_s"] for r in passed],
                [r["margin"] for r in passed],
                s=6,
                color=color,
                alpha=0.55,
                rasterized=True,
                label=f"CH{channel}",
            )
            axes[1, receiver].scatter(
                [r["time_s"] for r in passed],
                [r["cfo_hz"] / 1000 for r in passed],
                s=5,
                color=color,
                alpha=0.5,
                rasterized=True,
            )
            channel_visits = [r for r in visits if r["channel"] == channel]
            axes[2, receiver].scatter(
                [r["time_s"] for r in channel_visits],
                [r["receivers"][str(receiver)]["passed_count"] for r in channel_visits],
                s=8,
                color=color,
                alpha=0.6,
            )
        axes[0, receiver].set(
            title=f"RX{receiver}: fractional GLRT margin (exact − control)", ylabel="GLRT margin"
        )
        axes[0, receiver].legend(ncol=5, fontsize=8)
        axes[0, receiver].axhline(0.025, color="0.3", linewidth=0.8, linestyle="--")
        axes[1, receiver].set(
            title="All passing candidate frequencies", ylabel="Tracking CFO (kHz)"
        )
        axes[2, receiver].set(
            title="Passing candidates per dwell, before RX matching",
            ylabel="Candidate count",
            xlabel="Elapsed scan time (seconds)",
        )
        axes[2, receiver].axhline(2, color="0.3", linewidth=0.8, linestyle="--")
    for ax in axes.flat:
        ax.set_xlim(0, 300)
        ax.grid(alpha=0.2)
    fig.suptitle(
        f"{SESSION} · full published GLRT inventory\n"
        "Colors identify RF channel · GLRT gate = 0.025 · "
        "multiple peaks are not necessarily distinct emitters"
    )
    fig.savefig(OUT / "glrt-vs-time.png", dpi=165)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
