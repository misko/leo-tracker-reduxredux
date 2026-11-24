"""Reconstruct the installed-v3 process split from archived publication metadata."""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
from statistics import median


DECISION = "26ac73f584b58150b1205ccfb848b0317af322d5389c0b4e8eaf18c0a178f1f1"
FIRST = "dc046009db376b6655886d73755d61a8bad5d14b2a7c99b1231ad2cfff74e2f9"


def checked(path, expected):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f"Unexpected historical evidence in {path}")
    return data


def publication_clock(folder, name):
    files = list(folder.glob(f"*/{name}"))
    if len(files) != 1 or files[0].is_symlink() or not files[0].is_file():
        raise ValueError(f"Expected one original {name} in {folder}")
    return files[0].stat().st_mtime_ns


def reconstruct(folder, decision, earlier):
    rows = []
    compared = set()
    failures = set(decision["result"]["solver_failures"]["candidate"])
    for case, pin in decision["pair_sha256"].items():
        if not case.startswith("DS30-") or not case[5:].isdecimal():
            raise ValueError("Expected DS30 case in frozen panel")
        root = folder / case
        pair = json.loads(checked(root / "pair.json", pin))
        if pair["candidate_specification_digest"] != decision["candidate"]:
            raise ValueError(f"Different candidate specification in {case}")
        run = pair["runs"]["candidate"]
        total = run["elapsed_s"]
        if not 0 < run["cpu_s"] <= total:
            raise ValueError(f"Cannot split the single-core process clock in {case}")
        cache = pair["cache_observation"]["arms"]["candidate"]
        if (cache["unavailable"] or cache["observed_members"] != cache["members"]
                or not 0 <= cache["cached_pages"] <= cache["observed_file_pages"]
                or cache["observed_file_pages"] == 0):
            raise ValueError(f"Incomplete input residency observation in {case}")
        row = dict(case=case, pair_sha256=pin, elapsed_s=total, cpu_s=run["cpu_s"],
                   resident_fraction=cache["cached_pages"]/cache["observed_file_pages"])
        if case in failures:
            if run.get("failure_observation", {}).get("exit_code") != 1 or "terminal_file_s" in run:
                raise ValueError(f"Unexpected failure boundary in {case}")
            row.update(pre_s=None, post_s=None)
        else:
            work = root / "candidate/fast-scan-automatic-work"
            terminal = publication_clock(work, "terminal.json")
            detection = publication_clock(work, "detections.json")
            interval = (terminal-detection)/1e9
            pre = run["terminal_file_s"] - interval
            if not 0 <= pre <= run["terminal_file_s"] <= total:
                raise ValueError(f"Unordered publication milestones in {case}")
            if case in earlier:
                old = earlier[case]
                for key, value in (("launch_to_detections_s", pre), ("elapsed_s", total),
                                   ("detections_to_terminal_s", interval)):
                    if abs(float(old[key])-value) > 1e-6:
                        raise ValueError(f"Historical timing disagrees in {case}: {key}")
                compared.add(case)
            row.update(pre_s=pre, post_s=total-pre, detector_mtime_ns=detection, terminal_mtime_ns=terminal)
        rows.append(row)
    if compared != set(earlier) or len(rows) != 100 or len(failures) != 5:
        raise ValueError("Expected the frozen 100 cases and full earlier timing overlap")
    return rows


def gates(rows, pre_scale, post_scale, *, optimistic):
    # Failed processes have no terminal timestamp. Bound their contribution without dropping their elapsed time.
    missing_scale = (min if optimistic else max)(pre_scale, post_scale)
    costs = [r["elapsed_s"] * missing_scale if r["pre_s"] is None
             else r["pre_s"] * pre_scale + r["post_s"] * post_scale for r in rows]
    return dict(median_ratio=median(c/r["elapsed_s"] for c, r in zip(costs, rows, strict=True)),
                sum_ratio=sum(costs)/sum(r["elapsed_s"] for r in rows))


def required_pre_speedup(rows, post_scale, optimistic):
    def passes(scale):
        return max(gates(rows, scale, post_scale, optimistic=optimistic).values()) <= .5

    if not passes(0):
        return None
    if passes(1):
        return 1.0
    low, high = 0.0, 1.0
    for _ in range(54):
        middle = (low+high)/2
        if passes(middle):
            low = middle
        else:
            high = middle
    return 1/low if low else None


