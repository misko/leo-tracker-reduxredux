"""Audit complete single-pass detector payloads, signal reach, and matched timing."""

import argparse
import csv
import shutil
from pathlib import Path
from statistics import mean, median, quantiles

import matplotlib
import numpy as np

from ..__main__ import save_json
from ..variants.single_pass import MODES
from . import factor_cross, oracle_start
from . import single_pass_trial as trial
from .capture_runtime import read
from .full_v5_check import _sha

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402

GATE = factor_cross.GATE


def winner(candidates):
    index = factor_cross.winner(candidates)
    return candidates[index] if index is not None else None


def exact_point(candidate, target):
    return all(value == candidate[key] for key, value in target.items() if key != "candidate_rank")


def assess(before, after, candidate_set):
    reference, current = winner(before), winner(after)
    passing = [c for c in after if c[GATE]]
    return dict(
        teacher_positive=reference is not None,
        positive=current is not None,
        teacher_negative_new_positive=reference is None and current is not None,
        teacher_positive_now_negative=reference is not None and current is None,
        held_teacher_any_literal=bool(
            reference
            and any(oracle_start.target_matches(c, reference, exact_cfo=True) for c in passing)
        ),
        held_teacher_any_folded=bool(
            reference and any(oracle_start.target_matches(c, reference) for c in passing)
        ),
        held_teacher_winning_literal=bool(
            reference
            and current
            and oracle_start.target_matches(current, reference, exact_cfo=True)
        ),
        held_teacher_winning_folded=bool(
            reference and current and oracle_start.target_matches(current, reference)
        ),
        held_teacher_any_exact=bool(reference and any(exact_point(c, reference) for c in passing)),
        public_candidates=len(candidate_set),
        public_integer_positive=sum(c["passed_margin_gate"] for c in candidate_set),
        fractional_candidates=len(after),
        fractional_positive=len(passing),
    )


