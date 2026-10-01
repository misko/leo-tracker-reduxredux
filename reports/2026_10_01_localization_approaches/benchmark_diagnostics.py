"""Receipt-derived diagnostics and figures for the frozen A1/B1 benchmark."""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from timing_diagnostics import (
    ROOT,
    _continuation_fit_seconds,
    _load,
    _receipt_path,
    _rows,
    diagnose,
)

ARMS = ("A1", "B1")
PLANNED = 64


def _summary(values):
    a = np.asarray(values, dtype=float)
    return {
        "count": int(a.size),
        "median": None if not a.size else float(np.median(a)),
        "p90": None if not a.size else float(np.percentile(a, 90)),
        "max": None if not a.size else float(np.max(a)),
        "sum": float(np.sum(a)),
    }


def _receipt(row, root):
    path = _receipt_path(row, root)
    return (None, None) if not path or not path.is_file() else (path, _load(path))


def _dataset(unit):
    return unit.split("-")[0]


def _arm_diagnostics(arm, primary, final, root):
    fit_times, rss, acquisition, runtimes, iterations, cpu, acquisition_shares = (
        [], [], [], [], [], [], []
    )
    calls, reasons, background = Counter(), Counter(), 0
    omitted, approximate = [], Counter()
    dataset_errors = defaultdict(list)
    continuation_count = 0
    for unit in sorted({u for a, u in final if a == arm}):
        final_row = final[arm, unit]
        if final_row.get("accepted") and final_row.get("error_m") is not None:
            dataset_errors[_dataset(unit)].append(float(final_row["error_m"]))
        if final_row.get("runtime_s") is not None:
            runtimes.append(float(final_row["runtime_s"]))
        primary_row = primary.get((arm, unit), {})
        primary_path, primary_receipt = _receipt(primary_row, root)
        final_path, final_receipt = _receipt(final_row, root)
        unit_fit_seconds = 0.0
        has_fit_records = False
        if primary_receipt:
            if primary_receipt.get("acquisition_seconds") is not None:
                acquisition.append(float(primary_receipt["acquisition_seconds"]))
            unit_fit_seconds += sum(
                float(f.get("fit_seconds", 0)) for f in primary_receipt.get("fits", [])
            )
            has_fit_records = bool(primary_receipt.get("fits"))
            if primary_receipt.get("cpu_seconds") is not None:
                cpu.append(float(primary_receipt["cpu_seconds"]))
            if primary_receipt.get("max_rss_kib") is not None:
                rss.append(float(primary_receipt["max_rss_kib"]))
            for key, value in primary_receipt.get("port_calls", {}).items():
                calls[key] += int(value)
        receipt = final_receipt or primary_receipt
        if final_path and primary_path and final_path.resolve() != primary_path.resolve():
            continuation_count += 1
            incremental = _continuation_fit_seconds(final_receipt, root)
            unit_fit_seconds += incremental
            has_fit_records = has_fit_records or bool(final_receipt.get("fits"))
            if final_receipt.get("cpu_seconds") is not None:
                cpu.append(float(final_receipt["cpu_seconds"]))
            if final_receipt.get("max_rss_kib") is not None:
                rss.append(float(final_receipt["max_rss_kib"]))
            for key, value in final_receipt.get("port_calls", {}).items():
                calls[key] += int(value)
        if has_fit_records:
            fit_times.append(unit_fit_seconds)
        if (
            primary_receipt
            and final_row.get("runtime_s")
            and primary_receipt.get("acquisition_seconds") is not None
        ):
            acquisition_shares.append(
                float(primary_receipt["acquisition_seconds"]) / float(final_row["runtime_s"])
            )
        if receipt:
            for fit in receipt.get("fits", []):
                iterations.append(int(fit.get("iterations", 0)))
                reasons[fit.get("reason", "missing")] += 1
            best = receipt.get("best") or {}
            background += sum(value == "background" for value in best.get("associations", []))
            soft = best.get("soft_diagnostics")
            if soft:
                omitted.append(float(soft.get("max_omitted_responsibility", 0)))
                approximate[str(bool(soft.get("proposal_is_approximate")))] += 1
    attempted = sum(bool(row.get("attempted")) for (a, _), row in final.items() if a == arm)
    accepted = sum(bool(row.get("accepted")) for (a, _), row in final.items() if a == arm)
    return {
        "planned_count": PLANNED,
        "attempted_count": attempted,
        "accepted_count": accepted,
        "status_counts": dict(sorted(Counter(
            row.get("status", "unknown") for (a, _), row in final.items() if a == arm
        ).items())),
        "end_to_end_seconds": _summary(runtimes),
        "fit_only_seconds": _summary(fit_times),
        "peak_rss_kib": _summary(rss),
        "native_cpu_seconds": _summary(cpu),
        "acquisition_seconds": _summary(acquisition),
        "acquisition_share_of_attempted_runtime": (
            None if not runtimes or not acquisition else sum(acquisition) / sum(runtimes)
        ),
        "per_unit_acquisition_share": _summary(acquisition_shares),
        "continuation_count": continuation_count,
        "continuation_rate_of_attempted": None if not attempted else continuation_count / attempted,
        "fit_iterations": _summary(iterations),
        "fit_reason_counts": dict(sorted(reasons.items())),
        "port_call_totals": dict(sorted(calls.items())),
        "best_background_argmax_count": background,
        "max_omitted_responsibility": _summary(omitted),
        "approximate_proposal_counts": dict(sorted(approximate.items())),
        "errors_by_dataset_m": {
            name: _summary(values) for name, values in sorted(dataset_errors.items())
        },
        "unavailable": [
            "full responsibility masses were not persisted",
            "observability metrics were not persisted",
            "credible regions and calibrated region coverage are unavailable",
            "distinct basin counts and calibrated mode weights were not persisted",
        ],
    }


