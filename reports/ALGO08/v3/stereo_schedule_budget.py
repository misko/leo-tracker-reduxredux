"""Price a single dense half-time target and plot measured saved position errors."""

import gzip
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
DATA = HERE / "measurements"


def dense_budget(prior, plan, score):
    phases = prior["cpu_s"]
    if abs(sum(phases.values()) - prior["whole_cpu_s"]) > 1e-6:
        raise ValueError("Original whole-process CPU partition is incomplete")
    old_acquisition = phases["receiver"] + phases["other_acquisition"]
    budget = plan["budget"]
    if abs(old_acquisition - budget["original_acquisition_cpu_s"]) > 1e-6:
        raise ValueError("The proposed saving uses a different acquisition control")
    target = prior["elapsed_s"] - prior["controls"]["qualification"]["elapsed_above_half_s"]
    acquisition = old_acquisition - budget["gross_credit_cpu_s"]
    solve = score["reported_clock"]["candidate_solve_cpu_s"]
    planning = plan["planning_including_source_cpu_s"]
    other = phases["remaining"]
    allowance = target - solve - planning - other
    if allowance <= 0 or acquisition <= 0:
        raise ValueError("The modeled rates require positive acquisition time")
    return dict(warm_named_half_s=target, estimated_acquisition_cpu_s=acquisition, measured_numerical_cpu_s=solve,
                original_remaining_cpu_s=other, charged_saved_planner_cpu_s=planning,
                zero_wait_model_s=acquisition+solve+planning+other, allowable_acquisition_wall_s=allowance,
                allowable_extra_s=allowance-acquisition, required_compressed_MB_s=prior["dense_compressed_MB"]/allowance,
                earlier_acquisition_exposed_s=prior["acquire_wall_s"]-prior["acquire_cpu_s"],
                saved_process_exit_code=score["reported_clock"]["candidate_process_exit"])


def data():
    with gzip.open(DATA / "whole-stereo-blocks.json.gz", "rt") as stream:
        cases = json.load(stream)["cases"]
    prior = json.loads((DATA / "dense-measured-budget.json").read_bytes())
    dense = cases["DS30-0008"]
    return cases, dense_budget(prior, dense["plan"], dense["score"])


def draw(cases, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    fig, axes = plt.subplots(1, 2, figsize=(10.4, 3.7), sharex=True, sharey=True)
    fig.subplots_adjust(left=.145, right=.98, top=.68, bottom=.25, wspace=.16)
    fig.suptitle("Position error after skipping short stereo visits", x=.035, y=.97,
                 ha="left", fontsize=18, weight="bold")
    variants = [("named_v3", "ALGO08v3", "#354562", "o"), ("full_mixed", "All mixed-aperture visits", "#b36c25", "s"),
                ("masked", "Two of three short visits", "#007c75", "D")]
    handles = [Line2D([], [], marker=style, color=color, linestyle="none", label=label)
               for _, label, color, style in variants]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(.025,.855), ncol=3, frameon=False)
    for ax, (case, title) in zip(axes, [("DS30-0016", "Weak physical recording"), ("DS30-0008", "Dense physical recording")]):
        values = cases[case]["score"]["value"]
        for i, arm in enumerate(("c0","fitted_c")):
            for offset, (method, _, color, marker) in zip((-.09, 0, .09), variants):
                ax.scatter(values[method][arm]["error_km"], i+offset, marker=marker, color=color, s=57, zorder=2)
        ax.set(yticks=(0,1), yticklabels=("Fixed zero","Fitted"), ylim=(1.38,-.38), xlim=(.65,1.93),
               xlabel="Horizontal error (km)")
        ax.set_title(f"{case}  ·  {title}", fontsize=11, loc="left", weight="bold")
        ax.grid(axis="x", color="#dfe4e9")
        ax.spines[["top","left","right"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
    fig.text(.035,.045,"Both methods using mixed apertures were scored from saved detector data. Each point is one returned position.",fontsize=9)
    fig.savefig(path, dpi=160, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    cases, budget = data()
    print(json.dumps(budget, indent=2))
    draw(cases, HERE / "development/stereo-schedule-errors.png")
