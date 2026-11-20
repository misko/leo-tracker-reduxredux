"""Separate nested-grid numerical fidelity from changed primary science and CPU."""

import argparse
import shutil
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

import matplotlib
import numpy as np

from ..__main__ import save_json
from . import nested_anchors_order, oracle_start, single_pass_results
from . import nested_anchors_trial as trial
from .capture_runtime import read
from .full_v5_check import _sha
from .prefix_figures import csv_file

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

GATE = "passed_fractional_margin_gate"


def summarize(work, names):
    plan = read(work / "input-lock.json")
    outcomes, times, coarse, known, lanes = [], [], [], [], []
    for name in names:
        receipt = trial.prior.read_gzip(work / f"{name}.json.gz")
        binding = plan["cases"][name]
        if (
            receipt["input_lock_sha256"] != _sha(work / "input-lock.json")
            or receipt["case"] != name
        ):
            raise ValueError("waveform receipt lost its frozen source")
        for index, (row, fixture) in enumerate(zip(receipt["rows"], binding["rows"], strict=True)):
            if (row["visit"], row["cohort"]) != (fixture["visit"], fixture["cohort"]):
                raise ValueError("waveform receipt changed its frozen visit roster")
            identity = dict(
                case=name,
                edge=binding["producer"]["edge"],
                visit=row["visit"],
                cohort=row["cohort"],
                iq_sha256=row["iq_sha256"],
            )
            all_ = row["evidence"]
            orig, full, shared = (all_[m] for m in trial.MODES)
            original_retries = {rx: g for rx, n, g in orig["attempts"] if n == 22}
            audit = dict(
                **identity,
                installed_checked=row["installed_checked"],
                nested_pair_public_equal=full["public"] == shared["public"],
                nested_pair_probes_equal=full["probes"] == shared["probes"],
                nested_pair_attempts_equal=full["attempts"] == shared["attempts"],
                nested_pair_gate_equal=[
                    p["receiver_id"] for p in full["probes"] if trial.prior.positive(p)
                ]
                == [p["receiver_id"] for p in shared["probes"] if trial.prior.positive(p)],
                original_and_nested_public_equal=orig["public"] == shared["public"],
            )
            for mode, view in all_.items():
                retries = {rx: g for rx, n, g in view["attempts"] if n == 22}
                outcomes.append(
                    dict(
                        **audit,
                        mode=mode,
                        public_equal_to_original=orig["public"] == view["public"],
                        attempts=len(view["attempts"]),
                        retry_count=len(retries),
                        rescue_count=sum(retries.values()),
                        original_retries_retained=len(original_retries.keys() & retries.keys()),
                        original_retry_rescues_retained=sum(
                            g and retries.get(rx, False) for rx, g in original_retries.items()
                        ),
                    )
                )
                for rx, (before, after, public) in enumerate(
                    zip(orig["probes"], view["probes"], view["public"]["receivers"], strict=True)
                ):
                    scores = single_pass_results.assess(
                        before["candidates"], after["candidates"], public["candidates"]
                    )
                    lanes.append(
                        dict(
                            **identity,
                            mode=mode,
                            rx=rx,
                            retried=rx in retries,
                            original_rescued=original_retries.get(rx, False),
                            rescued=retries.get(rx, False),
                            public_equal=orig["public"]["receivers"][rx] == public,
                            **scores,
                        )
                    )
                if row["cohort"] == trial.prior.KNOWN:
                    rx = fixture["receiver"]
                    target = fixture["target"]
                    known.append(
                        dict(
                            **identity,
                            mode=mode,
                            receiver=rx,
                            original_rescued=original_retries.get(rx, False),
                            target_recovered=any(
                                c[GATE] and oracle_start.target_matches(c, target, exact_cfo=True)
                                for c in view["probes"][rx]["candidates"]
                            ),
                        )
                    )
                times.append(
                    dict(
                        **identity,
                        mode=mode,
                        stage="cold",
                        repeat=-1,
                        order=-1,
                        nested_retry=len(full["attempts"]) == 3,
                        **row["cold"][mode],
                    )
                )
                for time in row["warm"].get(mode, []):
                    if time["order"] != (trial.MODES.index(mode) - (index + time["repeat"])) % len(
                        trial.MODES
                    ):
                        raise ValueError("warm detector timings were not interleaved")
                    times.append(
                        dict(
                            **identity,
                            mode=mode,
                            stage="warm",
                            nested_retry=len(full["attempts"]) == 3,
                            **time,
                        )
                    )
            coarse.extend(dict(**identity, **audit) for audit in row["grids"])
    return dict(outcomes=outcomes, times=times, coarse=coarse, known=known, lanes=lanes)


