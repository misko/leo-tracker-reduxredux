"""Budget the frozen 4/16 DS30 prefixes and plot completed v3 successor pairs."""

import argparse
import csv
from hashlib import sha256
import json
from math import isclose
from pathlib import Path

from tools.pipeline_eval.qualification.score_paired_holdout import elapsed_ratios
from tools.pipeline_eval.scoring import distance_km

ROOT = Path(__file__).resolve().parent
PANEL_SHA = "147886973a6419baa925263c02e7b8d37e13737c94518bba69a023f47389d399"
CLOCK_SHA = "dc046009db376b6655886d73755d61a8bad5d14b2a7c99b1231ad2cfff74e2f9"
TIMES_SHA = "bb85ff40071ec84405135d723bc6b35ca17971f1e62d6759816be511569bcd11"
REFERENCE_SHA = "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5"
PAIRS = (
    ("successor-DS30-0374-pair.json", "b49af1ff154c7123574ffe6190e394c2d4ed7e29ea3da8d0da6dce479f3be82b",
     "Prefetch + orbit guard", "successor"),
    ("bounds-DS30-0008-pair.json", "0d2ec8bfd30a71142c9f88dcbcf2bcdef0d5f4188e8f6b42cb280bdaa06b6312",
     "Receiver + solver shortcuts", "bounds"),
)


def checked(path, expected):
    data = path.read_bytes()
    if sha256(data).hexdigest() != expected:
        raise ValueError(f"Input digest differs for {path}")
    return data


def stage_rows(cases, clocks):
    result = []
    for rank, case in enumerate(cases, 1):
        if case["rank"] != rank or case["case"] not in clocks:
            raise ValueError("Incomplete stage clocks or out-of-order assignment")
        row = clocks[case["case"]]
        stages = [float(row[key]) for key in ("launch_to_detections_s", "detections_to_terminal_s", "terminal_to_exit_s")]
        if min(stages) < 0 or not isclose(sum(stages), float(row["elapsed_s"]), abs_tol=1e-6):
            raise ValueError("Stage clocks disagree with total elapsed")
        result.append(stages)
    if len({case["raw_authority"] for case in cases}) != len(cases):
        raise ValueError("Repeated raw assignment")
    return result


def gates(stages, acquisition_fraction, solve_fraction):
    pairs = [(acq + solve + publish, acq * acquisition_fraction + solve * solve_fraction + publish)
             for acq, solve, publish in stages]
    return elapsed_ratios(pairs)


def acquisition_allowance(stages, solve_fraction):
    """Largest retained acquisition fraction satisfying both 0.5 elapsed gates."""
    if max(gates(stages, 0, solve_fraction)) > 0.5:
        return None
    low, high = 0., 1.
    for _ in range(48):
        middle = (low + high) / 2
        if max(gates(stages, middle, solve_fraction)) <= 0.5:
            low = middle
        else:
            high = middle
    return low


def observed():
    audit = json.loads(checked(ROOT.parents[1] / "2026_11_21_ds30_full/reference-audit.json", REFERENCE_SHA))
    references = {case["dataset_label"]: case["reference"] for case in audit["cases"]
                  if case["authority_eligible"] and case["sealed_metadata_digests_verified"]}
    result = []
    for filename, digest, label, contender in PAIRS:
        pair = json.loads(checked(ROOT / "measurements" / filename, digest))
        reference = references[pair["case"]]
        truth = (reference["latitude_deg"], reference["longitude_deg"])
        for name in ("baseline", contender):
            run = pair["runs"][name]
            result.append(dict(case=pair["case"], prototype=label, baseline=name == "baseline",
                               elapsed_s=run["elapsed_s"], cpu_s=run["cpu_s"], receipt_sha256=digest,
                               errors_km={arm: distance_km(truth, entry["latlon"]) for arm, entry in run["arms"].items()}))
    return result


