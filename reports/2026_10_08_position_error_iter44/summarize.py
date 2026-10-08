"""Full-manifest coverage and paired descriptive comparisons, without exclusions."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
ARMS = ("fitted-c", "zero-c")


def read(path):
    return json.loads(path.read_text())


def stats(values):
    return dict(
        n=len(values),
        mean=float(np.mean(values)),
        median=float(np.median(values)),
        p95=float(np.percentile(values, 95)),
        worst=float(np.max(values)),
    )


def main():
    readiness = read(HERE / "readiness.json")
    gaps = {r["member"]["inventory_label"]: r for r in read(HERE / "input-gaps.json")}
    archive = read(HERE / "archive-binding.json")
    assert archive["status"] == "published_after_mint_IQ_digest_verified"
    gaps["DS18-034"] = dict(
        gaps["DS18-034"],
        status="tracking_inputs_ready_IQ_bound",
        error=None,
        binding_correction=archive,
    )
    cases = []
    for row in readiness["members"]:
        member = row["member"]
        label = member["inventory_label"]
        item = dict(
            member=member,
            status="pending",
            baseline=None,
            candidate=None,
            input_audit=gaps.get(label),
        )
        prior = member["research_errors"]
        if prior:
            item.update(status="complete_prior_consumed", candidate=prior)
            if any(label.startswith("RESERVED-") for label in member["legacy_labels"]):
                reserved = read(REPORTS / "2026_10_08_position_error_iter29/summary.json")
                receipt = next(
                    r
                    for r in reserved["cases"]
                    if r["member"]["session_id"] == member["session_id"]
                )
                for arm in ARMS:
                    original = receipt["arms"][arm]
                    item["candidate"][arm]["raw_converged"] = original["final_raw_converged"]
                    stage = original["variants"]["slope-0.25"]["stage"]
                    item["candidate"][arm]["fallback"] = stage if stage != "slope-0.25" else None
            if member["dataset"] == "DS16":
                old = member["legacy_labels"][0]
                source = REPORTS / "2026_10_08_hard60_bounded_recovery/cohort" / f"{old}.json"
                baseline = read(source)
                assert baseline["session_id"] == member["session_id"]
                item["baseline"] = {a: baseline["arms"][a]["actual"] for a in ARMS}
                item["baseline_source"] = str(source.relative_to(REPORTS.parent))
            elif member["dataset"] == "DS17":
                source = REPORTS / "2026_10_08_position_error_iter01/baseline" / f"{label}.json"
                baseline = read(source)
                assert baseline["session_id"] == member["session_id"]
                assert baseline["configuration"]["run"] == readiness["expected_configuration"]
                item["baseline"] = {
                    a["name"]: a["selected"] for a in baseline["methods"][0]["arms"]
                }
                item["baseline_source"] = str(source.relative_to(REPORTS.parent))
            else:
                assert row["baseline_status"] == "compatible"
                item.update(baseline=row["baseline_arms"], baseline_source=row["document_digest"])
        path = HERE / "results" / f"{label}.json"
        if path.exists():
            result = read(path)
            item["status"] = result["status"]
            if result["status"] == "complete":
                extension = result["extension"]
                item["candidate"] = {}
                for arm, op in extension["operational"].items():
                    raw = extension["stages"].get("slope-0.25", {}).get(arm)
                    item["candidate"][arm] = dict(
                        error_km=op["error_km"],
                        rms_hz=op["posterior_rms_hz"],
                        raw_converged=raw["converged"] if raw else False,
                        fallback=op["stage"] if op["stage"] != "slope-0.25" else None,
                        objective=op.get("objective"),
                    )
                item.update(baseline=row["baseline_arms"], baseline_source=row["document_digest"])
                item["upstream_stopped"] = result["upstream"]["stopped"]
            else:
                item["failure"] = result["error"]
        cases.append(item)
    metrics = {}
    fig, axes = plt.subplots(2, 3, figsize=(14, 8))
    tables = []
    frequency = []
    for index, dataset in enumerate(("DS16", "DS17", "DS18")):
        members = [r for r in cases if r["member"]["dataset"] == dataset]
        paired = [r for r in members if r["candidate"] and r["baseline"]]
        metrics[dataset] = dict(members=len(members), paired=len(paired), arms={})
        for arm, color in zip(ARMS, ("tab:blue", "tab:orange"), strict=True):
            baseline = np.array([r["baseline"][arm]["horizontal_error_m"] / 1000 for r in paired])
            candidate = np.array([r["candidate"][arm]["error_km"] for r in paired])
            brms = np.array([r["baseline"][arm]["posterior_rms_hz"] for r in paired])
            crms = np.array([r["candidate"][arm]["rms_hz"] for r in paired])
            values = dict(
                baseline=stats(baseline),
                candidate=stats(candidate),
                improved=int(sum(candidate < baseline - 0.001)),
                regressed=int(sum(candidate > baseline + 0.001)),
                unchanged=int(sum(abs(candidate - baseline) <= 0.001)),
                baseline_nonconverged=sum(not r["baseline"][arm]["converged"] for r in paired),
                final_raw_nonconverged=sum(
                    r["candidate"][arm].get("raw_converged") is False for r in paired
                ),
                final_convergence_unknown=sum(
                    "raw_converged" not in r["candidate"][arm] for r in paired
                ),
                fallback_count=sum(bool(r["candidate"][arm].get("fallback")) for r in paired),
                frequency_mean_rms_hz=dict(
                    baseline=float(brms.mean()), candidate=float(crms.mean())
                ),
            )
            metrics[dataset]["arms"][arm] = values
            for method in ("baseline", "candidate"):
                s = values[method]
                tables.append(
                    f"| {dataset} {len(paired)}/{len(members)} | {arm} | {method} | "
                    + " | ".join(f"{s[k]:.3f}" for k in ("mean", "median", "p95", "worst"))
                    + " |"
                )
            frequency.append(
                f"| {dataset} | {arm} | {brms.mean():.2f} | {crms.mean():.2f} | "
                f"{values['improved']}/{values['regressed']}/{values['unchanged']} | "
                f"{values['final_raw_nonconverged']}/{values['fallback_count']} |"
            )
            axes[0, index].scatter(baseline, candidate, c=color, s=18, alpha=0.7, label=arm)
            axes[1, index].plot(
                np.sort(candidate),
                np.arange(1, len(candidate) + 1) / len(candidate),
                color=color,
                label=arm,
            )
        upper = max(r["baseline"][a]["horizontal_error_m"] / 1000 for r in paired for a in ARMS)
        axes[0, index].plot(
            [0.05, max(upper, 60)], [0.05, max(upper, 60)], color="gray", linestyle="--"
        )
        axes[0, index].set(
            xscale="log",
            yscale="log",
            xlabel="Baseline error km",
            ylabel="Candidate error km",
            title=f"{dataset}: {len(paired)}/{len(members)}",
        )
        axes[1, index].set(
            xscale="log", xlabel="Candidate error km", ylabel="Fraction of evaluated members"
        )
        for ax in axes[:, index]:
            ax.grid(alpha=0.2)
            ax.legend()
    fig.tight_layout()
    fig.savefig(HERE / "comparison.png", dpi=160)
    (HERE / "summary.json").write_text(
        json.dumps(dict(metrics=metrics, cases=cases), indent=2) + "\n"
    )
    text = (
        """# Iteration 44: expand DS18 coverage and restore paired baselines