def audit(work):
    source_path = work / "input-lock.json"
    lock = read(source_path)
    lanes, visits, clocks, known = [], [], [], []
    material = {}
    for ident, config in lock["cases"].items():
        document = trial.read_gzip(work / f"{ident}.json.gz")
        if document["case"] != ident or document["input_lock_sha256"] != _sha(source_path):
            raise ValueError("output worker receipt lost its frozen input")
        if [row["visit"] for row in config["rows"]] != [row["visit"] for row in document["rows"]]:
            raise ValueError("output worker receipt omitted or reordered an input")
        material[ident] = dict(cpu=document["cpu"], peak_rss_kib=document["peak_rss_kib"])
        archive_retry = trial.archive_counts()[1] if ident == "DS26-0237" else None
        for index, (fixture, row) in enumerate(zip(config["rows"], document["rows"], strict=True)):
            identity = dict(
                case=ident,
                edge=config["producer"]["edge"],
                visit=fixture["visit"],
                cohort=fixture["cohort"],
                iq_sha256=row["iq_sha256"],
            )
            baseline = row["evidence"]["conditional"]
            if baseline["probes"] != fixture["probes"] or fixture["cohort"] != row["cohort"]:
                raise ValueError("conditional output disagrees with the frozen cohort or factors")
            retry = {rx: passed for rx, anchors, passed in baseline["attempts"] if anchors == 22}
            if archive_retry is not None and len(retry) != archive_retry[fixture["visit"]]:
                raise ValueError("fresh retry tracker disagrees with the complete cache ledger")
            for mode in MODES:
                output = row["evidence"][mode]
                trial.validate_attempts(output["attempts"], mode, (0, 1), output["probes"])
                if {k: v for k, v in baseline["public"].items() if k != "receivers"} != {
                    k: v for k, v in output["public"].items() if k != "receivers"
                }:
                    raise ValueError("a counterfactual changed non-detector public fields")
                visits.append(
                    dict(
                        **identity,
                        mode=mode,
                        public_equal=baseline["public"] == output["public"],
                        projected_equal=baseline["probes"] == output["probes"],
                        conditional_retry=bool(retry),
                        conditional_retry_passed=any(retry.values()),
                    )
                )
                for rx, ((before, after), (before_public, after_public)) in enumerate(
                    zip(
                        zip(baseline["probes"], output["probes"], strict=True),
                        zip(
                            baseline["public"]["receivers"],
                            output["public"]["receivers"],
                            strict=True,
                        ),
                        strict=True,
                    )
                ):
                    if {k: v for k, v in before.items() if k != "candidates"} != {
                        k: v for k, v in after.items() if k != "candidates"
                    } or before["receiver_id"] != rx:
                        raise ValueError("a counterfactual changed the receiver or factor support")
                    selected = after["candidates"]
                    lanes.append(
                        dict(
                            **identity,
                            mode=mode,
                            rx=rx,
                            public_equal=before_public == after_public,
                            projected_equal=before == after,
                            conditional_retry=rx in retry,
                            conditional_retry_passed=retry.get(rx, False),
                            **assess(before["candidates"], selected, after_public["candidates"]),
                        )
                    )
                    if fixture["cohort"] == trial.KNOWN and rx == fixture["receiver"]:
                        target = fixture["target"]
                        if winner(before["candidates"]) != target:
                            raise ValueError(
                                "the forensic target is no longer the conditional winner"
                            )
                        known.append(
                            dict(
                                **identity,
                                mode=mode,
                                rx=rx,
                                target_on_retry=rx in retry,
                                target_literal=any(
                                    c[GATE]
                                    and oracle_start.target_matches(c, target, exact_cfo=True)
                                    for c in selected
                                ),
                                target_folded=any(
                                    c[GATE] and oracle_start.target_matches(c, target)
                                    for c in selected
                                ),
                                target_exact=any(
                                    c[GATE] and exact_point(c, target) for c in selected
                                ),
                                target_mode_winner=bool(
                                    (best := winner(selected))
                                    and oracle_start.target_matches(best, target, exact_cfo=True)
                                ),
                            )
                        )
                if fixture["cohort"] == trial.HELD:
                    times = row["clocks"][mode]
                    if [t["repetition"] for t in times] != list(range(lock["repeats"])):
                        raise ValueError("a held visit lost its interleaved timing repeat")
                    for timing in times:
                        turn = (index + timing["repetition"]) % len(MODES)
                        order = (MODES.index(mode) - turn) % len(MODES)
                        if timing["order"] != order:
                            raise ValueError("timed arm did not retain its interleaved order")
                        if ident == "DS26-0237" and timing["fft_inverses"] != (
                            timing["primary_grids"] * 104286 + timing["wide_grids"] * 191037
                        ):
                            raise ValueError(
                                "fresh dense-grid work disagrees with the archive formula"
                            )
                        clocks.append(
                            dict(
                                **identity,
                                mode=mode,
                                cpu=document["cpu"],
                                conditional_retry=bool(retry),
                                **timing,
                            )
                        )
    n_held = trial.COUNT * len(lock["cases"])
    if len(clocks) != n_held * len(MODES) * lock["repeats"] or len(known) != 16 * len(MODES):
        raise ValueError("the final report lost held timings or forensic rows")
    return lock, material, lanes, visits, clocks, known


def tally(rows, keys):
    return {key: sum(row[key] for row in rows) for key in keys}


