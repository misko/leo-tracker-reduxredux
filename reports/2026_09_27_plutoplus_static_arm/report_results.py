"""Render an auditable report from completed target receipts, without more DSP."""
import csv
import json
import math
from pathlib import Path
import statistics
import sys

HERE = Path(__file__).resolve().parent


def scientific(value):
    if isinstance(value, dict):
        return {k: scientific(v) for k, v in value.items()
                if "cpu_ms" not in k and "wall_ms" not in k and k != "index"}
    if isinstance(value, list):
        return [scientific(v) for v in value]
    return value


def tails(values):
    ordered = sorted(values)
    return {"calls": len(values), "median_ms": statistics.median(values),
            "p95_ms": ordered[math.ceil(.95*len(values))-1], "max_ms": max(values),
            "over_100ms": sum(t>100 for t in values), "over_120ms": sum(t>120 for t in values)}


def report(run):
    completion = json.loads((run / "completion.json").read_text())
    rows = json.loads((run / "assessments.json").read_text())
    summary = json.loads((run / "summary.json").read_text())
    lock = json.loads((run / "run-lock.json").read_text())
    manifest = json.loads((run / "manifest.json").read_text())
    full_determinism = []
    decision_checks = []
    for row in rows:
        method_activity = {}
        for method in "ABCD":
            raw = json.loads((run / (row["case_id"]+"-"+method+".json")).read_text())
            signatures = [scientific(rep["receivers"]) for rep in raw["repetitions"]]
            full_determinism.append({"case_id": row["case_id"], "method": method,
                                     "passed": all(s == signatures[0] for s in signatures)})
            activity = []
            for rx in raw["repetitions"][0]["receivers"]:
                candidates = rx["result"]["confirmations"][0]["candidates"]
                activity.append(bool(candidates and candidates[0]["fractional_complete"]
                                     and candidates[0]["margin"] > .025))
            method_activity[method] = activity
        for method in "BCD":
            decision_checks.append({"case_id": row["case_id"], "method": method,
                "baseline": method_activity["A"], "candidate": method_activity[method],
                "passed": method_activity["A"] == method_activity[method]})
    (run / "full-determinism-audit.json").write_text(json.dumps(full_determinism, indent=2)+"\n")
    (run / "decision-equality-audit.json").write_text(json.dumps(decision_checks, indent=2)+"\n")
    table = []
    quality = []
    incomplete_rates = []
    all_tails = []
    for rate in (2500000, 5000000, 7500000, 10000000):
        cases = [r for r in rows if r["split"] == "dev" and r["rate_hz"] == rate]
        expected = {c["case_id"] for c in manifest["cases"] if c["split"] == "dev" and c["rate_hz"] == rate}
        if {c["case_id"] for c in cases} != expected:
            incomplete_rates.append({"rate_hz": rate, "completed": len(cases), "planned": len(expected)})
            continue
        totals = next((s for s in summary if s["split"] == "dev" and s["rate_hz"] == rate), None)
        if not totals:
            continue
        for method in "ABCD":
            pair = []; receivers = [[], []]
            for case in cases:
                raw = json.loads((run / (case["case_id"]+"-"+method+".json")).read_text())
                for rep in raw["repetitions"]:
                    pair.append(rep["visit_wall_ms"])
                    for rx in rep["receivers"]:
                        receivers[rx["receiver"]].append(rx["packing_wall_ms"]+rx["detector_wall_ms"])
            all_tails.append({"rate_hz": rate, "method": method, "split": "dev",
                              "pair": tails(pair), "rx0": tails(receivers[0]), "rx1": tails(receivers[1])})
        costs = totals["methods"]
        measured_walls = []
        rx_walls = []
        for case in cases:
            raw = json.loads((run / (case["case_id"]+"-D.json")).read_text())
            measured_walls.extend(rep["visit_wall_ms"] for rep in raw["repetitions"])
            rx_walls.extend(rx["packing_wall_ms"]+rx["detector_wall_ms"]
                            for rep in raw["repetitions"] for rx in rep["receivers"])
        measured_walls.sort()
        table.append({"rate_msps": rate/1e6, "real_visits": len(cases),
            **{m+"_mean_cpu_ms": costs[m]["cpu_mean_ms"] for m in "ABCD"},
            **{m+"_speedup": costs[m]["speedup_vs_A"] for m in "BCD"},
            "D_speedup_vs_C": costs["C"]["cpu_total_ms"]/costs["D"]["cpu_total_ms"],
            "D_pair_wall_p95_ms": measured_walls[math.ceil(.95*len(measured_walls))-1],
            "D_pair_wall_max_ms": max(measured_walls),
            "D_rx_wall_max_ms": max(rx_walls),
            "D_pair_calls_over_120ms": sum(t>120 for t in measured_walls),
            "D_pair_measured_calls": len(measured_walls)})
        counts = {m: {k: sum(c["identity"][m][k] for c in cases) for k in
            ("reference_positives", "retained_reference_positives", "lost_reference_positives",
             "additional_candidate_positives", "identity_failures")} for m in "BCD"}
        quality.append({"rate_hz": rate, "methods": counts})
    if table:
        with (run / "results.csv").open("w") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(table[0]))
            writer.writeheader(); writer.writerows(table)
    (run / "quality-summary.json").write_text(json.dumps(quality, indent=2)+"\n")
    (run / "wall-tails.json").write_text(json.dumps(all_tails, indent=2)+"\n")
    failed = [r["case_id"] for r in rows if not r["passed"]]
    lines = ["# Single-core ARM saved-IQ result on 192.168.1.15", "",
        f"Completed {completion['completed_cases']}/{completion['planned_cases']} physical cases in "
        f"{completion['elapsed_seconds']:.1f} seconds. Complete: **{completion['complete']}**. "
        f"Scientific case failures: **{len(failed)}**.", "",
        f"Independent explicit decision-equality audit: "
        f"**{sum(c['passed'] for c in decision_checks)}/{len(decision_checks)}** comparisons pass.", "",
        "Incomplete real-data strata excluded from rate tables: "+json.dumps(incomplete_rates)+".", "",
        "These are measurements on the physical Cortex-A9, pinned to CPU0, with RX0 and RX1 "
        "processed sequentially. Input is stored IQ at its native rate. No RF, radio controls, "
        "firmware or production services were used or changed. The target SD card was formatted "
        "with user authorization and mounted at /mnt/glrtbench.", "",
        "A = packed input/FP64 FFTW; B = packed/FP32; C = natural-stride/FP64; "
        "D = natural-stride/FP32. All share the same scientific flags and six-window, "
        "one-confirmation-per-receiver profile. This is not the eleven-probe full scanner "
        "or a deployed production-service benchmark.", "",
        "## Real-data CPU result", "",
        "All times below are mean CPU milliseconds per complete dual-receiver visit. "
        "Each case contributes its median of five measured calls after one warmup. "
        "Speedups are ratios of paired summed medians, not multiplied stage gains.", "",
        "| MS/s | Visits | A FP64 packed | B FP32 packed | C FP64 strided | D FP32 strided | D speedup |",
        "|---:|---:|---:|---:|---:|---:|---:|"]
    for t in table:
        lines.append(f"| {t['rate_msps']:g} | {t['real_visits']} | {t['A_mean_cpu_ms']:.2f} | "
            f"{t['B_mean_cpu_ms']:.2f} | {t['C_mean_cpu_ms']:.2f} | {t['D_mean_cpu_ms']:.2f} | {t['D_speedup']:.3f}x |")
    primary = next((t for t in table if t["rate_msps"] == 2.5), None)
    science_eligible = (completion["complete"] and not failed
        and all(c["passed"] for c in decision_checks) and all(c["passed"] for c in full_determinism))
    if primary:
        lines += ["", f"At the primary 2.5-MS/s rate, FP32 alone gives {primary['B_speedup']:.3f}x, "
            f"strided ingress alone {primary['C_speedup']:.3f}x, and the combination {primary['D_speedup']:.3f}x "
            f"({100*(1-1/primary['D_speedup']):.2f}% less CPU). "
            + ("The 1.30x initial performance target passes." if primary['D_speedup']>=1.3 and science_eligible else
               "No promotion is claimed: the 1.30x performance requirement or complete-run scientific gate is not met. No 10x claim is supported.")]
    lines += ["", "Incremental FP32 gain after natural-stride ingress (C CPU / D CPU): "+
        "; ".join(f"{t['rate_msps']:g} MS/s: {t['D_speedup_vs_C']:.3f}x" for t in table)+"."]
    low = [s for s in summary if s["split"]=="dev" and s["rate_hz"] in (2500000,5000000)]
    if len(low)==2 and all(s["cases"]==32 for s in low):
        sums = {m: sum(s["methods"][m]["cpu_total_ms"] for s in low) for m in "ABCD"}
        lines += ["", f"The explicitly equal-visit 2.5/5-MS/s aggregate (32 visits each) gives "
            f"A/B {sums['A']/sums['B']:.3f}x, A/C {sums['A']/sums['C']:.3f}x, "
            f"A/D {sums['A']/sums['D']:.3f}x and C/D {sums['C']/sums['D']:.3f}x. "
            "The primary result remains 2.5 MS/s; no unequal four-rate aggregate is used."]
    lines += ["", "## Scientific comparison", "",
        "| MS/s | Baseline positive receivers | D retained | D lost | D added | D identity failures |",
        "|---:|---:|---:|---:|---:|---:|"]
    for q in quality:
        c = q["methods"]["D"]
        lines.append(f"| {q['rate_hz']/1e6:g} | {c['reference_positives']} | {c['retained_reference_positives']} | "
                     f"{c['lost_reference_positives']} | {c['additional_candidate_positives']} | {c['identity_failures']} |")
    controls = [r for r in rows if r["split"] == "control"]
    planned_controls = sum(c["split"] == "control" for c in manifest["cases"])
    lines += ["", f"Controls completed: {len(controls)}/{planned_controls}; required truth checks passed: "
        f"{sum(t['passed'] for r in controls for t in r['truth'])}/"
        f"{sum(len(r['truth']) for r in controls)}. Checks include pilot identity and window, "
        "noise/tone rejection, deterministic repetition, rank/window/candidate agreement and "
        "2-us circular timing / 8-kHz physical-CFO association. The raw per-case assessments "
        "retain score drift and all B/C/D comparisons.", "",
        "The real cohort is exposed development data without independent physical truth. "
        "A zero-positive rate has no real sensitivity denominator. Small constructed sets "
        "do not establish rare false-alarm rates or broad multisignal sensitivity.", "",
        f"A separate receipt-only check of every serialized non-timing field across repetitions "
        f"passed {sum(r['passed'] for r in full_determinism)}/{len(full_determinism)} method/case records. "
        "See full-determinism-audit.json; this is additional reporting, not a retuned gate.", "",
        "SOL review found that the inherited identity predicate did not itself reject a "
        "margin-threshold decision flip. Run 01 preserved its original evaluator; run 02 "
        "used the explicit decision gate. This report also "
        "independently checks explicit activity equality from every raw method/case result "
        "(decision-equality-audit.json). Any failure blocks scientific promotion even if the "
        "original case-level identity predicate passed. No threshold was changed.", "",
        "## Observed wall time", "",
        "These values use all five timed repetitions, not only case medians. p95 is the "
        "nearest-rank empirical percentile. Maxima and percentiles are descriptive only. "
        "Single-RX wall values are the sum of packing_wall_ms and detector_wall_ms, "
        "not a separately timed whole-RX service boundary. wall-tails.json contains "
        "A/B/C/D pair and separate RX0/RX1 p95/max and >100/>120-ms counts for each complete real cohort.", "",
        "| MS/s | D pair p95 ms | D pair max ms | D single-RX max ms | Pair calls >120 ms |",
        "|---:|---:|---:|---:|---:|"]
    for t in table:
        lines.append(f"| {t['rate_msps']:g} | {t['D_pair_wall_p95_ms']:.2f} | {t['D_pair_wall_max_ms']:.2f} | "
            f"{t['D_rx_wall_max_ms']:.2f} | {t['D_pair_calls_over_120ms']}/{t['D_pair_measured_calls']} |")
    if primary:
        lines += ["", "## Next optimization target", ""]
        stages = next(s for s in summary if s["split"]=="dev" and s["rate_hz"]==2500000)["methods"]["D"]["stage_mean_ms"]
        lines += ["Primary-rate D stage CPU, per dual-RX visit:", "",
            "| Stage | Mean ms |", "|---|---:|"]
        for key in ("rank_cpu_ms", "coarse_cpu_ms", "fine_cpu_ms", "fractional_cpu_ms", "conversion_cpu_ms", "nuisance_cpu_ms"):
            lines.append(f"| {key.removesuffix('_cpu_ms')} | {stages[key]:.2f} |")
        lines += ["", "Stage timers are diagnostic and potentially inclusive; do not sum them into a "
            "new total. The next experiment should target the measured rank/acquisition and "
            "fractional-sampling work, or causal fresh confirmation that avoids acquisition. "
            "Swapping FFT precision alone does not remove these costs."]
    lines += ["", "## Reproduction and limits", "",
        "See ../RUNBOOK.md, ../PROTOCOL.md and the immutable build-snapshot.tar.gz. "
        "Host ASan/UBSan passed 24 controls through four variants; eleven component tests passed "
        "including the post-review threshold-crossing regressions. "
        "High-rate admission required three scratch-capacity fixes, tested before ARM execution. "
        "Those changes are isolated research snapshots, not production edits.", "",
        "Timed service includes packing/conversion and the complete native detector on resident "
        "IQ. File transfer/read, FFT planning, initialization and JSON serialization are outside "
        "that boundary. Setup timers and whole-session elapsed time are retained separately. "
        "No per-case transfer timer, fault count or complete RSS trace was collected. One "
        "external process-status sample confirms Threads=1, CPU0 and an 18,616-KiB RSS/HWM; "
        "it is not a peak-memory bound across all cases. CPU frequency was not exposed through "
        "the target's cpufreq sysfs path. There was no clock-policy change.", "",
        f"Persistent target directory: `{lock['scratch']}`. Raw target receipts are also copied "
        "here. Input and executable hashes were checked on the target, inputs before and after "
        "each case, and binaries before and after the run. run-lock.json binds evaluator and "
        "build hashes; completion.json records truncation/failure status."]
    if failed:
        lines += ["", "Failed cases: "+", ".join(failed)]
    (run / "REPORT.md").write_text("\n".join(lines)+"\n")
    print("\n".join(lines[:25]))


if __name__ == "__main__":
    report(Path(sys.argv[1]))
