"""Bracket the five failed raw workers' launch clocks using their serial pair."""

import argparse
import gzip
import json
from pathlib import Path

from reports.ALGO08.v3.release_intake_rate import required_rate
from reports.ALGO08.v3.release_stage_budget import checked, publication_clock
from reports.ALGO08.v3.saved_solver_intake_budget import INTAKE_PIN, MEASUREMENTS


STAGES = "bf5e6488d1b59ba49ca091b6707b6d3fed099664f528bc7540bcbbed7afbc4be"
RECOVERY = "0dfd4cdbb1e9e9cda93280ea11fc1b5cecc758402c3beb4ad7985c1d365295e0"


def launch_interval(order, config_ns, pair_ns, baseline_start_ns, baseline_s, candidate_s):
    candidate_ns = round(candidate_s * 1e9)
    if order == ["candidate", "baseline"]:
        lower, upper = config_ns, baseline_start_ns - candidate_ns
    elif order == ["baseline", "candidate"]:
        lower = baseline_start_ns + round(baseline_s * 1e9)
        upper = pair_ns - candidate_ns
    else:
        raise ValueError("Expected both serial release workers")
    if upper < lower:
        raise ValueError("Serial pair timestamps disagree with measured process durations")
    return lower, upper


def observe(folder, stages):
    failed = {}
    margins = []
    for case in stages["rows"]:
        root = folder / case["case"]
        pair_path = root / "pair.json"
        pair = json.loads(checked(pair_path, case["pair_sha256"]))
        stock, trial = (pair["runs"][side] for side in ("baseline", "candidate"))
        work = "fast-scan-automatic-work"
        baseline_terminal = publication_clock(root / "baseline" / work, "terminal.json")
        baseline_start = baseline_terminal - round(stock["terminal_file_s"] * 1e9)
        config_ns = (root / "candidate-config.json").stat().st_mtime_ns
        pair_ns = pair_path.stat().st_mtime_ns
        lo, hi = launch_interval(pair["order"], config_ns, pair_ns, baseline_start,
                                 stock["elapsed_s"], trial["elapsed_s"])
        detect = publication_clock(root / "candidate" / work, "detections.json")
        if case["pre_s"] is not None:
            start = case["terminal_mtime_ns"] - round(trial["terminal_file_s"] * 1e9)
            if not lo <= start <= hi or case["detector_mtime_ns"] != detect:
                raise ValueError(f"Independent successful-job clock outside bounds for {root.name}")
            margins.append((start-lo, hi-start))
            continue
        pre = [(detect-hi)/1e9, (detect-lo)/1e9]
        if trial["failure_observation"]["exit_code"] != 1 or not 0 <= pre[0] <= pre[1] <= trial["elapsed_s"]:
            raise ValueError(f"Invalid failed worker evidence for {root.name}")
        failed[root.name] = dict(pair_sha256=case["pair_sha256"], order=pair["order"],
                                 config_ns=config_ns, pair_ns=pair_ns, baseline_start_ns=baseline_start,
                                 launch_ns=[lo, hi], detection_ns=detect, pre_s=pre,
                                 post_s=[trial["elapsed_s"]-pre[1], trial["elapsed_s"]-pre[0]])
    if len(failed) != 5 or len(margins) != 95:
        raise ValueError("The 100-worker release must be complete")
    return failed, dict(checked=len(margins), minimum_lower_margin_ns=min(x for x, _ in margins),
                        minimum_upper_margin_ns=min(y for _, y in margins))


def estimate(intake, failures, repair):
    outputs = {}
    for scenario in ("same_exits", "one_recovered_four_fixed"):
        bounds = []
        for i, size in enumerate(("byte_low", "byte_high")):
            rows = []
            for row in intake["rows"]:
                name = row["case"]
                cost = row["post_s"] / 1.5 if row["post_s"] is not None else None
                if name in failures:
                    if scenario == "same_exits":
                        cost = failures[name]["post_s"][i] / 1.5
                    elif name == repair["case"]:
                        cost = repair["clock"]["elapsed_s"] + repair["admission"]["setup_clock"]["elapsed_s"]
                rows.append(dict(row, post_s=cost))
            bounds.append(required_rate(rows, size, 1., 0.))
        outputs[scenario] = bounds
    return outputs