def _comparison(final):
    units = sorted({u for _, u in final})
    discordant = Counter()
    paired = []
    for unit in units:
        a, b = final.get(("A1", unit), {}), final.get(("B1", unit), {})
        aa, ba = bool(a.get("accepted")), bool(b.get("accepted"))
        label = "both" if aa and ba else "a1_only" if aa else "b1_only" if ba else "neither"
        discordant[label] += 1
        if aa and ba and a.get("error_m") is not None and b.get("error_m") is not None:
            paired.append((unit, float(a["error_m"]), float(b["error_m"])))
    a = np.asarray([x[1] for x in paired])
    b = np.asarray([x[2] for x in paired])
    a_median = None if not len(a) else float(np.median(a))
    b_median = None if not len(b) else float(np.median(b))
    a_p90 = None if not len(a) else float(np.percentile(a, 90))
    b_p90 = None if not len(b) else float(np.percentile(b, 90))
    accepted_a_errors = [float(r["error_m"]) for (arm, _), r in final.items()
                         if arm == "A1" and r.get("accepted") and r.get("error_m") is not None]
    accepted_b_errors = [float(r["error_m"]) for (arm, _), r in final.items()
                         if arm == "B1" and r.get("accepted") and r.get("error_m") is not None]
    accepted_a_units = {u for (arm, u), r in final.items() if arm == "A1" and r.get("accepted")}
    accepted_b_units = {u for (arm, u), r in final.items() if arm == "B1" and r.get("accepted")}
    a_only = sorted(accepted_a_units - accepted_b_units)
    b_only = sorted(accepted_b_units - accepted_a_units)
    all_a_p90 = None if not accepted_a_errors else float(np.percentile(accepted_a_errors, 90))
    all_b_p90 = None if not accepted_b_errors else float(np.percentile(accepted_b_errors, 90))
    new_large = [unit for unit, ae, be in paired if be > 100_000 and ae <= 100_000]
    checks = {
        "b1_paired_median_at_least_20_percent_lower": (
            None if a_median is None else b_median <= .8 * a_median
        ),
        "b1_no_accepted_scan_loss": not a_only,
        "b1_p90_no_more_than_10_percent_worse": (
            None if all_a_p90 is None or all_b_p90 is None else all_b_p90 <= 1.1 * all_a_p90
        ),
        "b1_no_new_error_over_100km": not new_large,
    }
    return {
        "planned_denominator": PLANNED,
        "discordant_completion_counts": dict(sorted(discordant.items())),
        "a1_only_accepted_units": a_only,
        "b1_only_accepted_units": b_only,
        "paired_accepted_count": len(paired),
        "paired_a1_median_error_m": a_median,
        "paired_b1_median_error_m": b_median,
        "paired_a1_p90_error_m": a_p90,
        "paired_b1_p90_error_m": b_p90,
        "all_accepted_a1_p90_error_m": all_a_p90,
        "all_accepted_b1_p90_error_m": all_b_p90,
        "accepted_error_threshold_counts": {
            "A1": {"over_10km": sum(x > 10_000 for x in accepted_a_errors),
                   "over_100km": sum(x > 100_000 for x in accepted_a_errors)},
            "B1": {"over_10km": sum(x > 10_000 for x in accepted_b_errors),
                   "over_100km": sum(x > 100_000 for x in accepted_b_errors)},
        },
        "new_b1_errors_over_100km": new_large,
        "decision_checks": checks,
        "practical_accuracy_win": all(value is True for value in checks.values()),
        "qualification": "descriptive engineering rule; no significance claim",
    }


