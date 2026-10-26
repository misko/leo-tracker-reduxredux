"""Final geography for all sealed CH8 experiments; no inference imports."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def load(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def distance(point, reference):
    # Same regional-coordinate conversion as the archived baseline evaluator.
    lat = 37.906 + point[1] / 111.0
    lon = -122.545 + point[0] / (111.32 * math.cos(math.radians(37.906)))
    a, b, c, d = map(math.radians, (lat, lon, *reference))
    h = math.sin((c-a)/2)**2 + math.cos(a)*math.cos(c)*math.sin((d-b)/2)**2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1., max(0., h))))


def evaluate(study, out, reference):
    cfo = study / "cfo"
    seals = [cfo/n for n in ("RF_seal.json", "rf_report/RF_seal.json",
        "position/RF_seal.json", "channel_RF_seal.json", "terminal_seal.json")]
    checked = {}
    for seal in seals:
        for name, digest in load(seal)["files"].items():
            assert sha(name) == digest, f"sealed artifact changed: {name}"
            checked[name] = digest
        checked[str(seal)] = sha(seal)
    rows = [dict(row) for path in (cfo/"position/execution.json", cfo/"channel_execution.json")
            for case in load(path)["results"] for row in case["rows"]]
    assert len(rows) == 24 and all(r["status"] == "complete" and not r["GPS_used"] for r in rows)
    keys = [(r["case"], r["kind"], r["method"], r["arm"]) for r in rows]
    assert len(set(keys)) == len(rows)
    totals = {}
    for case in ("DS24-0010", "DS24-0011"):
        path = Path("/srv/bulk/leo/research/ds25-20261024")/case/"observations.json"
        values = load(path)
        totals[case] = len({o["observation_id"] for o in values})
        assert totals[case] == len(values)
        checked[str(path)] = sha(path)
    for row in rows:
        row["error_km"] = distance(row["endpoint_east_north_km"], reference)
        row["all_GLRT_points"] = totals[row["case"]]
        row["GLRT_associated_percent"] = 100*row["associated_IDs"]/row["all_GLRT_points"]
    paired = []
    for row in rows:
        if row["method"] == "original":
            continue
        original, = [r for r in rows if r["case"] == row["case"] and r["kind"] == row["kind"]
                     and r["arm"] == row["arm"] and r["method"] == "original"]
        same_pair = [r for r in rows if all(r[k] == row[k] for k in ("case", "kind", "method"))]
        assert len(same_pair) == 2
        assert row["likelihood_points"] == original["likelihood_points"]
        paired.append(dict(case=row["case"], kind=row["kind"], method=row["method"], arm=row["arm"],
            original_error_km=original["error_km"], corrected_error_km=row["error_km"],
            improvement_m=1000*(original["error_km"]-row["error_km"]),
            endpoint_movement_m=1000*math.dist(row["endpoint_east_north_km"], original["endpoint_east_north_km"]),
            objective_change=row["objective"]-original["objective"],
            frequency_RMS_change_hz=row["conditional_RMS_hz"]-original["conditional_RMS_hz"],
            original_associated_points=original["associated_IDs"], corrected_associated_points=row["associated_IDs"],
            all_GLRT_points=row["all_GLRT_points"], corrected_GLRT_associated_percent=row["GLRT_associated_percent"],
            postfit_IDs_lost=row["postfit_IDs_lost"],
            all_fitted_checks_pass=all(r["single_arm_valid"] and r["Gamma_converged"] and
                r["final_phase_change_s"] <= .01 and r["maximum_unclipped_phase_s"] <= 15.000001 for r in same_pair),
            extra_paired_retention_rule_passes=all(r["all_original_accepted_IDs_preserved"] for r in same_pair)))
    assert len(paired) == 16
    # Independent consistency with the earlier final-evaluation report.
    previous = load(cfo/"geographic/summary.json")
    for row in rows[:16]:
        old, = [r for r in previous["rows"] if all(r[k] == row[k] for k in ("case", "kind", "method", "arm"))]
        assert abs(row["error_km"]-old["error_km"]) < 1e-12
    out.mkdir(parents=True, exist_ok=True)
    write(out/"summary.json", dict(rows=rows, comparisons=paired, evaluation_reference_latlon=reference,
        inference_input_hashes=checked, evaluation_only_GPS=True, independent_validation=False,
        regional_association_rerun=False, all_24_endpoints_reported=True,
        interpretation="Two exposed development scans; fixed identities, cold regional-center/zero-phase fits."))
    with (out/"paired.csv").open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(paired[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(paired)
    make_figures(rows, paired, out)
    write(out/"seal.json", dict(files={str(p):sha(p) for p in sorted(out.iterdir()) if p.is_file()},
        evaluator_sha256=sha(__file__), GPS_used_only_in_evaluation=True))
    for row in paired:
        print(row)


def make_figures(rows, paired, out):
    colors = {"original":"#656565", "CH8_only":"#007e80", "CH7_only":"#bd7433", "refined":"#81569f"}
    names = {"original":"Original", "CH8_only":"Refine CH8", "CH7_only":"Refine CH7", "refined":"Refine both"}
    cases = ("DS24-0010", "DS24-0011")
    arms = ("c0", "fitted_c")
    labels = [c[-4:]+"\n"+("c=0" if a == "c0" else "fitted c") for c in cases for a in arms]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.7), layout="constrained")
    for i, method in enumerate(colors):
        rr = [next(r for r in rows if r["case"]==c and r["arm"]==a and r["kind"]=="ordinary_VI"
                   and r["method"]==method) for c in cases for a in arms]
        axes[0].bar(np.arange(4)+(i-1.5)*.20, [r["error_km"] for r in rr], .19, color=colors[method], label=names[method])
        if method != "original":
            pp = [next(p for p in paired if p["case"]==c and p["arm"]==a and p["kind"]=="ordinary_VI"
                       and p["method"]==method) for c in cases for a in arms]
            for j, p in enumerate(pp):
                x = j+(i-2)*.22
                axes[1].bar(x, p["improvement_m"], .21, color=colors[method],
                    hatch="//" if not p["extra_paired_retention_rule_passes"] else None)
                axes[1].text(x, p["improvement_m"]+(0.4 if p["improvement_m"]>=0 else -.4),
                    f'{p["improvement_m"]:+.1f}', ha="center", va="bottom" if p["improvement_m"]>=0 else "top", fontsize=8)
    axes[0].set_ylabel("Final evaluation position error (km)"); axes[0].set_ylim(0, 1.95)
    axes[0].set_title("All channels remain in the position fit"); axes[0].legend(fontsize=8, ncols=2)
    axes[1].axhline(0, color="black", lw=.7); axes[1].set_ylabel("Position-error reduction (m); positive is better")
    axes[1].set_title("Correction attribution: improvements are small")
    axes[1].margins(y=.25)
    for ax in axes:
        ax.set_xticks(range(4), labels); ax.grid(axis="y", alpha=.2); ax.set_axisbelow(True)
    fig.suptitle("CH8 development tests · fixed identities · ordinary VI\nHatching: extra paired retention rule fails; fitted residual/phase checks pass", fontsize=11)
    for suffix in ("png", "pdf"):
        fig.savefig(out/f"channel_attribution.{suffix}", dpi=180)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.5), layout="constrained")
    for ax, field, title in zip(axes, ("improvement_m", "frequency_RMS_change_hz"),
                               ("Position-error reduction (m); positive is better", "Frequency RMS change (Hz); negative is better"), strict=True):
        for i, kind in enumerate(("ordinary_VI", "fixed_original_full_precision_packet")):
            pp = [next(p for p in paired if p["case"]==c and p["arm"]==a and p["kind"]==kind and p["method"]=="refined")
                  for c in cases for a in arms]
            ax.bar(np.arange(4)+(i-.5)*.35, [p[field] for p in pp], .33,
                   color=("#81569f", "#446f92")[i], label=("Ordinary VI", "Frozen original precisions")[i])
        ax.axhline(0, color="black", lw=.7); ax.set_xticks(range(4), labels); ax.set_ylabel(title)
        ax.grid(axis="y", alpha=.2); ax.legend(fontsize=8); ax.set_axisbelow(True)
    fig.suptitle("Refine both CH7 and CH8: frequency fit and position accuracy are different outcomes", fontsize=11)
    for suffix in ("png", "pdf"):
        fig.savefig(out/f"precision_comparison.{suffix}", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--study", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--reference-latlon", required=True, type=float, nargs=2)
    args = parser.parse_args()
    evaluate(args.study, args.out, args.reference_latlon)