def timing_summary(rows):
    clocks = {}
    baseline = {
        (r["case"], r["visit"], r["repetition"]): r for r in rows if r["mode"] == "conditional"
    }
    for mode in MODES:
        data = [row for row in rows if row["mode"] == mode]
        cpu = [row["cpu_ns"] / 1e6 for row in data]
        wall = [row["wall_ns"] / 1e6 for row in data]
        coarse = [row["coarse_cpu_ns"] / 1e6 for row in data]
        pairs = [baseline[r["case"], r["visit"], r["repetition"]]["cpu_ns"] for r in data]
        delta = [(r["cpu_ns"] - ref) / 1e6 for r, ref in zip(data, pairs, strict=True)]
        ratio = [(r["cpu_ns"] / ref - 1) * 100 for r, ref in zip(data, pairs, strict=True)]
        clocks[mode] = dict(
            calls=len(cpu),
            cpu_median_ms=median(cpu),
            cpu_mean_ms=mean(cpu),
            cpu_p95_ms=quantiles(cpu, n=20, method="inclusive")[-1],
            wall_median_ms=median(wall),
            wall_p95_ms=quantiles(wall, n=20, method="inclusive")[-1],
            wall_at_most_20_ms=sum(t <= 20 for t in wall),
            coarse_mean_ms=mean(coarse),
            paired_delta_ms=median(delta),
            paired_delta_min_ms=min(delta),
            paired_delta_max_ms=max(delta),
            paired_delta_pct=median(ratio),
            total_delta_pct=100 * (sum(r["cpu_ns"] for r in data) / sum(pairs) - 1),
            extra_numeric_grids=sum(
                r["primary_grids"]
                + r["wide_grids"]
                - 2
                - (mode == "conditional" and r["conditional_retry"])
                for r in data
            ),
        )
    return clocks


def groups(lanes, visits, clocks, known):
    held = [r for r in lanes if r["cohort"] == trial.HELD]
    held_visits = [r for r in visits if r["cohort"] == trial.HELD]
    lane_keys = (
        "teacher_positive",
        "positive",
        "public_equal",
        "projected_equal",
        "held_teacher_any_literal",
        "held_teacher_any_folded",
        "held_teacher_winning_literal",
        "held_teacher_winning_folded",
        "held_teacher_any_exact",
        "teacher_negative_new_positive",
        "teacher_positive_now_negative",
        "public_candidates",
        "public_integer_positive",
        "fractional_candidates",
        "fractional_positive",
        "conditional_retry",
        "conditional_retry_passed",
    )
    visit_keys = (
        "public_equal",
        "projected_equal",
        "conditional_retry",
        "conditional_retry_passed",
    )
    forensic_keys = (
        "target_on_retry",
        "target_literal",
        "target_folded",
        "target_exact",
        "target_mode_winner",
    )
    summaries = {}
    for group in ("all", *trial.CASE_IDS, "upper", "lower"):

        def include(row, group=group):
            return group in ("all", row["case"], row["edge"])

        outcomes = {}
        for mode in MODES:
            lane_rows = [r for r in held if r["mode"] == mode and include(r)]
            v = [r for r in held_visits if r["mode"] == mode and include(r)]
            k = [r for r in known if r["mode"] == mode and include(r)]
            outcomes[mode] = dict(
                lanes=dict(n=len(lane_rows), **tally(lane_rows, lane_keys)),
                by_receiver={
                    rx: dict(
                        n=len(q := [r for r in lane_rows if r["rx"] == rx]), **tally(q, lane_keys)
                    )
                    for rx in (0, 1)
                },
                visits=dict(n=len(v), **tally(v, visit_keys)),
                forensic=dict(n=len(k), **tally(k, forensic_keys)),
            )
        summaries[group] = dict(
            outcomes=outcomes, timing=timing_summary([r for r in clocks if include(r)])
        )
    for retried in (True, False):
        summaries[f"conditional_retry_{retried}"] = timing_summary(
            [r for r in clocks if r["conditional_retry"] == retried]
        )
    return summaries