def analyze(primary_evaluator: Path, two_stage_evaluator: Path, *, repository_root=ROOT):
    primary, final = _rows(_load(primary_evaluator)), _rows(_load(two_stage_evaluator))
    return {
        "schema": "localization-benchmark-diagnostics/v1",
        "coverage_is_complete": all(
            sum(bool(r.get("attempted")) for (a, _), r in final.items() if a == arm) == PLANNED
            for arm in ARMS
        ),
        "arms": {arm: _arm_diagnostics(arm, primary, final, repository_root) for arm in ARMS},
        "a1_b1": _comparison(final),
        "timing_phases": diagnose(
            primary_evaluator, two_stage_evaluator, repository_root=repository_root
        ),
    }


def plot(result, final_evaluator: Path, prefix: Path):
    """Write plain-language accuracy/runtime and all-attempt phase figures."""
    import matplotlib.pyplot as plt

    rows = list(_rows(_load(final_evaluator)).values())
    fig, axes = plt.subplots(2, 1, figsize=(9, 7), constrained_layout=True)
    for arm, marker in (("A1", "o"), ("B1", "s")):
        accepted = [r for r in rows if r.get("arm") == arm and r.get("accepted")]
        axes[0].scatter([r["runtime_s"] for r in accepted], [r["error_m"] / 1000 for r in accepted],
                        label=f"{arm} accepted", marker=marker)
        failed = [
            r for r in rows
            if r.get("arm") == arm and r.get("attempted") and not r.get("accepted")
        ]
        axes[1].scatter([r.get("runtime_s") for r in failed], [arm] * len(failed), marker="x",
                        label=f"{arm} failed or unresolved")
    axes[0].set(xlabel="End-to-end runtime (seconds)", ylabel="Accepted location error (km)")
    axes[1].set(xlabel="End-to-end runtime (seconds)", ylabel="Failed status (error unavailable)")
    axes[0].legend()
    axes[1].legend()
    accuracy_path = prefix.with_name(prefix.name + "-accuracy-vs-runtime.png")
    fig.savefig(accuracy_path, dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4), constrained_layout=True)
    labels = list(ARMS)
    x = np.arange(2)
    acquisition = [result["arms"][arm]["acquisition_seconds"]["sum"] for arm in labels]
    fitting = [result["arms"][arm]["fit_only_seconds"]["sum"] for arm in labels]
    ax.bar(x, acquisition, label="Completed acquisition time")
    ax.bar(x, fitting, bottom=acquisition, label="Recorded optimizer fit time")
    ax.set_xticks(x, labels)
    ax.set_ylabel("Summed seconds across all 64 planned units")
    ax.set_title("Acquisition timeouts remain failures; missing fit time is unavailable, not zero")
    timeout_counts = result["timing_phases"]["primary_phase_counts"]
    ax.text(
        .99, .98,
        "Acquisition timeouts: "
        + ", ".join(f"{arm}={timeout_counts[arm].get('acquisition_timeout', 0)}" for arm in ARMS),
        transform=ax.transAxes, ha="right", va="top",
    )
    ax.legend()
    breakdown_path = prefix.with_name(prefix.name + "-runtime-breakdown.png")
    fig.savefig(breakdown_path, dpi=160)
    plt.close(fig)
    return [str(accuracy_path), str(breakdown_path)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("primary_evaluator", type=Path)
    parser.add_argument("two_stage_evaluator", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--figure-prefix", type=Path)
    args = parser.parse_args()
    result = analyze(args.primary_evaluator, args.two_stage_evaluator)
    if args.figure_prefix:
        result["figures"] = plot(result, args.two_stage_evaluator, args.figure_prefix)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
