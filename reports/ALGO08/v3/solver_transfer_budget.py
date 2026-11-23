"""Check dense solver scaling against completed weak and medium physical fixes."""

from bisect import bisect_left
import gzip
import json
from pathlib import Path
from statistics import median


DATA = Path(__file__).resolve().parent / "measurements"


def receipt(name):
    data = (DATA / name).read_bytes()
    return json.loads(gzip.decompress(data) if name.endswith(".gz") else data)


def measured_cases():
    weak = receipt("unified-short-layout.json.gz")["observations"]["weak"]["rows"]
    earlier = receipt("full-short-DS30-0016-raw.json.gz")
    medium = receipt("cumulative-medium-DS30-0057.json.gz")
    dense = receipt("cumulative-dense-graph-DS30-0008.json.gz")
    roster = {r["case"]: r for r in receipt("acquisition-throughput.json")["rows"]}
    for arm, row in weak.items():
        if (earlier["runs"][arm]["detection"]["native_sha256"] != row["science"]["native"]
                or earlier["request"]["inventory_sha256"] != row["science"]["input_manifest"]):
            raise ValueError("Weak clocks must refer to the same original recording and detector packets")
    if (medium["admission"]["input_manifest"] != roster[medium["case"]]["inventory_sha256"]
            or dense["inputs"]["inventory"] != roster[dense["case"]]["inventory_sha256"]
            or not earlier["runs"]["stock"]["publication"]["stock_control"]):
        raise ValueError("Stock timer or physical recording identity changed")
    m = medium["runs"]
    d = dense["runs"]
    return {
        "DS30-0016": [earlier["runs"]["stock"]["publication"]["solve"]["cpu_s"],
                      weak["candidate"]["science"]["bootstrap"]["numerical_publication"]["solve"]["cpu_s"]],
        medium["case"]: [m["stock"]["phases"]["clocks"]["solve"]["cpu_s"],
                         m["candidate"]["phases"]["clocks"]["solve"]["cpu_s"]],
        dense["case"]: [receipt("full-short-live-budget.json")["dense_solve_cpu_s"]["installed"],
                        d["installed"]["worker"]["solve"]["cpu_s"]],
    }, d["reused"]["worker"]["solve"]["cpu_s"]


def interpolate(stock_s, anchors):
    xs = [x for x, _ in anchors]
    if xs[0] != 0 or any(b <= a for a, b in zip(xs, xs[1:])) or stock_s < 0:
        raise ValueError("Expected ordered stock times from zero")
    i = max(1, min(bisect_left(xs, stock_s), len(xs) - 1))
    (x0, y0), (x1, y1) = anchors[i - 1:i + 1]
    return y0 + (stock_s - x0) * (y1 - y0) / (x1 - x0)


def ratios(rows, rate, startup, anchors):
    totals, candidates = [], []
    for row in rows:
        acquire, solve, tail = row["stages"]
        original = acquire + solve + tail
        totals.append(original)
        candidates.append(startup + row["compressed_MB"] / rate + interpolate(solve, anchors) + tail
                          if acquire else original)
    return median(c / b for c, b in zip(candidates, totals, strict=True)), sum(candidates) / sum(totals)


def required_rates(rows, startup, anchors):
    required = []
    for gate in (0, 1):
        if ratios(rows, float("inf"), startup, anchors)[gate] >= .5:
            required.append(None)
            continue
        lo, hi = 0., 1.
        while ratios(rows, hi, startup, anchors)[gate] > .5:
            hi *= 2
        for _ in range(55):
            mid = (lo + hi) / 2
            if ratios(rows, mid, startup, anchors)[gate] > .5:
                lo = mid
            else:
                hi = mid
        required.append(hi)
    return required


def study():
    from cumulative_graph_budget import budget
    from regional_dense_budget import select

    cases, lean_dense = measured_cases()
    weak, medium, dense = [cases[k] for k in ("DS30-0016", "DS30-0057", "DS30-0008")]
    dense_reused = [dense[0], lean_dense]
    scenarios = dict(dense_only=[(0, 0), dense], all_sizes=[(0, 0), weak, medium, dense],
                     dense_only_graph_reuse=[(0, 0), dense_reused],
                     all_sizes_dense_graph_reuse=[(0, 0), weak, medium, dense_reused])
    prior = budget()
    baseline = receipt("regional-dense-budget.json")
    roster = receipt("acquisition-throughput.json")["rows"]
    startup = baseline["common_charge_s"]
    models = {}
    for name, anchors in scenarios.items():
        panels = {}
        for size in ("4", "16"):
            rows = select(roster, baseline["panels"][size]["cases"])
            rates = required_rates(rows, startup, anchors)
            panels[size] = dict(required_MB_s=rates, at_weak_rate=ratios(rows, prior["warm_weak_MB_s"], startup, anchors),
                                at_dense_zero_wait_rate=ratios(rows, prior["dense_CPU_only_MB_s"], startup, anchors))
            if name == "dense_only_graph_reuse" and abs(max(rates) - prior["panels"][size]["effective_MB_s_required"]) > 1e-7:
                raise ValueError("The dense-only scenario must reproduce the previous published budget")
        models[name] = panels
    return dict(stock_candidate_solve_cpu_s=cases, dense_reused_cpu_s=lean_dense,
                warm_weak_MB_s=prior["warm_weak_MB_s"], dense_zero_wait_MB_s=prior["dense_CPU_only_MB_s"],
                common_charge_s=startup, panels_by_scenario=models)


def plot(result, output):
    from matplotlib.figure import Figure
    from matplotlib.ticker import PercentFormatter

    fig = Figure(figsize=(9.3, 3.8), layout="constrained")
    times, rates = fig.subplots(1, 2, width_ratios=[1.05, 1])
    cases = result["stock_candidate_solve_cpu_s"]
    fractions = [c / b for b, c in cases.values()]
    bars = times.barh(list(cases), fractions, color=["#24686c", "#308487", "#6a989b"])
    times.bar_label(bars, labels=[f"{v:.1%}" for v in fractions], padding=4)
    times.invert_yaxis()
    times.set(xlim=(0, 1), xlabel="Candidate CPU / ALGO08v3 CPU", title="Measured numerical solve")
    times.xaxis.set_major_formatter(PercentFormatter(1))
    for name, offset, label, color in (
        ("dense_only_graph_reuse", -.13, "Dense-only scaling", "#526687"),
        ("all_sizes_dense_graph_reuse", .13, "Three measured sizes", "#a65d25"),
    ):
        for i, size in enumerate(("4", "16")):
            rate = max(result["panels_by_scenario"][name][size]["required_MB_s"])
            rates.scatter(rate, i + offset, label=label if i == 0 else None, color=color, s=47)
            rates.annotate(f"{rate:.1f}", (rate, i + offset), xytext=(5, 0), textcoords="offset points",
                           va="center", color=color)
    rates.set(xlim=(250, 313), ylim=(1.55, -.5), yticks=[0, 1], yticklabels=["First 4", "First 16"],
              xlabel="Required uniform acquisition rate (MB/s)", title="Modeled rate for 2× end to end")
    rates.legend(frameon=False, loc="lower right", fontsize=8)
    for ax in (times, rates):
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.grid(axis="x", color="#e2e7e8")
        ax.set_axisbelow(True)
        ax.tick_params(axis="y", length=0)
    fig.savefig(output, dpi=160)


if __name__ == "__main__":
    import argparse

    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--plot", type=Path)
    args = cli.parse_args()
    result = study()
    if args.plot:
        plot(result, args.plot)
    print(json.dumps(result, indent=2, allow_nan=False))
