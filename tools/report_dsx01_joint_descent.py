"""Post-fit maps of stepwise satellite reassociation; GPS is evaluation only."""

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from debug_dsx01_purple_basin import finite_hessian
from localize_merged_track_catalogue import distance_km
from map_dsx01_clean_region import factory, finite_gradient, loss
from matplotlib.lines import Line2D
from report_dsx01_radial_restarts import (
    REFERENCE,
    endpoint_groups,
    geographic_position,
    raw_denominators,
    truth_position,
)
from run_dsx01_clean_region import load_scan
from run_dsx01_joint_descent import ARMS, CASES, CENTER, OUTPUT, STARTS, hypothesis_bank


def read_case(case):
    records, bindings = [], {}
    for i, start in enumerate(STARTS):
        path = OUTPUT / case / f"start_{i:02d}.json"
        data = path.read_bytes()
        r = json.loads(data)
        if r["case"] != case or r["start_id"] != i or r["status"] != "complete":
            raise ValueError("wrong or incomplete result")
        if not np.array_equal(r["start_east_north_km"], start):
            raise ValueError("start coordinate mismatch")
        if r["GPS_or_following_TLE_used"] is not False:
            raise ValueError("evaluation-site or noncausal input in inference")
        if set(r["arms"]) != set(ARMS):
            raise ValueError("missing matched c control")
        if records and (
            r["hypotheses"] != records[0]["hypotheses"]
            or r["discovery_bindings"] != records[0]["discovery_bindings"]
            or r["input_audit"] != records[0]["input_audit"]
        ):
            raise ValueError("starts do not share exactly the same candidates and inputs")
        for a in ARMS:
            arm = r["arms"][a]
            trace = arm["trace"]
            scores = np.array([t["score"] for t in trace])
            if np.any(np.diff(scores) > 1e-6):
                raise ValueError("nonmonotone descent")
            if any(t["score"] > min(t["hypothesis_scores"]) + 1.1e-7 for t in trace):
                raise ValueError("a better available association hypothesis was ignored")
            if not np.array_equal(trace[0]["point"], start):
                raise ValueError("trajectory does not begin at the declared start")
            if not np.array_equal(trace[-1]["point"], arm["parameters"]):
                raise ValueError("endpoint does not match accepted trajectory")
        bindings[str(path.relative_to(OUTPUT))] = hashlib.sha256(data).hexdigest()
        records.append(r)
    return records, bindings


