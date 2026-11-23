"""Apply both enrolled elapsed gates to the measured dense graph composition."""

import gzip
import json

from regional_dense_budget import DATA, gates, minimum_rate, select


def budget():
    def read(name):
        data = (DATA / name).read_bytes()
        return json.loads(gzip.decompress(data) if name.endswith(".gz") else data)

    dense = read("cumulative-dense-graph-DS30-0008.json.gz")
    acquisition = read("dense-measured-budget.json")
    original = read("acquisition-throughput.json")["rows"]
    enrolled = read("regional-dense-budget.json")
    weak = read("unified-short-layout.json.gz")["observations"]["weak"]["rows"]["candidate"]
    members = read("unified-raw-member-sizes.json")["weak"]
    if weak["science"]["native"] != members["native_sha256"]:
        raise ValueError("Warm acquisition sizes and publication must refer to the same packet")
    weak_bytes = sum(c["compressed"] for c in members["members"])
    weak_s = weak["science"]["bootstrap"]["phases"]["authenticated_raw_acquisition"]["elapsed_s"]
    weak_rate = weak_bytes / 1e6 / weak_s
    dense_size = acquisition["dense_compressed_MB"]
    dense_cpu = acquisition["acquire_cpu_s"]
    solve = dense["runs"]["reused"]["worker"]["solve"]["cpu_s"]
    fraction = solve / enrolled["historical_installed_solve_cpu_s"]
    startup = enrolled["common_charge_s"]
    panels = {}
    for size in ("4", "16"):
        rows = select(original, enrolled["panels"][size]["cases"])
        required = max(minimum_rate(rows, fraction, i, startup_s=startup) for i in (0, 1))
        allowed = dense_size / required
        panels[size] = dict(
            effective_MB_s_required=required,
            dense_acquire_elapsed_budget_s=allowed,
            dense_acquire_CPU_reduction_at_zero_wait_s=max(0.0, dense_cpu - allowed),
            ratios_at_dense_cpu_only_rate=gates(
                rows, dense_size / dense_cpu, fraction, startup_s=startup
            ),
            ratios_at_observed_warm_weak_rate=gates(rows, weak_rate, fraction, startup_s=startup),
        )
    return dict(
        dense_solve_cpu_s=solve,
        dense_acquire_cpu_s=dense_cpu,
        warm_weak_MB_s=weak_rate,
        dense_CPU_only_MB_s=dense_size / dense_cpu,
        panels=panels,
    )


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--plot", type=Path)
    args = cli.parse_args()
    result = budget()
    if args.plot:
        from matplotlib.figure import Figure

        fig = Figure(figsize=(7.8, 3.45), layout="constrained")
        ax = fig.subplots()
        rates = [
            result["dense_CPU_only_MB_s"],
            result["panels"]["16"]["effective_MB_s_required"],
            result["panels"]["4"]["effective_MB_s_required"],
            result["warm_weak_MB_s"],
        ]
        descriptions = [
            "Earlier dense CPU, zero wait",
            "Required for first 16",
            "Required for first 4",
            "Measured on warm DS30-0016",
        ]
        for i, rate in enumerate(rates):
            color = "#34496b" if i in (0, 3) else "#187363"
            ax.scatter([rate], [i], color=color, s=50)
            ax.text(rate + 1.8, i, f"{rate:.1f}", va="center", color=color)
        ax.set(
            yticks=range(4),
            yticklabels=descriptions,
            ylim=(3.55, -0.55),
            xlim=(230, 310),
            xlabel="Effective compressed acquisition rate (MB/s)",
            title="Acquisition needed with a 22.76 s dense solve",
        )
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
        ax.set_axisbelow(True)
        ax.grid(axis="x", color="#e3e7ea")
        fig.savefig(args.plot, dpi=160, facecolor="white")
    print(json.dumps(result, indent=2, allow_nan=False))
