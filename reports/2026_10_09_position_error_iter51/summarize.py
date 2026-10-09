"""Full-denominator progress and paired metrics for the uniform region policy."""

import json
from datetime import UTC, datetime
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter  # noqa: E402

HERE = Path(__file__).resolve().parent
ARMS = ("fitted-c", "zero-c")


def read(path):
    return json.loads(path.read_text())


def values(row, baseline=False):
    return dict(
        error_km=row["horizontal_error_m"] / 1000 if baseline else row["error_km"],
        rms_hz=row.get("posterior_rms_hz", row.get("rms_hz")),
        converged=row.get("converged", row.get("raw_converged")),
    )


def stats(values):
    return dict(
        n=len(values),
        mean=float(np.mean(values)),
        median=float(np.median(values)),
        p95=float(np.percentile(values, 95)),
        worst=float(max(values)),
    )


def main():
    protocol = read(HERE / "protocol.json")
    cases = []
    for binding in protocol["members"]:
        member = binding["member"]
        label = member["inventory_label"]
        row = dict(member=member, status="not_run", arms=None)
        path = HERE / "results" / f"{label}.json"
        pending = HERE / "pending" / f"{label}.json"
        if path.exists():
            result = read(path)
            row["status"] = result["status"]
            if result["status"] == "complete":
                row.update(
                    arms={},
                    sources=result["upstream"]["regional_sources"],
                    region_receipts=result["region_receipts"],
                    elapsed_s=result["elapsed_s"],
                    upstream_stopped=result["upstream"]["stopped"],
                )
                for arm in ARMS:
                    raw = result["extension"]["stages"].get("slope-0.25", {}).get(arm)
                    op = result["extension"]["operational"][arm]
                    row["arms"][arm] = dict(
                        baseline=values(result["baseline_arms"][arm], True),
                        previous=values(result["previous_candidate"][arm]),
                        candidate=values(op),
                        raw_final_converged=raw["converged"] if raw else None,
                        fallback=op["stage"] if op["stage"] != "slope-0.25" else None,
                        paired_delta_km=op["error_km"]
                        - result["previous_candidate"][arm]["error_km"],
                    )
            else:
                row["failure"] = result.get("error")
        elif pending.exists():
            row.update(status="pending_baseline", reason=read(pending)["reason"])
        cases.append(row)
    assert len(cases) == 148
    metrics = {}
    fig, axes = plt.subplots(2, 3, figsize=(14, 8), layout="constrained")
    for col, dataset in enumerate(("DS16", "DS17", "DS18")):
        members = [r for r in cases if r["member"]["dataset"] == dataset]
        complete = [r for r in members if r["status"] == "complete"]
        summary = dict(membership=len(members), complete=len(complete), arms={})
        for i, arm in enumerate(ARMS):
            if not complete:
                continue
            models = {
                name: stats([r["arms"][arm][name]["error_km"] for r in complete])
                for name in ("baseline", "previous", "candidate")
            }
            delta = np.array([r["arms"][arm]["paired_delta_km"] for r in complete])
            summary["arms"][arm] = dict(
                position=models,
                improved=int(sum(delta < -0.001)),
                regressed=int(sum(delta > 0.001)),
                tied=int(sum(abs(delta) <= 0.001)),
                final_failed=sum(r["arms"][arm]["raw_final_converged"] is False for r in complete),
                final_not_reached=sum(
                    r["arms"][arm]["raw_final_converged"] is None for r in complete
                ),
                fallbacks=sum(bool(r["arms"][arm]["fallback"]) for r in complete),
                mean_frequency_rms_hz={
                    name: float(np.mean([r["arms"][arm][name]["rms_hz"] for r in complete]))
                    for name in models
                },
            )
            for model, style in (("baseline", ":"), ("previous", "--"), ("candidate", "-")):
                errors = sorted(r["arms"][arm][model]["error_km"] for r in complete)
                axes[i, col].step(
                    errors,
                    np.arange(1, len(errors) + 1) / len(errors),
                    where="post",
                    linestyle=style,
                    label=model,
                )
            axes[i, col].set(
                xscale="log",
                xlabel="Position error km",
                ylabel="Evaluated fraction",
                title=f"{dataset} {len(complete)}/{len(members)} {arm}",
            )
            axes[i, col].legend(fontsize=8)
            axes[i, col].grid(alpha=0.2)
            axes[i, col].xaxis.set_major_locator(LogLocator(base=10, subs=(1, 3)))
            axes[i, col].xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}"))
            axes[i, col].xaxis.set_minor_formatter(NullFormatter())
        metrics[dataset] = summary
    fig.savefig(HERE / "comparison.png", dpi=160)
    summary = dict(generated_utc=datetime.now(UTC).isoformat(), metrics=metrics, cases=cases)
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    count = sum(r["status"] == "complete" for r in cases)
    text = f"""# Iteration 51: uniform additive region policy, {count}/148 completed

This is a descriptive completion checkpoint at {summary["generated_utc"]}.
All 63 DS16, 51 DS17 and 34 DS18 members remain in the denominator. Pending,
unstarted and failed members are listed explicitly; subset means are not
full-dataset results. No new independent validation claim is made.

![Paired baseline, previous research and uniform-policy distributions](comparison.png)

## Position error on the matched completed subset

| Dataset evaluated/full | Arm | Model | Mean km | Median km | p95 km | Worst km |
|---|---|---|---:|---:|---:|---:|
"""
    for dataset, metric in metrics.items():
        for arm, value in metric["arms"].items():
            for model, stat in value["position"].items():
                text += (
                    f"| {dataset} {metric['complete']}/{metric['membership']} | {arm} | {model} | "
                )
                text += (
                    " | ".join(f"{stat[k]:.3f}" for k in ("mean", "median", "p95", "worst"))
                    + " |\n"
                )
    text += """
Baseline is deployed bounded-recovery hard60 (including qualified historical
replays). Previous is the frozen joint-clock/RF-time/satellite-slope research
candidate. Candidate retains baseline, sep25 and sep50 regions and selects each
arm by eligible regional score, then runs the same downstream model. Original
choices are never discarded because of their reference error.

## Paired changes and frequency fit

| Dataset | Arm | Better/worse/tied | Failed/not reached | Fallbacks | RMS base/previous/new Hz |
|---|---|---:|---:|---:|---:|
"""
    for dataset, metric in metrics.items():
        for arm, v in metric["arms"].items():
            rms = v["mean_frequency_rms_hz"]
            text += (
                f"| {dataset} | {arm} | {v['improved']}/{v['regressed']}/{v['tied']} | "
                f"{v['final_failed']}/{v['final_not_reached']} | {v['fallbacks']} | "
                f"{rms['baseline']:.2f}/{rms['previous']:.2f}/{rms['candidate']:.2f} |\n"
            )
    text += """
Position ties use 1 m tolerance. Frequency RMS is separate from localization;
objectives from different models/banks are not treated as position accuracy.
c=0 and fitted-c retain matched observations, candidate sets, priors, seeds and
budgets within each stage; c=0 also locks RF-time terms. Failed final fits use
only the frozen convergence fallbacks, whose exact receipts remain in results/.

The policy adds computation: the identical ordered 400-point grid is reused,
but new regional calibrations/fits are required. Some older scans had no sep25
replay, so this uniform policy computes missing sep25 as well as sep50. This is
not an equal-total-compute comparison. Each result records archived/new replay
status, borrowed stages and elapsed time. DS16-046 reuses its already consumed
sep50 diagnostic; its success is not relabeled independent validation.

The protocol includes every frozen member, authority/exposure metadata, source
hashes and bindings. DS18 authority and seal remain unchanged. No readiness or
quality filter changes membership. Production, public contracts, golden fixtures,
QNAP data and RF collection are unchanged. Results do not promote a new default.

## Full membership and outcomes

| Member | Session | Outcome | Fitted-c new km | Zero-c new km | Exposure |
|---|---|---|---:|---:|---|
"""
    for row in cases:
        m = row["member"]
        errors = [
            f"{row['arms'][a]['candidate']['error_km']:.3f}" if row["arms"] else "—" for a in ARMS
        ]
        status = row["status"] + " " + row.get("failure", row.get("reason", ""))
        text += (
            f"| {m['inventory_label']} | {m['session_id']} | {status} | "
            f"{errors[0]} | {errors[1]} | {m['exposure']} |\n"
        )
    (HERE / "README.md").write_text(text)
    print("Completed", count, "/148", {d: v["complete"] for d, v in metrics.items()})


if __name__ == "__main__":
    main()