def chart(output, summary):
    fig, (cost, evidence, misses) = plt.subplots(1, 3, figsize=(13.4, 4.8), layout="constrained")
    fig.suptitle("Single-pass capture GLRT on authenticated dual receiver IQ", fontsize=15)
    colors = ("#304569", "#269185", "#c75c37")
    x = np.arange(len(MODES))
    overall = summary["all"]
    coarse = np.array([overall["timing"][mode]["coarse_mean_ms"] for mode in MODES])
    cpu = np.array([overall["timing"][mode]["cpu_mean_ms"] for mode in MODES])
    cost.bar(x, coarse, color="#7692bd", label="Prepared coarse grid")
    cost.bar(x, cpu - coarse, bottom=coarse, color="#304569", label="Other detector work")
    for i, value in enumerate(cpu):
        cost.text(i, value + 5, f"{value:.0f}", ha="center", fontsize=9)
    cost.set_ylim(0, max(cpu) * 1.2)
    cost.set_ylabel("Mean CPU per dual visit (ms)")
    cost.set_title("64 outcome-blind visits")
    cost.legend(frameon=False, loc="upper left", fontsize=8)
    for ax in (cost, evidence, misses):
        ax.set_xticks(x, ["Conditional\n12 / 22", "One\n12", "One\n22"])
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_axisbelow(True)
        ax.grid(axis="y", alpha=0.24)
    observed = [overall["outcomes"][mode]["lanes"] for mode in MODES]
    denominator = observed[0]["teacher_positive"]
    winners = np.array([r["held_teacher_winning_literal"] for r in observed])
    for i, w in enumerate(winners):
        evidence.bar(i, w, color=colors[i])
        evidence.text(i, w + 0.5, f"{w}/{denominator}", ha="center", fontsize=9)
    evidence.set_ylim(0, denominator * 1.16)
    evidence.set_title("Archived winners on held visits")
    evidence.set_ylabel("Same winner within 2 samples and 1 kHz")
    observed = [overall["outcomes"][mode]["forensic"] for mode in MODES]
    for i, row in enumerate(observed):
        misses.bar(i, row["target_literal"], color=colors[i])
        misses.text(
            i, row["target_literal"] + 0.25, f"{row['target_literal']}/{row['n']}", ha="center"
        )
    misses.set_ylim(0, observed[0]["n"] * 1.16)
    misses.set_ylabel("Gated original targets recovered")
    misses.set_title("16 predeclared stock wide misses")
    misses.yaxis.set_major_locator(MaxNLocator(integer=True))
    for suffix in ("pdf", "png"):
        fig.savefig(output / f"stage.{suffix}", dpi=175)
    plt.close(fig)


def save_csv(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def publish(work, output):
    lock, workers, lanes, visits, clocks, known = audit(work)
    summary = groups(lanes, visits, clocks, known)
    output.mkdir(parents=True, exist_ok=True)
    for name, rows in (
        ("lanes", lanes),
        ("visits", visits),
        ("timing", clocks),
        ("forensic", known),
    ):
        save_csv(output / f"{name}.csv", rows)
    archive = {ident: case["archive_structure"] for ident, case in lock["cases"].items()}
    save_json(
        output / "summary.json", dict(groups=summary, archive_census=archive, workers=workers)
    )
    save_json(
        output / "stage-figure.json",
        dict(
            id="capture-glrt-single-pass",
            title="One anchor set for the complete capture GLRT",
            image="stage.png",
            pdf="stage.pdf",
            csv="timing.csv",
            boundary="Resident dual CI16 through complete detector output and projection",
            sample="64 outcome-blind visits with five paired repeats and 16 forensic misses",
            note="Target retrieval counts use the archived original detector as teacher.",
            seal="qualification-lock.json",
            version=1,
        ),
    )
    chart(output, summary)
    names = ["input-lock.json", *(f"{name}.json.gz" for name in trial.CASE_IDS)]
    for name in names:
        shutil.copyfile(work / name, output / name)
    names += [
        "lanes.csv",
        "visits.csv",
        "timing.csv",
        "forensic.csv",
        "summary.json",
        "stage-figure.json",
        "stage.pdf",
        "stage.png",
    ]
    save_json(
        output / "qualification-lock.json",
        dict(
            files={name: _sha(output / name) for name in names},
            generator_sha256=_sha(Path(__file__)),
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("--out", type=Path, default=trial.REPORT)
    args = parser.parse_args()
    publish(args.work, args.out)