def summarize(rows):
    known = [r for r in rows if r["pre_s"] is not None]
    groups = {}
    for label, items in (
        ("all_partitioned", known),
        ("at_most_one_percent_resident", [r for r in known if r["resident_fraction"] <= .01]),
        ("between_one_and_99_percent", [r for r in known if .01 < r["resident_fraction"] < .99]),
        ("at_least_99_percent_resident", [r for r in known if r["resident_fraction"] >= .99]),
    ):
        if items:
            pre = sum(r["pre_s"] for r in items)
            total = sum(r["elapsed_s"] for r in items)
            groups[label] = dict(n=len(items), pre_s=pre, post_s=total-pre, summed_pre_fraction=pre/total,
                                 median_pre_fraction=median(r["pre_s"]/r["elapsed_s"] for r in items))
    results = {}
    for optimistic in (True, False):
        key = "optimistic_unpartitioned" if optimistic else "pessimistic_unpartitioned"
        results[key] = dict(
            free_post=gates(rows, 1, 0, optimistic=optimistic),
            free_pre=gates(rows, 0, 1, optimistic=optimistic),
            required_pre_speedup={str(speed): required_pre_speedup(rows, 1/speed, optimistic)
                                  for speed in (1, 1.25, 1.5, 1.6, 2)},
        )
    cpu_rows = [dict(elapsed_s=r["elapsed_s"], pre_s=r["cpu_s"], post_s=r["elapsed_s"]-r["cpu_s"])
                for r in rows]
    return dict(panel_elapsed_s=sum(r["elapsed_s"] for r in rows),
                unpartitioned_elapsed_s=sum(r["elapsed_s"] for r in rows if r["pre_s"] is None),
                panel_cpu_s=sum(r["cpu_s"] for r in rows),
                cpu_half_with_other_time_fixed=gates(cpu_rows, .5, 1, optimistic=False),
                required_cpu_speedup_with_other_time_fixed=required_pre_speedup(cpu_rows, 1, False),
                groups=groups, gates=results)


def plot(rows, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (cost, target) = plt.subplots(1, 2, figsize=(10, 4.7))
    fig.subplots_adjust(left=.08, right=.97, top=.73, bottom=.26, wspace=.34)
    fig.suptitle("Where a 2× end-to-end speedup has to come from", x=.04, ha="left",
                 fontsize=17, weight="bold")
    fig.text(.041, .83, "Original ALGO08v3  ·  frozen DS30 panel  ·  historical elapsed time",
             fontsize=10, color="#435462")
    known = sorted(r["pre_s"]/r["elapsed_s"] for r in rows if r["pre_s"] is not None)
    cost.plot(range(1, len(known)+1), [100*v for v in known], color="#16746c", lw=2)
    cost.axhline(50, color="#9b6346", linestyle="--", lw=1)
    cost.set(xlabel="Recordings ordered by time share", ylabel="Time before detections (%)",
             title="95 recordings with both timestamps", ylim=(0, 100))
    speeds = [1+i/40 for i in range(61)]
    low = [required_pre_speedup(rows, 1/s, True) for s in speeds]
    high = [required_pre_speedup(rows, 1/s, False) for s in speeds]
    target.fill_between(speeds, low, high, color="#b4dad1")
    target.plot(speeds, low, color="#16746c")
    target.plot(speeds, high, color="#16746c")
    target.scatter([2], [2], color="#283d56", zorder=4)
    target.set(xlabel="Speedup after detections (×)", ylabel="Required speedup before detections (×)",
               title="Both timing gates across all 100")
    for ax in (cost, target):
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", color="#dfe6e7", lw=.7)
        ax.set_axisbelow(True)
    fig.text(.04, .075, "Band shows the full range possible for five failed runs with unknown stage split.",
             fontsize=9)
    fig.text(.04, .03, "The right panel gives the required speedups if each historical interval scales uniformly.",
             fontsize=9)
    fig.savefig(output, dpi=145, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("panel", "decision", "earlier", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--plot", type=Path)
    args = parser.parse_args()
    earlier = csv.DictReader(io.StringIO(checked(args.earlier, FIRST).decode()))
    rows = reconstruct(args.panel, json.loads(checked(args.decision, DECISION)),
                       {r["recording"]: r for r in earlier})
    result = dict(decision_sha256=DECISION, earlier_sha256=FIRST, rows=rows, summary=summarize(rows))
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    if args.plot:
        plot(rows, args.plot)