def run(folder):
    intake = json.loads(checked(MEASUREMENTS/"release-intake-rate.json", INTAKE_PIN))
    stages = json.loads(checked(MEASUREMENTS/"release-stage-budget.json", STAGES))
    repair = json.loads(gzip.decompress(checked(MEASUREMENTS/"solver-exception-0022.json.gz", RECOVERY)))
    failed, controls = observe(folder, stages)
    if not repair["qualified_recovery"] or repair["admission"]["pair_sha256"] != failed[repair["case"]]["pair_sha256"]:
        raise ValueError("Saved recovery must use the original failed pair")
    return dict(failures=failed, controls=controls, targets=estimate(intake, failed, repair))


def render(result, output):
    import matplotlib.pyplot as plt

    records = sorted(result["failures"].items())
    fig, (raw, saved) = plt.subplots(1, 2, figsize=(10.3, 4.5), sharey=True,
                                     gridspec_kw={"width_ratios": [2.15, 1]})
    fig.subplots_adjust(left=.13, right=.98, bottom=.23, top=.72, wspace=.12)
    fig.suptitle("Where the five failed DS30 runs spent their time", x=.025, ha="left",
                 fontsize=16, fontweight="bold")
    raw.set_title("Original ALGO08v3 through failed exit", loc="left", fontsize=11)
    saved.set_title("Saved solver through publication", loc="left", fontsize=11)
    for i, (case, bounds) in enumerate(records):
        pre = sum(bounds["pre_s"]) / 2
        post = sum(bounds["post_s"]) / 2
        raw.barh(i, pre, height=.6, color="#405873", label="To detections" if i == 0 else None)
        raw.barh(i, post, left=pre, height=.6, color="#ccb48b", label="To failed exit" if i == 0 else None)
        raw.text(pre-1.5, i, f"{pre:.1f}", color="white", ha="right", va="center")
        raw.text(pre+post/2, i, f"{post:.1f}", color="#30291f", ha="center", va="center", fontsize=9)
    raw.set_yticks(range(len(records)), [key for key, _ in records])
    raw.legend(ncol=2, loc="lower left", bbox_to_anchor=(0, 1.13), frameon=False, borderaxespad=0)
    raw.invert_yaxis()
    products = (
        ("0022", "661311100d12da42dc72d05db76e3ba4f95fecb9a5f45857415c2da65363dc9a", "candidate_clock"),
        ("0129", "8ac6521afabd3cdccd93acb1ee5bfc835efe69abfe9b7a28fd2b247139b7d093", "clock"),
    )
    names = [key for key, _ in records]
    for key, pin, clock in products:
        path = MEASUREMENTS / f"live-orbit-support-{key}.json.gz"
        replay = json.loads(gzip.decompress(checked(path, pin)))
        if replay["case"] != "DS30-"+key or replay[clock]["exit_code"] != 0:
            raise ValueError("Require a successful saved publication for the same failed case")
        i = names.index(replay["case"])
        elapsed = replay[clock]["elapsed_s"]
        saved.barh(i, elapsed, height=.6, color="#147b70")
        saved.text(elapsed-1, i, f"{elapsed:.1f}", va="center", ha="right", color="white")
    for ax, limit in ((raw, 115), (saved, 45)):
        ax.set_xlim(0, limit)
        ax.set_xlabel("Elapsed seconds")
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
    fig.text(.025, .055, "Left bars use the midpoint of timing bounds narrower than 0.19 s. "
             "Right bars start at saved detections for the two replays.", fontsize=9)
    fig.savefig(output, dpi=145, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("panel", type=Path)
    parser.add_argument("--plot", type=Path)
    args = parser.parse_args()
    result = run(args.panel)
    if args.plot:
        render(result, args.plot)
    print(json.dumps(result, indent=2, allow_nan=False))