def plot(rows, path):
    from matplotlib import pyplot as plt
    from matplotlib.lines import Line2D

    colors = ("#293b57", "#007c72")
    fig, axes = plt.subplots(1, 3, figsize=(11.1, 3.4), layout="constrained", width_ratios=[1.15, 1, 1])
    for index, row in enumerate(rows):
        y = index // 2 + (0.08 if row["baseline"] else -0.08)
        color = colors[int(not row["baseline"])]
        values = [row["elapsed_s"], row["errors_km"]["c0"], row["errors_km"]["fitted_c"]]
        for ax, value in zip(axes, values):
            ax.scatter(value, y, color=color, s=48)
        if row["baseline"]:
            axes[0].scatter(row["elapsed_s"] / 2, y, marker="|", s=130, color="#934900", linewidth=2)
    labels = [row["case"] + "\n" + row["prototype"] for row in rows if row["baseline"]]
    limits = [max(row["elapsed_s"] for row in rows)]
    limits.extend(max(row["errors_km"][arm] for row in rows) for arm in ("c0", "fitted_c"))
    for ax, label, limit in zip(axes, ("Elapsed (s)", "Fixed c = 0 error (km)", "Fitted c error (km)"), limits):
        ax.set_xlabel(label)
        ax.set_yticks(range(len(labels)), labels if ax is axes[0] else [""] * len(labels))
        ax.set_ylim(len(labels) - .55, -.55)
        ax.set_xlim(0, limit * 1.10)
        ax.grid(axis="x", alpha=.25)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
    fig.suptitle("Complete saved-recording runs on one Gauss core", fontsize=15)
    handles = [Line2D([], [], linestyle="", marker="o", color=color, label=label)
               for color, label in zip(colors, ("Installed ALGO08v3", "Prototype"))]
    handles.append(Line2D([], [], linestyle="", marker="|", color="#934900", label="Half-time target"))
    fig.legend(handles=handles, loc="outside lower center", ncols=3, frameon=False)
    fig.savefig(path, dpi=155)
    plt.close(fig)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("panel", type=Path)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    panel = json.loads(checked(args.panel, PANEL_SHA))
    source = checked(ROOT / "first-55/stage-clocks.csv", CLOCK_SHA)
    clocks = {row["recording"]: row for row in csv.DictReader(source.decode().splitlines())}
    timings = checked(ROOT / "first-55/recordings.csv", TIMES_SHA)
    fixed = {}
    for row in csv.DictReader(timings.decode().splitlines()):
        # The historic "candidate" column is the named v3 release.
        if row["build"] != "candidate" or row["decision"] != "solver_failed":
            continue
        if row["case"] in clocks:
            raise ValueError("Failure and split clocks both present")
        elapsed = row["elapsed_s"]
        # Carry its full elapsed cost unchanged in each hypothetical scenario.
        clocks[row["case"]] = dict(launch_to_detections_s=0, detections_to_terminal_s=0,
                                   terminal_to_exit_s=elapsed, elapsed_s=elapsed)
        fixed[row["case"]] = float(elapsed)
    result = dict(source_panel_sha256=PANEL_SHA, source_clocks_sha256=CLOCK_SHA, source_times_sha256=TIMES_SHA,
                  stages={}, observed=observed())
    for size in (4, 16):
        cases = panel["cases"][:size]
        stages = stage_rows(cases, clocks)
        result["stages"][size] = dict(
            cases=cases, v3_elapsed_s=sum(sum(row) for row in stages),
            unsplit_failures_charged_in_full={case["case"]: fixed[case["case"]] for case in cases if case["case"] in fixed},
            max_acquisition_fraction_by_solver_speed={speed: acquisition_allowance(stages, 1/speed)
                                                       for speed in (1, 1.5, 2, 3)},
            ratios_with_zero_solver_time=gates(stages, 1, 0),
        )
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "stages.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    plot(result["observed"], args.output / "physical-pairs.png")


if __name__ == "__main__":
    main()
