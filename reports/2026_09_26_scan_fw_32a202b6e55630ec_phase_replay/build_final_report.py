"""Assemble the audited 30-method report from persisted numerical evidence."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

R = Path(__file__).resolve().parent


def read(path):
    return json.loads((R / path).read_text())


def main():
    dense = read("dense-coverage-summary.json")
    frame = read("frame-methods/frame-method-summary.json")
    full = read("frame-methods/fullspan/fullspan-trackers.json")
    direct = read("dual-rx/dense-direct/method24-corrected-summary.json")
    response = read("dual-rx/method23-dense-relative-phase-summary.json")
    spectral = read("sync-spectral/guarded-spectral-dense-summary.json")
    cross = read("cross-dwell/summary.json")
    robust = read("frame-methods/row16-root/results.json")
    registry = read("method-registry.json")
    eval_frame = frame["split_metrics"]["evaluation"]
    ev_direct = direct["evaluation_medians"]
    spec = spectral["medians"]
    acquired = [row for row in full["rows"] if row["disposition"] == "processed"]
    evaluation = [row for row in acquired if row["split"] == "evaluation"]
    no_result = sum(row["pnt_v2"]["status"] != "complete" for row in acquired)
    eligible_long = sum(row["actual_support_ms"] >= 75 for row in acquired)
    rm = robust["summary"]["cached_even_to_odd"]["models"]
    frame_count = frame["frame_count"]
    arc_count = frame["acquired_receivers"]
    deg = 180 / math.pi
    records = []

    def row(number, scope, outcome, evidence, observable, value=None, units="", validation="", coverage=None):
        method = registry["methods"][number - 1]
        records.append({
            "method_id": method["method_id"], "approach": method["name"],
            "historical_reports": "; ".join(method["historical_report_refs"]),
            "scope": scope, "outcome": outcome, "observable": observable,
            "metric": value, "units": units, "validation": validation,
            "coverage": coverage, "evidence": evidence,
        })

    local = f"128 visits; {arc_count}/256 receiver arcs acquired; {len(evaluation)}/192 evaluation arcs"
    bounded = "8 frozen development visits / 16 receiver cases; 9 acquired"
    row(1, "552 candidate adjacent boundaries; 99 CFO-compatible; 71 evaluation", "Some adjacent-boundary continuity; no unique cross-retune phase bridge.", "cross-dwell/REPORT.md", "RX differential 2π", cross["evaluation_causal_r"], "R", "left-only boundary prediction", "71/552 evaluation-compatible edges")
    row(2, local, "Strong local fold agreement; it does not establish continuity between frames.", "frame-methods/REPORT.md", "within-frame modulo π", eval_frame["median_per_arc_held_rms_rad_mod_pi"] * deg, "degrees RMS", "even/odd-symbol agreement", f"{len(evaluation)}/192 evaluation receiver arcs")
    row(3, local, "Adjacent constant-increment prediction is substantially worse than within-frame agreement.", "frame-methods/REPORT.md", "adjacent-frame modulo π", eval_frame["median_per_arc_adjacent_rms_rad_mod_pi"] * deg, "degrees RMS", "sequential frame diagnostic")
    row(4, bounded, "Actual integrated linear CFO: 126/632 exact phase transitions accepted versus 124/632 rolled-control; no useful exact continuity advantage.", "frame-methods/actual-05-14-smoke.json", "prompt 2π", .2951 * 360, "degrees RMS", "development diagnostic; exact .2951 vs control .2919 cycles")
    row(5, bounded, "Actual phase-feedback on/off replay changes final rate by median 102.48 Hz/s; computational completion is not a phase lock or truth-frequency improvement.", "frame-methods/actual-05-14-smoke.json", "frequency-state feedback", 102.48, "Hz/s difference", "development-only matched observations")
    resets = {name: sum(row[name]["phase_reset_count"] for row in acquired) for name in ("ordinary_2pi", "causal_modulo_pi")}
    row(6, local, f"Actual full-span ordinary tracker: {resets['ordinary_2pi']} resets; {arc_count-no_result} numerical completions, {no_result} no-results. No continuous long-track phase established.", "frame-methods/fullspan/fullspan-trackers.json", "ordinary 2π", resets["ordinary_2pi"], "resets", "actual full-cohort kernel")
    row(7, f"{frame_count:,} frames on {arc_count} acquired receiver arcs", "Full 300-symbol/eight-tone Qin supports local frequency measurement; absolute CFO truth and emitter identity remain unavailable.", "frame-methods/REPORT.md", "frame-local frequency", frame["exact_margin_positive_fraction"] * 100, "% exact margin positive", "rolled control; descriptive all-frame count")
    row(8, "8 development visits: 8 complete / 8 insufficient receiver cases", "Historical channel/delay separation and binary-π batch core ran; median fitted residual about .777 rad is weak and uses future data.", "frame-methods/actual-08-smoke.json", "batch modulo π", .777 * deg, "degrees RMS", "in-sample noncausal; not held prediction")
    row(9, local, f"Modulo-π tracker reduces resets to {resets['causal_modulo_pi']}; the shorter wrap interval is not proof of unambiguous 2π phase.", "frame-methods/fullspan/fullspan-trackers.json", "causal modulo π", resets["causal_modulo_pi"], "resets", "actual symmetry-order ablation")
    row(10, local, f"PNT V1 and V2 each produce zero inner phase locks; {arc_count-no_result} numerical completions and {no_result} no-results per kernel.", "frame-methods/fullspan/fullspan-trackers.json", "five-state modulo π", 0, "qualified locks", "published inner gates retained")
    row(11, f"{eligible_long} acquired arcs with ≥75 ms raw support", "Zero inner phase locks; a pipeline requiring that gate cannot pass. No outer-gate success is imputed; shorter arcs are duration-ineligible.", "frame-methods/fullspan/fullspan-trackers.json", "production qualification", 0, "qualified locks", "necessary-gate rejection, not a fabricated outer score")
    row(12, "Actual 50/75/80/100/120 ms bounded spans plus full-cohort local folds", "Short local observations exist, but the forward-half phase baseline deteriorates to near-uniform modulo-π error. Multi-second uninterrupted GLRT lines cannot be reproduced inside a 120 ms dwell.", "frame-methods/REPORT.md", "forward modulo π", eval_frame["median_per_arc_forward_rms_rad_mod_pi"] * deg, "degrees RMS", "local forward diagnostic; long-line extension unavailable")
    row(13, local, "Every arc remains within its original dwell. Acquisition duration reaches 120 ms, but qualified continuous PNT phase span remains zero.", "frame-methods/fullspan/fullspan-trackers.json", "retune-bounded phase", 0, "qualified spans", "explicit resets at unobserved support")
    row(14, "9 development arcs: 20/50 ms 9 each; 100 ms 8 eligible", "Actual semi-coherent line pooling: median even/odd frequency differences 25/0/0 Hz; rate differences 600/500/400 Hz/s. Same grid bin is not zero uncertainty; phase is a per-frame nuisance.", "frame-methods/actual-05-14-smoke.json", "semi-coherent frequency", None, "", "bounded even/odd frequency consistency; 1 late-seed 100 ms case ineligible")
    row(15, "All 2,214 chunks / 2.6568 billion dual-RX rows", "Hashes pass; zero known counter-word matches, clipped rows or repeated 100k-row blocks. Retune failures remain despite absence of this contamination signature.", "capture-audit/REPORT.md", "capture validity", 0, "known contaminated rows", "full recorded-data census")
    jump = rm["robust-jump-filter"]["median_common_receiver_arc_rms_hz"]
    line = rm["trailing-20ms-line"]["median_common_receiver_arc_rms_hz"]
    row(16, f"{arc_count} cached arcs; exact V2/phase-gated comparison bounded to development states", f"On matched evaluation frames, robust jump median per-arc frequency RMS {jump:.2f} Hz versus trailing-20-ms line {line:.2f} Hz. Offline smoothing uses future times; this is frequency consistency, not phase continuity.", "frame-methods/row16-root/REPORT.md", "held frame CFO", jump, "Hz RMS", "past even-fold fits versus current odd-fold CFO")
    row(17, "14 actual V3 development spans at 75/120 ms", "10 numerical completions, 4 no-results after independent alignment; bounded acquisition ablation, not a 128-visit V3 efficacy claim.", "frame-methods/REPORT.md", "V3 phase-safe tracking", 10, "numerical completions", "bounded actual kernel")
    row(18, "16 development receiver cases: 8 processed, 7 not acquired, 1 short", "Actual seeded V4: zero phase-qualified modes; experimental uncalibrated thresholds unchanged.", "frame-methods/v4-smoke.json", "V4 phase-safe tracking", 0, "qualified modes", "bounded actual acquisition/control kernel")
    row(19, "128 visits / 256 receiver cases; independent PSS 4, conditioned 73, SSS 17", "Correct physical GLRT seed improves PSS timing availability. Carrier prediction remains weak: conditioned PSS held RMS .279 cycles; independent SSS .282 cycles.", "sync-spectral/REPORT.md", "PSS/SSS carrier 2π", .279 * 360, "degrees RMS", "alternating-frame carrier holdout; candidate-selected support")
    row(20, "48 evaluation receiver cases with GLRT-conditioned PSS timing", "Equal-weight timing held RMS about .802 μs; score and robust weighting do not rescue carrier continuity. 125/250 ms uninterrupted windows are unavailable.", "sync-spectral/REPORT.md", "timing", .802, "μs RMS", "timing and carrier are distinct observables")
    row(21, "42 sparse-acquired primary visits; 2 multimode evaluation visits", "Actual simultaneous-IQ two-mode DD: at 23 ms R=.584 versus shifted-RX .055, but 47/95 ms controls remain strong. Two candidate modes are not proven distinct emitters.", "dual-rx/method21-22-shared-residual.json", "two-mode differential 2π", .584, "R", "10 windows from only 2 visits; descriptive in-fit/control evidence")
    row(22, "42 sparse-acquired visits; 29 evaluation; 23/47/95 ms", "Single-pair exact/control median frame R: .884/.543, .662/.425, .555/.324. Longer windows reduce coherence; frame-center coincidence is not required for the simultaneous-IQ variant.", "dual-rx/method21-22-shared-residual.json", "within-window differential 2π", None, "", "fixed .4093 ms RX-time control; 20 ms recurrence sensitivity separate")
    ev_resp = response["by_split"]["evaluation"]
    row(23, f"128 visits; 46 training-half acquired; {response['counts']['completed']} completed; {response['counts']['supported']} broadband-supported", f"Best local held result: {ev_resp['with_pilot_holdout']} evaluation visits have held pilot checks, median {ev_resp['pilot_held_rms_median_deg']:.2f}°. Only {ev_resp['supported']}/96 evaluation visits pass the broadband support gate. Response normalization removes instrument/channel terms; this is not raw geometric phase.", "dual-rx/method23-dense-relative-phase-summary.json", "response-normalized differential 2π", ev_resp["pilot_held_rms_median_deg"], "degrees RMS", "train-half response and disjoint-band/held-time checks", f"{ev_resp['supported']}/96 evaluation visits supported")
    row(24, "46 training-half-acquired visits; 32 evaluation", f"Random-held R raw/CFO/CFO+rate={ev_direct['random_raw_r']:.3f}/{ev_direct['random_constant_cfo_r']:.3f}/{ev_direct['random_cfo_rate_r']:.3f}; forward={ev_direct['forward_raw_r']:.3f}/{ev_direct['forward_constant_cfo_r']:.3f}/{ev_direct['forward_cfo_rate_r']:.3f}. Local correction helps reconstruction but does not establish future phase.", "dual-rx/dense-direct/method24-corrected-summary.json", "direct differential 2π", ev_direct["forward_cfo_rate_r"], "R", "training-only aliases/frequency/rate; zero-intercept and centered errors retained")
    row(25, "46 training-half-acquired visits; 32 evaluation", f"Full FFT/direct Parseval error ~{spec['native']['random']['parseval_rms_rad']:.1e} rad. Held common-bin and phase-only results remain close to direct IQ; equivalent transforms do not add independent evidence.", "sync-spectral/guarded-spectral-dense-summary.json", "FFT differential 2π", spec["native"]["forward"]["held_r"], "R", "training-frozen bin masks; disjoint raw supports")
    row(26, "Same 32 acquired evaluation visits and identical guarded splits", f"Native 10 / derived 2.5 MS/s random-held R={spec['native']['random']['held_r']:.3f}/{spec['derived_2p5']['random']['held_r']:.3f}; forward={spec['native']['forward']['held_r']:.3f}/{spec['derived_2p5']['forward']['held_r']:.3f}. Narrowing bandwidth does not rescue continuity.", "sync-spectral/guarded-spectral-dense-summary.json", "matched-band differential 2π", spec["derived_2p5"]["forward"]["held_r"], "R", "physical recentering, anti-alias filter, disjoint FIR support")
    row(27, "177 touched visits; 75 retuned returns; 54 evaluation returns after CFO gate", "Actual retuned-return prediction fails: R=.090 and median absolute error 76.13°. Absolute phase across a track remains unresolved; not every visit of every track was extracted.", "cross-dwell/REPORT.md", "cross-retune differential 2π", .090, "R", "left-only transport across intervening target changes")
    row(28, "99 admitted adjacent edges; 71 evaluation / 56 overlapping-edge groups", "Historical joint R=.636; raw-disjoint joint=.634; left-only causal=.624. Median development-calibrated error 33.08°; shifted-RX control R=.065.", "cross-dwell/REPORT.md", "boundary differential 2π", cross["evaluation_causal_r"], "R", "boundary-held raw support; joint and causal separated")
    row(29, "Evaluation CH1/CH2/CH4 edges: 33/17/21", "Causal R=.500/.648/.835 by channel. CH3 has no admitted edge. These are within-recording repetitions, not independent recording replications or named satellites.", "cross-dwell/REPORT.md", "grouped boundary differential 2π", None, "", "shared-dwell groups retained")
    row(30, "22 development and 56 evaluation edge groups; 33 TLE reviews available", "Development-frozen circular pairing model beats uniform reset by 21.74 log-likelihood units on evaluation groups. This supports local pairing evidence; missing qualified baseline/phase reference prevents geometric identification or TLE reranking.", "cross-dwell/REPORT.md", "conditional pairing evidence", 21.74, "log-likelihood units", "not a calibrated posterior or identity probability")

    with (R / "method-summary.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader(); writer.writerows(records)
    (R / "method-summary.json").write_text(json.dumps(records, indent=2) + "\n")
    for method, result in zip(registry["methods"], records, strict=True):
        method["execution_binding"] = {"status": "completed_bounded" if "bounded" in result["validation"] or "development" in result["scope"] else "completed_reported_scope", "result_path": "method-summary.json", "evidence_path": result["evidence"], "scope": result["scope"]}
    (R / "method-registry.json").write_text(json.dumps(registry, indent=2) + "\n")

    lines = [
        "# Phase recovery on scan-fw-32a202b6e55630ec", "",
        "**Local phase is measurable, but this recording does not support a continuous absolute phase track through retunes.** Corrected dense acquisition improves coverage; response-normalized dual-RX extraction gives the strongest local held result. Full-dwell PNT V1/V2 do not qualify a phase lock. Adjacent unchanged-target boundaries retain some structure, while returns after tuning elsewhere fail.", "",
        "This report completes a bounded replay of the 30-method ledger using SOL workers and a coordinator review. The full 128-visit cohort was processed for capture/acquisition, frame extraction, ordinary/modulo-π/V1/V2 tracking, PSS/SSS and the primary dense broadband comparisons. Expensive historical feedback/batch/semi-coherent/V3/V4 variants use the explicitly labeled frozen development subset. Those rows are not full-cohort efficacy claims. No new RF collection or production change was made.", "",
        "## Main results", "",
        f"- **Capture:** all 2,214 chunks and the full 2.6568-billion-row stream pass integrity checks. No known timestamp-word signature, clipping or repeated 100k-row block was found. This excludes the tested defect, not every possible RF impairment.",
        f"- **Acquisition:** six 20 ms probes per dwell give simultaneous dual-RX detections in **49/128 visits**, versus **42/128** with only the first probe. Evaluation coverage rises from **29/96 to 34/96**. Only **46/128** have a paired acquisition in the training half and are eligible for the dense forward broadband comparison.",
        f"- **Frame-local Qin:** {frame_count:,} extracted frames on {arc_count} acquired receiver arcs. Evaluation median per-arc even/odd phase disagreement is **{eval_frame['median_per_arc_held_rms_rad_mod_pi'] * deg:.1f}° modulo π**; adjacent prediction is **{eval_frame['median_per_arc_adjacent_rms_rad_mod_pi'] * deg:.1f}°**, and the forward-half baseline is **{eval_frame['median_per_arc_forward_rms_rad_mod_pi'] * deg:.1f}°**. Fold agreement is not absolute-phase truth.",
        f"- **Actual full-dwell tracking:** ordinary 2π resets **{resets['ordinary_2pi']}** times and modulo-π resets **{resets['causal_modulo_pi']}** times. PNT V1 and V2 each yield **0 phase locks on {arc_count} acquired arcs**; {no_result} arcs return no result. The smaller modulo-π wrap interval explains part of its lower error.",
        f"- **Response-normalized phase:** **{ev_resp['with_pilot_holdout']} evaluation visits** have second-half pilot checks, with median error **{ev_resp['pilot_held_rms_median_deg']:.2f}°**. **{ev_resp['supported']}/96** evaluation visits pass the broadband support gate. These are different denominators; the phase error is conditional on an available pilot check.",
        f"- **Direct IQ / FFT / bandwidth:** random reconstruction improves after CFO correction, but forward phase remains weak. Guarded native random/forward median R is **{spec['native']['random']['held_r']:.3f}/{spec['native']['forward']['held_r']:.3f}**; matched derived-2.5-MS/s gives **{spec['derived_2p5']['random']['held_r']:.3f}/{spec['derived_2p5']['forward']['held_r']:.3f}**.",
        "- **Across visits:** adjacent-boundary causal R is **0.624** with **33.08°** median development-calibrated error on 71 evaluation edges. Actual retuned returns give **R=0.090**, **76.13°** median error on 54 evaluation returns. The evidence does not support absolute phase, satellite identity or geometry.", "",
        "![Final comparison overview](overview.png)", "",
        "## Approach / report / outcome", "",
        "The [historical review](HISTORICAL_REVIEW.md) gives previous outcomes and original report links. The table below gives this recording's replay outcomes. Counts are visits unless explicitly labeled receiver arcs, windows, frames or edges. R is circular concentration, not Pearson correlation; different phase symmetries and normalization conventions must not be ranked on one common scale.", "",
        "| Approach | Replay report / scope | Outcome |", "| --- | --- | --- |",
    ]
    for item in records:
        lines.append(f"| {item['method_id'][:2]}. {item['approach']} | [{item['scope']}]({item['evidence']}) | {item['outcome']} |")
    lines += ["", "## Visual evidence", "",
        "![Full recording and frozen cohort acquisition](population-overview.png)", "",
        "![Frame-local versus neighboring-frame evidence](frame-methods/frame-held-control-overview.png)", "",
        "![Evaluation examples selected by declared best/median/worst fold error](frame-methods/representative-eval-fold-traces.png)", "",
        "![Pilot differential-phase window and shifted-RX controls](dual-rx/method21-22-shared-residual.png)", "",
        "![Paired bandwidth holdouts with guarded physical support](sync-spectral/guarded-spectral-dense-summary.png)", "",
        "![Adjacent-boundary causal residuals](cross-dwell/summary.png)", "",
        "## What the fixes changed", "",
        "The saved sparse product was already produced by corrected release `2c30eaf5…`; numerical parity with replay base `e1a24b20…` was checked. It is not legacy evidence. The bounded legacy/corrected comparison and mechanism ablations are in [acquisition](acquisition/README.md). On eight frozen diagnostic visits, tuning-only, wider coverage, fallback and 22-candidate shortlist each found at least one passing candidate in five visits; they retained 14/13/15/18 passing candidates respectively. Wider coverage cost more without another recovered visit. These are diagnostic counts, not calibrated false-alarm rates.", "",
        "Raw and RF-valid input are identical for the tested timestamp-word defect on this scan. No zero filling, deletion or invented capture repair was applied. Correct physical CFO coordinates were essential: display aliases cannot be used for coherent mixing or PSS conditioning.", "",
        "## Validation and practical limits", "",
        "The 128 visits were chosen from metadata: four targets × eight common session-time bins × four hash-ranked visits. The first two bins are development (32); the remaining six are evaluation (96). Failed acquisitions stay in the denominator. Source samples, acquisition candidates, code and configurations are retained in the reproduction artifacts.", "",
        "The final spectral results use shared random partitions at both rates, raw-disjoint windows with FIR guards, training-only alias/frequency/rate fits, and training-frozen masks. Earlier spectral and direct files with incorrect operation order, future-fit leakage or overlapping transform support are superseded; see [review log](REVIEW.md). Random reconstruction and forward prediction remain separate.", "",
        "The full-span trackers use the earliest qualifying dense probe and only the remaining actual raw support. An acquisition consumes 20 ms, so earlier innovations are acquisition-conditioned diagnostics, not online forecasts. Response-normalized results remove learned instrument/channel terms. Neither a fitted phase intercept nor a response correction is a measured electrical baseline.", "",
        "The shared-source double-difference experiment has only two frequency-separated candidate visits. Shifted-receiver and deranged controls prevent interpreting a near-zero difference as automatic two-emitter or geometric evidence. The 23/47/95 ms results do not provide independent visit-level replication.", "",
        "Cross-dwell selection inventories all 552 same-target candidate boundaries, then uses 99 with phase-blind CFO-compatible sparse support. Retuned-return testing uses 177 visits touched by that analysis; it is a bounded subset, not every visit in all 45 tracklets. Overlapping edges are grouped. Existing TLE reviews are available, but a qualified electrical baseline and a stitched phase reference are not. The absolute UTC bracket is 364.64 ms; device counters govern relative time.", "",
        "The report-owned regression suite passes **23 tests**; the acquisition package also records 109 focused checks. The final numerical outputs are not a detector false-alarm calibration. [Test receipt](test-results.xml), [machine-readable ledger](method-summary.csv), [reproduction guide](REPRODUCE.md), [exclusion counts](exclusions.csv), and [artifact hashes](artifact-manifest.json) are included.", "",
    ]
    (R / "REPORT.md").write_text("\n".join(lines))

    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    axes[0, 0].bar(["First probe", "Dense any probe", "Training-half pair", "Response gate"], [29, 34, 32, ev_resp["supported"]], color=["#809bab", "#3a738e", "#4d8a8a", "#ac754c"])
    axes[0, 0].set(ylim=(0, 96), ylabel="Evaluation visits / 96", title="Availability stays in the denominator")
    axes[0, 0].tick_params(axis="x", labelrotation=12)
    axes[0, 1].bar(["Even/odd fold", "Adjacent frame", "Forward half"], [eval_frame["median_per_arc_held_rms_rad_mod_pi"] * deg, eval_frame["median_per_arc_adjacent_rms_rad_mod_pi"] * deg, eval_frame["median_per_arc_forward_rms_rad_mod_pi"] * deg], color="#487f9a")
    axes[0, 1].set(ylabel="Median per-arc RMS (degrees, modulo π)", title="Single-RX local agreement degrades over time")
    axes[1, 0].bar(["Raw", "CFO", "CFO + rate"], [ev_direct["random_raw_r"], ev_direct["random_constant_cfo_r"], ev_direct["random_cfo_rate_r"]], width=.36, align="edge", label="Random held", color="#487f9a")
    axes[1, 0].bar(["Raw", "CFO", "CFO + rate"], [ev_direct["forward_raw_r"], ev_direct["forward_constant_cfo_r"], ev_direct["forward_cfo_rate_r"]], width=-.36, align="edge", label="Forward held", color="#c18b55")
    axes[1, 0].set(ylim=(0, 1), ylabel="Median ordinary 2π concentration R", title="Direct IQ · 32 acquired evaluation visits")
    axes[1, 0].legend(frameon=False)
    axes[1, 1].bar(["Adjacent\n71 edges", "Wrong RX time\n71 controls", "Retuned return\n54 edges"], [.6237401981, .0647758005, .090], color=["#487f9a", "#a5a5a5", "#c18b55"])
    axes[1, 1].set(ylim=(0, 1), ylabel="Boundary residual ordinary 2π R", title="Continuity depends on the boundary type")
    fig.suptitle("scan-fw-32a202b6e55630ec · final bounded phase replay", fontsize=16)
    fig.supxlabel("Panels measure different observables. Local response-normalized pilot error is 3.42° on 26 evaluation visits; no calibrated geometry.", fontsize=9)
    for suffix in ("png", "svg"):
        fig.savefig(R / f"overview.{suffix}", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    main()
