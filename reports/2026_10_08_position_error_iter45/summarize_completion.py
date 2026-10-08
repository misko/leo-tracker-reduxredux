"""Merge completion receipts into all 148 immutable dataset members."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "2026_10_08_position_error_iter44"
ARMS = ("fitted-c", "zero-c")


def read(path):
    return json.loads(path.read_text())


def stats(values):
    values = np.asarray(values)
    return dict(
        n=len(values),
        mean=float(values.mean()),
        median=float(np.median(values)),
        p95=float(np.percentile(values, 95)),
        worst=float(max(values)),
    )


def metrics(rows):
    valid = [r for r in rows if r["candidate"] and r["baseline"]]
    output = dict(membership=len(rows), evaluated=len(valid), arms={})
    if not valid:
        return output
    for arm in ARMS:
        b = np.array([r["baseline"][arm]["horizontal_error_m"] / 1000 for r in valid])
        c = np.array([r["candidate"][arm]["error_km"] for r in valid])
        output["arms"][arm] = dict(
            baseline=stats(b),
            candidate=stats(c),
            paired_delta_km=stats(c - b),
            improved=int(sum(c < b - 0.001)),
            regressed=int(sum(c > b + 0.001)),
            unchanged=int(sum(abs(c - b) <= 0.001)),
            baseline_nonconverged=sum(not r["baseline"][arm]["converged"] for r in valid),
            final_raw_nonconverged=sum(
                r["candidate"][arm]["raw_converged"] is False for r in valid
            ),
            fallbacks=sum(bool(r["candidate"][arm].get("fallback")) for r in valid),
            frequency_rms_hz=dict(
                baseline_mean=float(
                    np.mean([r["baseline"][arm]["posterior_rms_hz"] for r in valid])
                ),
                candidate_mean=float(np.mean([r["candidate"][arm]["rms_hz"] for r in valid])),
            ),
        )
    output["ablation"] = dict(
        candidate_mean_position_delta_fitted_minus_zero_km=float(
            np.mean(
                [
                    r["candidate"]["fitted-c"]["error_km"] - r["candidate"]["zero-c"]["error_km"]
                    for r in valid
                ]
            )
        ),
        candidate_mean_rms_delta_fitted_minus_zero_hz=float(
            np.mean(
                [
                    r["candidate"]["fitted-c"]["rms_hz"] - r["candidate"]["zero-c"]["rms_hz"]
                    for r in valid
                ]
            )
        ),
        fitted_position_better=sum(
            r["candidate"]["fitted-c"]["error_km"] < r["candidate"]["zero-c"]["error_km"] - 0.001
            for r in valid
        ),
        fitted_position_worse=sum(
            r["candidate"]["fitted-c"]["error_km"] > r["candidate"]["zero-c"]["error_km"] + 0.001
            for r in valid
        ),
    )
    return output


def main():
    previous = read(PREVIOUS / "summary.json")
    cases = previous["cases"]
    for case in cases:
        label = case["member"]["inventory_label"]
        for folder in (HERE, HERE / "retry"):
            path = folder / "results" / f"{label}.json"
            if not path.exists():
                continue
            result = read(path)
            if folder != HERE:
                case["original_attempt"] = read(HERE / "results" / f"{label}.json")
            case.update(
                status=result["status"], completion_source=str(path.relative_to(HERE.parent.parent))
            )
            if result["status"] != "complete":
                case["failure"] = result.get("error")
                if (
                    "pinned storage root" in case["failure"]
                    and not (HERE / "retry/results" / f"{label}.json").exists()
                ):
                    case["status"] = "setup_failed_retry_pending"
                continue
            baseline = read(folder / "baselines" / f"{label}.json")
            assert baseline["session_id"] == case["member"]["session_id"]
            case["baseline"] = {a["name"]: a["selected"] for a in baseline["methods"][0]["arms"]}
            case["baseline_source"] = str(
                (folder / "baselines" / f"{label}.json").relative_to(HERE.parent.parent)
            )
            case["baseline_mode"] = result["baseline_mode"]
            case["candidate"] = {}
            extension = result["extension"]
            for arm, op in extension["operational"].items():
                raw = extension["stages"].get("slope-0.25", {}).get(arm)
                case["candidate"][arm] = dict(
                    error_km=op["error_km"],
                    rms_hz=op["posterior_rms_hz"],
                    raw_converged=raw["converged"] if raw else False,
                    fallback=op["stage"] if op["stage"] != "slope-0.25" else None,
                    objective=op.get("objective"),
                )
            case.pop("failure", None)
            case["upstream_stopped"] = result["upstream"]["stopped"]
            case["stage_failures"] = {
                stage: [arm for arm in ARMS if not rows[arm]["converged"]]
                for stage, rows in {**result["upstream"]["stages"], **extension["stages"]}.items()
                if any(not rows[arm]["converged"] for arm in ARMS)
            }
        if case["candidate"] and case["baseline"]:
            case["paired_delta_km"] = {
                a: case["candidate"][a]["error_km"]
                - case["baseline"][a]["horizontal_error_m"] / 1000
                for a in ARMS
            }
    assert len(cases) == 148 and len({r["member"]["session_id"] for r in cases}) == 148
    datasets = {
        d: metrics([r for r in cases if r["member"]["dataset"] == d])
        for d in ("DS16", "DS17", "DS18")
    }
    groups = {}
    for d in ("DS16", "DS18"):
        for consumed in (True, False):
            group = [
                r
                for r in cases
                if r["member"]["dataset"] == d
                and (r["member"]["exposure"] == "previously_evaluated_consumed") == consumed
            ]
            groups[f"{d}-{'historical' if consumed else 'completion'}"] = metrics(group)
    summary = dict(datasets=datasets, groups=groups, pooled=metrics(cases), cases=cases)
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    figure, axes = plt.subplots(1, 3, figsize=(14, 4.5))
    for ax, dataset in zip(axes, datasets, strict=True):
        selected = [r for r in cases if r["member"]["dataset"] == dataset and r["candidate"]]
        for arm, color in zip(ARMS, ("tab:blue", "tab:orange"), strict=True):
            for method, style in (("baseline", "--"), ("candidate", "-")):
                errors = sorted(
                    r[method][arm]["horizontal_error_m"] / 1000
                    if method == "baseline"
                    else r[method][arm]["error_km"]
                    for r in selected
                )
                ax.step(
                    errors,
                    np.arange(1, len(errors) + 1) / len(errors),
                    where="post",
                    color=color,
                    linestyle=style,
                    label=f"{method} {arm}",
                )
        ax.set(
            xscale="log",
            xlabel="Position error km",
            ylabel="Evaluated fraction",
            title=f"{dataset}: {len(selected)}/{datasets[dataset]['membership']}",
        )
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8)
    figure.tight_layout()
    figure.savefig(HERE / "comparison.png", dpi=160)
    text = """# Iteration 45: expanded DS16/DS17/DS18 descriptive benchmark