def plot_case(case, records):
    fig, axes = plt.subplots(1, 2, figsize=(17, 9), layout="constrained")
    starts, truth = np.array(STARTS), truth_position()
    for ax, arm in zip(axes, ARMS, strict=True):
        values = [r["arms"][arm] for r in records]
        endpoints = np.array([v["parameters"] for v in values])
        groups = endpoint_groups(endpoints)
        colors = plt.get_cmap("tab20")
        angle = np.linspace(0, 2 * np.pi, 300)
        ax.plot(10 * np.cos(angle), 10 * np.sin(angle), color="0.6", ls="--", lw=1)
        for value, group in zip(values, groups, strict=True):
            path = np.array([t["point"] for t in value["trace"]])
            color = colors(int(group) % 20)
            ax.plot(*path.T, color=color, alpha=0.5, lw=0.9, zorder=2)
            ax.scatter(*path[-1], marker="x", color=color, s=30, linewidths=1.2, zorder=5)
            for event in value["switches"]:
                ax.scatter(*event["point"], marker="D", s=16, color=color,
                           edgecolors="black", linewidths=0.4, zorder=4)
            if value["stopped"] == "step_budget":
                ax.scatter(*path[-1], marker="s", s=65, facecolors="none",
                           edgecolors="black", zorder=6)
        ax.scatter(*starts.T, marker="o", s=22, facecolors="white",
                   edgecolors="firebrick", lw=0.9, zorder=6)
        for i, point in enumerate(starts):
            ax.annotate(f"{i:02d}", point, xytext=(2, 5), textcoords="offset points",
                        fontsize=5.7, color="darkred", zorder=8)
        ax.scatter(*truth, marker="*", s=220, color="gold", edgecolors="black", zorder=9)
        for group in np.unique(groups):
            members = endpoints[groups == group]
            center = members.mean(axis=0)
            ax.annotate(f"G{group + 1}: {len(members)}", center, xytext=(12, -18),
                        textcoords="offset points", fontsize=8, weight="bold",
                        color=colors(int(group) % 20),
                        bbox=dict(facecolor="white", alpha=0.8, edgecolor="none"),
                        arrowprops=dict(arrowstyle="-", color="0.5", lw=0.6), zorder=10)
        switches = sum(len(v["switches"]) for v in values)
        caps = sum(v["stopped"] == "step_budget" for v in values)
        ax.set(title=f"{'c = 0' if arm == 'c0' else 'Fitted c'} | 81 starts | "
                     f"{switches} switches | {caps} capped",
               xlabel="East of regional center (km)", ylabel="North of regional center (km)",
               xlim=(-12.5, 12.5), ylim=(-12.5, 12.5), aspect="equal")
        ax.set_xticks(np.arange(-12, 13, 2))
        ax.set_yticks(np.arange(-12, 13, 2))
        ax.grid(alpha=0.18)
    handles = [
        Line2D([], [], marker="o", mfc="white", mec="firebrick", ls="none",
               label="Grid start (ID)"),
        Line2D([], [], color="0.4", label="Accepted position steps"),
        Line2D([], [], marker="D", color="black", ls="none", label="Satellite/alias switch"),
        Line2D([], [], marker="x", color="0.3", ls="none", label="Final position"),
        Line2D([], [], marker="*", mfc="gold", mec="black", ls="none", ms=12,
               label="GPS: evaluation only"),
    ]
    fig.legend(handles=handles, loc="outside lower center", ncol=5, fontsize=9)
    fig.suptitle(f"{case} — position descent with satellite reassociation after every step\n"
                 f"81 starts on a 2 km grid inside a 10 km radius; "
                 f"{len(records[0]['hypotheses'])} same-scan radio hypotheses\n"
                 f"25 × 25 km box centered at {CENTER[0]}, {CENTER[1]}; "
                 "colors group endpoints within 0.5 km", fontsize=12)
    path = OUTPUT / case / "joint_descent.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(13, 4), layout="constrained")
    for ax, arm in zip(axes, ARMS, strict=True):
        minimum = min(r["arms"][arm]["score"] for r in records)
        for r in records:
            v = r["arms"][arm]
            ax.plot([t["step"] for t in v["trace"]],
                    [t["score"] - minimum for t in v["trace"]], alpha=0.35, lw=0.8)
        ax.set(title=arm, xlabel="Accepted position step", ylabel="Loss above best endpoint",
               yscale="symlog")
        ax.grid(alpha=0.2)
    fig.suptitle(f"{case}: objective traces (frequency fit and priors; no GPS term)")
    fig.savefig(OUTPUT / case / "loss_traces.png", dpi=150)
    plt.close(fig)


