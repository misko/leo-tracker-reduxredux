"""Postfit RF-only C diagnostics; no threshold selection or geography access."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent
REPORT = ROOT.parent


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def describe(values):
    values = np.asarray(values, float)
    if not len(values):
        return dict(count=0)
    q = np.quantile(values, [0, .25, .5, .75, .9, 1])
    return dict(count=len(values), minimum=float(q[0]), q25=float(q[1]),
                median=float(q[2]), q75=float(q[3]), p90=float(q[4]), maximum=float(q[5]))


def write_csv(path, rows):
    if not rows:
        Path(path).write_text("")
        return
    with Path(path).open("w") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def summarize(results_path, audit_path):
    results, audit = read(results_path), read(audit_path)
    digest = sha(results_path)
    if audit["status"] != "passed" or audit["results_sha256"] != digest:
        raise ValueError("Successful combined RF audit binding required before summary")
    rows, pairs, reasons = [], [], Counter()
    accepted_B = sum(bool(r["variants"]["A+B"]["accepted"]) for r in results["rows"])
    guard_statuses = Counter()
    for case in results["rows"]:
        variant = case["variants"]["A+B+C"]
        guards = variant.get("geometry_guards", {})
        pair = dict(case=case["case"], dataset=case["dataset"],
            B_accepted=bool(case["variants"]["A+B"]["accepted"]),
            C_accepted=bool(variant["accepted"]),
            recorded_guard_arms=len(guards),
            C_fully_evaluated=set(guards) == {"c0", "fitted_c"}
                and all(g.get("status") == "complete" for g in guards.values()))
        for arm in ("c0", "fitted_c"):
            g = guards.get(arm)
            pair[arm+"_information"] = None
            pair[arm+"_RF_gain"] = None
            pair[arm+"_Gaussian_all_widths_favor_candidate"] = None
            if g is None:
                continue
            guard_statuses[g["status"]] += 1
            reasons.update(g["reasons"])
            if g["status"] != "complete":
                continue
            prior = g["nominal_gaussian_prior_sensitivity"]
            gains = {float(item["prior_SD_multiplier"]):item["normalized_gaussian_gain"] for item in prior}
            lofo = g["leave_one_family_out"]
            row = dict(case=case["case"], dataset=case["dataset"], arm=arm,
                B_pair_accepted=pair["B_accepted"], C_arm_pass=bool(g["guard_pass"]),
                displacement_km=g["displacement_km"], other_families=len(g["other_families"]),
                other_points=g["other_points"], information=g["full"]["displacement_information"],
                RF_gain=g["full"]["projected_RF_gain"],
                raw_information=g["full"]["unprojected_displacement_information"],
                retained_information_fraction=g["full"]["retained_displacement_information_fraction"],
                nuisance_confounding_fraction=g["full"]["nuisance_confounding_fraction"],
                nuisance_rank=g["full"]["nuisance_rank"], residual_dimension=g["full"]["residual_dimension"],
                minimum_LOFO_information=min((item["displacement_information"] for item in lofo), default=None),
                minimum_LOFO_RF_gain=min((item["projected_RF_gain"] for item in lofo), default=None),
                gaussian_gain_SD05=gains[.5], gaussian_gain_SD1=gains[1.], gaussian_gain_SD2=gains[2.],
                gaussian_all_widths_favor_candidate=all(value > 0 for value in gains.values()),
                gaussian_width_ordering_changes=min(gains.values()) < 0 < max(gains.values()),
                reasons=";".join(g["reasons"]))
            rows.append(row)
            pair[arm+"_information"] = row["information"]
            pair[arm+"_RF_gain"] = row["RF_gain"]
            pair[arm+"_Gaussian_all_widths_favor_candidate"] = row["gaussian_all_widths_favor_candidate"]
        pairs.append(pair)
    by_arm = {}
    for arm in ("c0", "fitted_c"):
        arm_rows = [r for r in rows if r["arm"] == arm]
        by_arm[arm] = dict(
            complete_guards=len(arm_rows), guard_passes=sum(r["C_arm_pass"] for r in arm_rows),
            displacement_km=describe([r["displacement_km"] for r in arm_rows]),
            unprojected_information=describe([r["raw_information"] for r in arm_rows]),
            information=describe([r["information"] for r in arm_rows]),
            RF_gain=describe([r["RF_gain"] for r in arm_rows]),
            retained_information_fraction=describe([r["retained_information_fraction"] for r in arm_rows]),
            retained_information_fraction_when_raw_nonzero=describe([r["retained_information_fraction"]
                for r in arm_rows if r["raw_information"] > 0]),
            exactly_zero_raw_information_arms=sum(r["raw_information"] == 0 for r in arm_rows),
            gaussian_gains={str(scale):describe([r[key] for r in arm_rows]) for scale, key in
                [(.5, "gaussian_gain_SD05"), (1., "gaussian_gain_SD1"), (2., "gaussian_gain_SD2")]},
            gaussian_all_widths_favor_candidate=sum(r["gaussian_all_widths_favor_candidate"] for r in arm_rows),
            gaussian_width_ordering_changes=sum(r["gaussian_width_ordering_changes"] for r in arm_rows),
            gaussian_all_widths_positive_but_projection_abstains=sum(r["gaussian_all_widths_favor_candidate"]
                and not r["C_arm_pass"] for r in arm_rows))
    fully = [p for p in pairs if p["C_fully_evaluated"]]
    output = dict(results_sha256=digest, combined_audit_sha256=sha(audit_path),
        summarizer_sha256=sha(__file__), GPS_read=False, no_fits=True,
        available_pairs=len(results["rows"]), B_accepted_pairs=accepted_B,
        C_fully_evaluated_pairs=len(fully),
        B_accepted_but_no_complete_C_pair=accepted_B-sum(p["B_accepted"] for p in fully),
        C_accepted_pairs=sum(p["C_accepted"] for p in pairs),
        guard_status_counts=dict(guard_statuses), failure_reason_arm_counts=dict(reasons),
        by_arm=by_arm,
        Gaussian_all_three_widths_favor_candidate_in_both_arms_despite_C_abstention=sum(
            p["c0_Gaussian_all_widths_favor_candidate"] and p["fitted_c_Gaussian_all_widths_favor_candidate"]
            and not p["C_accepted"] for p in fully),
        all_executed_numerical_cell_receipts=audit["all_numerical_cell_receipts"],
        executed_cell_status_counts=audit["numerical_cell_status_counts"],
        orphan_unadopted_cell_receipts=audit["orphan_unadopted_numerical_cell_count"],
        checkpoint_or_temporary_only_interrupted_cells=audit["checkpoint_or_temporary_only_interrupted_cell_count"],
        observed_attempted_arm_cell_lower_bound=audit["observed_attempted_arm_cell_lower_bound"],
        raw_cell_accounting_limit=audit["raw_cell_accounting_limit"],
        interpretation="Engineering prior-free projection can remove real position information. "
            "Abstention is not a bad-association finding or evidence of successful risk control. "
            "Positive nominal Gaussian gains are sensitivity diagnostics, not calibrated model "
            "probabilities or guarantees of position accuracy. The current RF data are reused "
            "in selecting endpoints and shared unmodeled errors remain possible.")
    (ROOT/"guard_summary.json").write_text(json.dumps(output, indent=2, allow_nan=False)+"\n")
    write_csv(ROOT/"guard_arm_diagnostics.csv", rows)
    write_csv(ROOT/"guard_pair_diagnostics.csv", pairs)
    plot(rows, reasons)
    print(json.dumps(output, indent=2))


def plot(rows, reasons):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
    colors = {"c0":"#2166ac", "fitted_c":"#b2182b"}
    for arm, marker in [("c0", "o"), ("fitted_c", "^")]:
        selected = [r for r in rows if r["arm"] == arm]
        if selected:
            axes[0].scatter([max(r["information"], 1e-30) for r in selected],
                            [r["gaussian_gain_SD1"] for r in selected],
                            color=colors[arm], marker=marker, s=28, alpha=.8, label=arm)
    axes[0].set_xscale("log")
    axes[0].set_yscale("symlog", linthresh=1.)
    axes[0].axvline(4., color=".4", linestyle="--", linewidth=1)
    axes[0].axhline(0., color=".5", linewidth=.8)
    axes[0].set_xlabel("Other-family displacement information after projection\n(engineering threshold = 4)")
    axes[0].set_ylabel("Nominal Gaussian gain at SD multiplier 1\npositive favors candidate; sensitivity only")
    axes[0].set_title("Prior-supported gain can survive weak free-nuisance geometry")
    if rows:
        axes[0].legend(frameon=False)
    else:
        axes[0].text(.5, .5, "No complete C diagnostics", transform=axes[0].transAxes, ha="center")
    labels = dict(
        fewer_than_three_other_families="Fewer than 3 other families",
        weak_other_family_displacement_information="Weak projected information",
        insufficient_other_family_RF_support_for_displacement="Insufficient projected RF gain",
        weak_leave_one_family_out_displacement_information="Weak family-deletion information",
        contradictory_leave_one_family_out_RF_support="Opposing family-deletion RF",
        other_family_nominal_prediction_below_horizon="Nominal prediction below horizon",
        no_other_family_evidence="No other-family evidence")
    counts = sorted(reasons.items(), key=lambda item:item[1])
    if counts:
        axes[1].barh([labels.get(key,key) for key,_ in counts], [value for _,value in counts], color="#6d8495")
    axes[1].set_xlabel("Guard arm receipts (reasons overlap)")
    axes[1].set_title("Recorded C abstention reasons")
    axes[1].spines[["top", "right"]].set_visible(False)
    fig.suptitle("RF-only geometry guard: conservative abstention, not localization validation", fontsize=12)
    fig.savefig(ROOT/"guard_diagnostics.png", dpi=160)
    fig.savefig(ROOT/"guard_diagnostics.pdf")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=REPORT/"evaluation/combined_results.json")
    parser.add_argument("--audit", type=Path, default=REPORT/"review/combined_audit.json")
    args = parser.parse_args()
    summarize(args.results, args.audit)