All 148 frozen members are accounted for below. Evaluated/full denominators are
explicit; incomplete coverage is never presented as a full-dataset mean. The
candidate remains the unchanged joint-clock, additive-region, timing-pruning,
RF-time and satellite-slope-0.25 sequence from iterations 20 and 28. None of the
later oracle-region rescue results replaces an operational result.

![Dataset-specific error distributions](comparison.png)

## Position accuracy

| Dataset evaluated/full | Arm | Method | Mean km | Median km | p95 km | Worst km |
|---|---|---|---:|---:|---:|---:|
"""
    for dataset, result in datasets.items():
        for arm in ARMS:
            for method in ("baseline", "candidate"):
                s = result["arms"][arm][method]
                text += (
                    f"| {dataset} {result['evaluated']}/{result['membership']} | "
                    f"{arm} | {method} | "
                )
                text += (
                    " | ".join(f"{s[k]:.3f}" for k in ("mean", "median", "p95", "worst")) + " |\n"
                )
    text += """
## Paired regressions, convergence and frequency fit

Frequency-fit changes are separate from position accuracy. Models have different
nuisance terms and priors, so baseline/candidate objective differences are not
interpreted as accuracy improvement. Raw scores and all stage receipts remain in
the linked result JSON. c=0/fitted-c share observations, banks, priors, starts and
budgets within each frozen stage; c=0 additionally fixes RF-time terms to zero.
Reference coordinates enter error reporting after inference only.