def relative(times):
    pairs = defaultdict(dict)
    for t in times:
        pairs[t["case"], t["visit"], t["repeat"]][t["mode"]] = t["cpu_ns"]
    return (
        dict(
            mean_cpu_ms={m: mean(t[m] for t in pairs.values()) * 1e-6 for m in trial.MODES},
            reuse_vs_recompute_cpu_pct=100
            * (
                sum(p["reuse"] for p in pairs.values())
                / sum(p["recompute"] for p in pairs.values())
                - 1
            ),
            paired_reuse_vs_recompute_cpu_pct=median(
                100 * (p["reuse"] / p["recompute"] - 1) for p in pairs.values()
            ),
            n=len(pairs),
        )
        if pairs
        else dict(n=0)
    )


def summary(table, names):
    held = [r for r in table["outcomes"] if r["cohort"] == trial.prior.HELD]
    lane = [r for r in table["lanes"] if r["cohort"] == trial.prior.HELD]
    results = {}
    for group in ("all", *names):
        modes = {}
        for mode in trial.MODES:
            rows = [r for r in held if r["mode"] == mode and group in ("all", r["case"])]
            lane_rows = [r for r in lane if r["mode"] == mode and group in ("all", r["case"])]
            known_rows = [
                r for r in table["known"] if r["mode"] == mode and group in ("all", r["case"])
            ]
            modes[mode] = dict(
                visits=len(rows),
                public_candidates=sum(r["public_candidates"] for r in lane_rows),
                positive=sum(r["positive"] for r in lane_rows),
                teacher_positive=sum(r["teacher_positive"] for r in lane_rows),
                lost_positive=sum(r["teacher_positive_now_negative"] for r in lane_rows),
                extra_positive=sum(r["teacher_negative_new_positive"] for r in lane_rows),
                teacher_winners=sum(r["held_teacher_winning_literal"] for r in lane_rows),
                positive_recovered=sum(r["held_teacher_any_literal"] for r in lane_rows),
                teacher_exact=sum(r["held_teacher_any_exact"] for r in lane_rows),
                retries=sum(r["retry_count"] for r in rows),
                rescue=sum(r["rescue_count"] for r in rows),
                rescue_old_lane=sum(r["original_retry_rescues_retained"] for r in rows),
                original_primary_or_retry_recovery=sum(
                    r["original_rescued"] and r["positive"] for r in lane_rows
                ),
                exact_original_visits=sum(r["public_equal_to_original"] for r in rows),
                exact_nested_visits=sum(
                    r["nested_pair_public_equal"]
                    and r["nested_pair_probes_equal"]
                    and r["nested_pair_attempts_equal"]
                    for r in rows
                ),
                forensic_recovered=sum(r["target_recovered"] for r in known_rows),
                forensic_total=len(known_rows),
            )
        times = [
            r
            for r in table["times"]
            if group in ("all", r["case"]) and r["cohort"] == trial.prior.HELD
        ]
        results[group] = dict(
            modes=modes,
            clocks={
                f"{stage}_{suffix}": relative(
                    [
                        r
                        for r in times
                        if r["stage"] == stage and (r["nested_retry"] or suffix == "all")
                    ]
                )
                for stage in ("cold", "warm")
                for suffix in ("all", "retry")
            },
        )
    return results