def report():
    all_rows, summaries, bindings = [], [], {}
    totals, raw_hash = raw_denominators()
    if not set(CASES) <= totals.keys():
        raise ValueError("missing raw GLRT denominator evidence")
    diagnostics = {}
    text = ["# DSX01: position descent with stepwise satellite reassociation", "",
            "Each scan has 81 position starts on a 2 km grid inside a 10 km disk. "
            "The enclosing search box is 25 × 25 km, centered at "
            f"{CENTER[0]}, {CENTER[1]}. All original curved graph observations are retained.", "",
            "At the initial position and after every accepted damped Gauss–Newton step, "
            "the algorithm scores every available satellite/alias hypothesis with the "
            "same full normal-model objective, including integrated nuisance priors and "
            "noise/complexity terms. A lower-scoring assignment replaces the incumbent. "
            "Thus these paths can change satellite identities during descent; they are "
            "not descent under one fixed starting assignment.", "",
            "## Candidate scope and controls", "",
            "The candidate hypothesis bank is the union of 13 independently cold, same-scan "
            "radio discoveries across the region. Those discovery searches examined each "
            "scan's complete causal regional satellite catalogue. Only discrete fragment "
            "labels and alias integers are reused; all learned phase, receiver calibration, "
            "smooth coefficients and positions are discarded. All models are rebuilt with "
            "common zero phase references and absolute zero-mean nuisance priors. "
            "Duplicate label/alias combinations collapse without positional ranking.", "",
            "The common zero phase expansion makes branch comparisons reproducible, "
            "but is a different numerical linearization from the earlier per-discovery "
            "phase-reference experiments. This report therefore does not attribute changes "
            "in position error versus those experiments solely to reassociation. A fixed "
            "zero expansion is not a requirement that posterior phase be zero: phase and "
            "orbital corrections are still inferred under their absolute priors.", "",
            "This is a finite search over whole-assignment hypotheses. It does not "
            "rediscover all catalogue candidates at every step, recombine arbitrary "
            "fragments into new hypotheses, or guarantee a global optimum. The 81 position "
            "starts share this RF-derived hypothesis bank; they are not 81 independent "
            "cold discovery runs. The earlier independent-start results remain intact.", "",
            "Both c = 0 and fitted-c arms use the same observations, candidates, nuisance "
            "priors, initial grid and 64-step budget. Each arm selects its own best available "
            "assignment by its model objective. Causal TLE epoch and collection cutoffs "
            "are checked against the scan receipt. GPS is read only by this post-fit reporter; "
            "it never controls an update, stopping decision, candidate ranking, or restart.", "",
            "## Results", "",
            "The best endpoint below is selected by model loss, independently of GPS. "
            "Position error is an evaluation statistic. A lower frequency/prior loss does "
            "not establish better position accuracy. Association percentages use all "
            "original GLRT points as denominator; the objective uses original curved "
            "graph observations and final associations must also pass the existing gates.", "",
            "| Scan | Arm | Hypotheses | Starts <1 km | Median error (km) | "
            "Error range (km) | Best-loss error (km) | Best-loss associated points | "
            "% all GLRT | Switches | Capped |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for case in CASES:
        records, case_bindings = read_case(case)
        bindings.update(case_bindings)
        plot_case(case, records)
        scan, sigma = load_scan(case)
        nodes, _ = hypothesis_bank(scan, sigma)
        diagnostics[case] = {}
        for arm in ARMS:
            values = [r["arms"][arm] for r in records]
            errors = np.array([distance_km(geographic_position(v["parameters"]), REFERENCE)
                               for v in values])
            best = min(range(len(values)), key=lambda i: values[i]["score"])
            v = values[best]
            problem = factory(scan, nodes[v["final_mode"]], sigma, "normal", arm == "fitted_c")

            def objective(x, selected_problem=problem):
                return loss(selected_problem, x)

            gradient = finite_gradient(objective, v["parameters"])
            eigenvalues = np.linalg.eigvalsh(finite_hessian(objective, v["parameters"]))
            replay_error = abs(objective(v["parameters"]) - v["score"])
            if replay_error > 1e-6:
                raise ValueError("selected endpoint objective replay failed")
            diagnostics[case][arm] = dict(
                selected_by="lowest model loss, no GPS", start_id=best,
                replay_error=replay_error, gradient_loss_per_km=gradient.tolist(),
                hessian_eigenvalues=eigenvalues.tolist(),
                interpretation="conditional local curvature, not a global optimality certificate")
            switches = sum(len(a["switches"]) for a in values)
            capped = sum(a["stopped"] == "step_budget" for a in values)
            row = dict(case=case, arm=arm, hypotheses=len(records[0]["hypotheses"]),
                       starts=len(values), under_1km=int(sum(errors < 1)),
                       median_error_km=float(np.median(errors)),
                       min_error_km=float(errors.min()), max_error_km=float(errors.max()),
                       best_loss_start_id=best, best_loss=v["score"],
                       best_loss_error_km=float(errors[best]),
                       best_loss_residual_rms_hz=v["residual_rms_hz"],
                       best_loss_accepted_rms_hz=v["associated_native_rms_hz"],
                       best_loss_associated_points=v["associated_points"],
                       best_loss_associated_percent=100 * v["associated_points"] / totals[case],
                       switches=switches, capped=capped)
            summaries.append(row)
            text.append(f"| {case} | {arm} | {row['hypotheses']} | {row['under_1km']}/81 | "
                        f"{row['median_error_km']:.3f} | {errors.min():.3f}–{errors.max():.3f} | "
                        f"{errors[best]:.3f} | {v['associated_points']} | "
                        f"{row['best_loss_associated_percent']:.2f}% | {switches} | {capped} |")
            for i, value in enumerate(values):
                all_rows.append(dict(case=case, arm=arm, start_id=i,
                                     start_east_km=STARTS[i][0], start_north_km=STARTS[i][1],
                                     end_east_km=value["parameters"][0],
                                     end_north_km=value["parameters"][1],
                                     error_km=float(errors[i]), score=value["score"],
                                     final_mode=value["final_mode"], steps=value["steps"],
                                     switches=len(value["switches"]), stopped=value["stopped"],
                                     associated_points=value["associated_points"],
                                     associated_fragments=value["associated_fragments"],
                                     residual_rms_hz=value["residual_rms_hz"]))
    text += ["", "## c ablation: fit and position evaluated separately", "",
             "The loss includes frequency fit, nuisance integration and complexity terms. "
             "Compare its values within a scan; scans contain different observations. "
             "The RMS below covers all curved observations, including those rejected by "
             "the final gates. Each row uses the lowest-loss endpoint in that arm.", "",
             "| Scan | c0 loss | Fitted-c loss | Δ loss (fitted − c0) | "
             "c0 RMS (Hz) | Fitted-c RMS (Hz) | c0 error (km) | Fitted-c error (km) |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for case in CASES:
        a, b = [next(r for r in summaries if r["case"] == case and r["arm"] == arm)
                for arm in ARMS]
        text.append(f"| {case} | {a['best_loss']:.3f} | {b['best_loss']:.3f} | "
                    f"{b['best_loss'] - a['best_loss']:+.3f} | "
                    f"{a['best_loss_residual_rms_hz']:.2f} | "
                    f"{b['best_loss_residual_rms_hz']:.2f} | "
                    f"{a['best_loss_error_km']:.3f} | {b['best_loss_error_km']:.3f} |")
    text += ["", "## Reading the figures", "",
             "Open red circles are actual starting positions, numbered 00–80. Lines "
             "join actual accepted position iterates. Diamonds mark accepted changes in "
             "satellite labels or aliases; alternatives are rescored even where no diamond "
             "appears. Crosses mark final positions. Endpoint colors and G labels describe "
             "groups with at most 0.5 km pairwise separation, not proven distinct optima. "
             "The gold star is evaluation GPS only. A black square would mark a step-budget "
             "termination, which is not convergence. Loss curves show the same objective "
             "used to accept position and assignment updates.", ""]
    for case in CASES:
        text += [f"## {case}", "", f"![{case} reassociation paths]({case}/joint_descent.png)",
                 "", f"![{case} objective traces]({case}/loss_traces.png)", ""]
    text += ["## Artifacts and validation", "",
             "[All 810 endpoints and starting coordinates](endpoints.csv), "
             "[summary](summary.json), [protocol](protocol.json), "
             "[selected-endpoint gradients and curvature](endpoint_diagnostics.json), "
             "[validation and artifact hashes](validation.json). Each per-start JSON "
             "contains every accepted position, all candidate scores at that position, "
             "actual assignment changes, final labels, calibration state and association "
             "gate results. The reporter checks monotonic loss, lowest available branch "
             "selection, matched inputs, declared starts and trajectory endpoint identity.", ""]
    with (OUTPUT / "endpoints.csv").open("w") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(all_rows[0]))
        writer.writeheader()
        writer.writerows(all_rows)
    (OUTPUT / "summary.json").write_text(json.dumps(summaries, indent=2) + "\n")
    (OUTPUT / "endpoint_diagnostics.json").write_text(json.dumps(diagnostics, indent=2) + "\n")
    (OUTPUT / "validation.json").write_text(json.dumps(dict(
        status="pass", cases=5, paired_starts=405, trajectories=810,
        monotone_objectives=True, best_available_branch_at_every_step=True,
        matched_hypotheses_observations_priors_starts_budgets=True,
        GPS_in_inference=False, raw_GLRT_denominator_sha256=raw_hash,
        source_bindings={str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in (Path(__file__), Path(__file__).with_name(
                             "run_dsx01_joint_descent.py"))},
        bindings=bindings), indent=2) + "\n")
    (OUTPUT / "README.md").write_text("\n".join(text))
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    report()