| Dataset | Arm | Better/worse/tied | Base failed | Raw failed/fallback | RMS before → after Hz |
|---|---|---:|---:|---:|---:|
"""
    for dataset, result in datasets.items():
        for arm, r in result["arms"].items():
            rms = r["frequency_rms_hz"]
            text += (
                f"| {dataset} | {arm} | {r['improved']}/{r['regressed']}/{r['unchanged']} | "
                f"{r['baseline_nonconverged']} | {r['final_raw_nonconverged']}/{r['fallbacks']} | "
                f"{rms['baseline_mean']:.2f} → {rms['candidate_mean']:.2f} |\n"
            )
    text += """
Ties use 1 m tolerance. Final raw failures count the satellite-slope stage and
include inability to reach it; earlier-stage failures are preserved separately.
Full member-paired deltas are in summary.json. Largest fitted-c regressions:

| Member | Baseline km | Candidate km | Regression km |
|---|---:|---:|---:|
"""
    ranked = sorted(
        (r for r in cases if r.get("paired_delta_km")),
        key=lambda r: r["paired_delta_km"]["fitted-c"],
        reverse=True,
    )
    for r in ranked[:10]:
        text += (
            f"| {r['member']['inventory_label']} | "
            f"{r['baseline']['fitted-c']['horizontal_error_m'] / 1000:.3f} | "
            f"{r['candidate']['fitted-c']['error_km']:.3f} | "
            f"{r['paired_delta_km']['fitted-c']:.3f} |\n"
        )
    text += """
## Historical subsets and completion members

DS16's earlier 48 members and remaining 15 stay distinguishable. DS18's earlier
24 are consumed research data; its other ten lack registry matches, which is not
proof of unseen validation. No outcome-based membership filter was applied.

| Group evaluated/full | Arm | Baseline mean km | Candidate mean km |
|---|---|---:|---:|
"""
    for name, group in groups.items():
        for arm, r in group["arms"].items():
            text += (
                f"| {name} {group['evaluated']}/{group['membership']} | {arm} | "
                f"{r['baseline']['mean']:.3f} | {r['candidate']['mean']:.3f} |\n"
            )
    text += """
## Provenance and operational status

The DS18 final manifest SHA256 is
`894a6f4b7055e5f6bd602f94ce3acf7f722f204c68c2b521a06dfd6be35a7516`.
Its sealed capture-start window and all 34 members are unchanged. DS18-034's
later publication is bound to its sealed IQ digest in iteration44/archive-binding.json.
The original pre-publication authority remains intact.

Baseline uses hard60 configuration
`d1524c45e6e702008221d941240e7a0ac26f13feac87fef73e83f04c9c0a80f6`.
Compatible publications are reused; other baselines are run in isolated storage,
at most four resumable 500-second slices per invocation. Production publications,
default settings and longest-16-track PNG rendering remain unchanged. No RF was collected.

Initial missing-output-directory errors happened before baseline fitting and are
retained in results/. Identical frozen retries live in retry/results/. A repaired
setup attempt is never silently erased. Numerical convergence failures use only
the pre-existing model fallbacks. Source, configuration and input bindings are
recorded with the results; full membership and coverage follows.

| Member | Session | Outcome | Fitted-c error km | Zero-c error km |
|---|---|---|---:|---:|
"""
    for r in cases:
        errors = [f"{r['candidate'][a]['error_km']:.3f}" if r["candidate"] else "—" for a in ARMS]
        text += (
            f"| {r['member']['inventory_label']} | {r['member']['session_id']} | "
            f"{r['status']} {r.get('failure', '')} | {errors[0]} | {errors[1]} |\n"
        )
    (HERE / "README.md").write_text(text)
    print(json.dumps(dict(datasets=datasets, groups=groups), indent=2))


if __name__ == "__main__":
    main()