The frozen research candidate is compared with bounded-recovery hard60 on the
available matched members below. **These are subset statistics wherever the
coverage denominator is incomplete.** All 148 members remain in the inventory.
No new RF collection or production change was made.

![Paired errors and candidate distributions](comparison.png)

| Dataset evaluated/full | Arm | Method | Mean km | Median km | p95 km | Worst km |
|---|---|---|---:|---:|---:|---:|
"""
        + "\n".join(tables)
        + """

## Frequency fit and numerical qualification

Frequency RMS is reported separately from position accuracy. Baseline and research
objectives have different nuisance models and priors; their objective differences
are not a localization improvement metric. The unchanged stage sequence pairs c=0
and fitted-c with matched observations, candidate sets, priors, seeds and budgets;
c=0 also locks RF-time terms. Fitted-c is never selected using reference position.

| Dataset | Arm | Baseline RMS Hz | Candidate RMS Hz | Better/worse/tied | Failures/fallbacks |
|---|---|---:|---:|---:|---:|
"""
        + "\n".join(frequency)
        + """

Position ties use a 1 m tolerance. Final raw failure counts describe the final
slope stage; earlier-stage convergence and fallbacks remain in original result
receipts. Missing convergence fields are explicit in summary.json, not counted
as success. The historical 24 DS18 cases are already consumed; registry absence
for ten others does not establish unseen validation.

## Sources and full membership

The final DS18 manifest matches SHA256
`894a6f4b7055e5f6bd602f94ce3acf7f722f204c68c2b521a06dfd6be35a7516`;
all 42 seal entries verified. The authority window and membership are unchanged.
DS16 baselines come from the archived integrated bounded-recovery replay; DS17
from its archived bounded-recovery documents; DS18 from digest-bound compatible
publications. Old live DS16/DS17 publications often predate recovery and are not
silently substituted. The eight new results use unchanged iterations 20+28,
frozen in protocol.json before execution. Oracle rescue experiments are excluded.

[summary.json](summary.json) retains every member, source binding, exposure label,
paired result, and gap. [input-gaps.json](input-gaps.json) records concrete source
checks. All 17 pending baseline cases have tracking inputs. DS18-034 was published
after minting; its initial assertion against the absent publication digest is
superseded by [archive-binding.json](archive-binding.json), which verifies the
published IQ digest against the sealed archive member. This does not change membership.
Full status inventory:

| Member | Session | Evaluation | Input / baseline gap |
|---|---|---|---|
"""
    )
    for r in cases:
        gap = r["input_audit"] or {}
        text += (
            f"| {r['member']['inventory_label']} | {r['member']['session_id']} | "
            f"{r['status']} | {gap.get('error', gap.get('status', '—'))} |\n"
        )
    (HERE / "README.md").write_text(text)
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