def chart(out, details):
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.2), layout="constrained")
    stats = details["all"]
    colors = ("#476080", "#ae7158", "#438581")
    modes = stats["modes"]
    panels = (
        (
            list(stats["clocks"]["warm_retry"]["mean_cpu_ms"][m] for m in trial.MODES),
            "CPU on paired retry visits (ms)",
        ),
        (
            [modes[m]["teacher_winners"] for m in trial.MODES],
            "Original winners retained on held visits",
        ),
        ([modes[m]["forensic_recovered"] for m in trial.MODES], "Forensic targets recovered"),
    )
    for ax, (values, label) in zip(axes, panels, strict=True):
        ax.bar(np.arange(3), values, color=colors)
        ax.set_xticks(np.arange(3), ["Original", "Nested\nfull 22", "Nested\nadd 10"])
        ax.set_title(label)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.2)
        ax.set_axisbelow(True)
        ax.set_ylim(0, max(values) * 1.16)
        for i, v in enumerate(values):
            ax.text(i, v + max(values) * 0.023, f"{v:.0f}", ha="center", fontsize=9)
    fig.suptitle("Reuse folded anchor sums in the original capture detector")
    for suffix in ("png", "pdf"):
        fig.savefig(out / f"stage.{suffix}", dpi=160)
    plt.close(fig)


def publish(work):
    table = summarize(work, trial.CASES)
    details = summary(table, trial.CASES)
    output = trial.REPORT
    for k, v in table.items():
        csv_file(output / f"{k}.csv", v)
    save_json(output / "summary.json", details)
    chart(output, details)
    names = [
        "input-lock.json",
        "capture_fft.c",
        "folded_bank.c",
        "nested_anchors.so",
        *(f"{name}.json.gz" for name in trial.CASES),
    ]
    order_counts = {}
    for name in trial.CASES:
        filename = f"{name}-order.json"
        evidence = read(work / filename)
        if (
            evidence["case"] != name
            or evidence["program_sha256"] != _sha(Path(nested_anchors_order.__file__))
            or evidence["waveform_sha256"] != _sha(work / f"{name}.json.gz")
        ):
            raise ValueError("coarse-order evidence differs from the complete held waveform")
        pairs = [pair for row in evidence["rows"] for pair in row["peaks"]]
        order_counts[name] = dict(
            grids=len(pairs), same_order=sum(p["reused"] == p["full"] for p in pairs)
        )
        names.append(filename)
    if sum(r["grids"] for r in order_counts.values()) != len(table["coarse"]):
        raise ValueError("ordered coarse audit did not cover every reused grid")
    save_json(
        output / "numerical-grid.json",
        dict(
            ordered_peak_keys=order_counts,
            cells=sum(r["cells"] for r in table["coarse"]),
            changed_cells=sum(r["differing"] for r in table["coarse"]),
            max_cell_difference=max(r["max_abs"] for r in table["coarse"]),
            integer_support_equal=all(r["support_equal"] for r in table["coarse"]),
        ),
    )
    for name in names:
        shutil.copyfile(work / name, output / name)
    save_json(
        output / "stage-figure.json",
        dict(
            version=1,
            id="nested-anchor-stage",
            title="Nested capture anchors",
            image="stage.png",
            pdf="stage.pdf",
            csv="times.csv",
            seal="qualification-lock.json",
            sample="32 outcome-blind visits with five interleaved repeats and 16 forensic visits",
            boundary="Resident dual IQ through complete capture detector and factor projection",
            note="Numerical reuse shares its primary with the full 22-anchor control.",
        ),
    )
    names.extend(
        [
            "summary.json",
            "numerical-grid.json",
            "stage.png",
            "stage.pdf",
            "stage-figure.json",
            "PROTOCOL.md",
            *(f"{key}.csv" for key in table),
        ]
    )
    save_json(
        output / "qualification-lock.json",
        dict(files={n: _sha(output / n) for n in names}, generator_sha256=_sha(Path(__file__))),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("--case", choices=trial.CASES)
    args = parser.parse_args()
    if args.case:
        table = summarize(args.work, (args.case,))
        print(summary(table, (args.case,))["all"])
    else:
        publish(args.work)
