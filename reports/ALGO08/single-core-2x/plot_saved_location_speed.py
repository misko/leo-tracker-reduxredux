"""Compare component CPU savings across the released geographic development controls."""

import argparse
from hashlib import sha256
from pathlib import Path

from .screened_tiled_graph_trial import KEYS, MEASUREMENTS, evidence_digests, read, write


def record_controls(directory):
    receipt = MEASUREMENTS / "solver-wide-private-blocks.json"
    prior = read(receipt)
    pairs = {}
    for case, baseline, treatment in (
        ("DS30-0008", "control-0008-uninstrumented.json", "terminal.json"),
        ("southern-portable", "control-south-uninstrumented.json", "south.json"),
    ):
        original = prior["cases"][case]["wider_private"]
        times = {}
        for label, file in (("control", baseline), ("wider", treatment)):
            path = directory / file
            run = read(path)
            if (any(run[k] != original[k] for k in KEYS)
                    or evidence_digests(run) != original["science"]):
                raise ValueError(f"Changed scientific result on {case} in {label}")
            times[label] = {k: run[k] for k in ("solver_cpu_s", "solver_wall_s")}
            if label == "wider" and any(times[label][k] != original[k] for k in times[label]):
                raise ValueError(f"Unexpected treatment clock on {case}")
            times[label]["terminal_file_sha256"] = sha256(path.read_bytes()).hexdigest()
        pairs[case] = times
    output = MEASUREMENTS / "solver-wide-private-plain-controls.json"
    document = dict(specification=prior["specification"],
                    instrumented_receipt_sha256=sha256(receipt.read_bytes()).hexdigest(),
                    run_order=["wider", "control"], pairs=pairs)
    if output.exists():
        if read(output) != document:
            raise ValueError("Control results differ from the published measurement")
    else:
        write(output, document)


def plot():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mtick

    fir = read(MEASUREMENTS / "receiver-fir-tile.json")
    ranks = (read(MEASUREMENTS / "sparse-rank-projection.json")["results"]
             | read(MEASUREMENTS / "sparse-rank-projection-omitted.json")["results"])
    solves = read(MEASUREMENTS / "solver-wide-private-plain-controls.json")["pairs"]
    rows = [
        ("Complete receiver", "DS26, weak carriers", fir["weak"]["median_paired_saved"]),
        ("Complete receiver", "Austin, measured signal",
         fir["Austin"]["physical"]["median_paired_saved"]),
    ]
    for key, label in (("DS30-0008", "DS30, dense recording"), ("India", "India, containing"),
                       ("Portable south omitted", "Southern Africa, far omission")):
        modes = ranks[key]["results"]
        saving = 1 - modes["sparse"]["cpu_less_audit_s"] / modes["dense"]["cpu_less_audit_s"]
        rows.append(("Satellite ranking", label, saving))
    for key, label in (("DS30-0008", "DS30, dense recording"),
                       ("southern-portable", "Southern Africa, containing")):
        pair = solves[key]
        saving = 1 - pair["wider"]["solver_cpu_s"] / pair["control"]["solver_cpu_s"]
        rows.append(("Complete solver", label, saving))

    fig, axes = plt.subplots(1, 3, figsize=(11.6, 3.6), sharex=True)
    fig.subplots_adjust(left=.035, right=.965, top=.73, bottom=.24, wspace=.22)
    lo = min(0, min(row[2] for row in rows)) - .025
    hi = max(row[2] for row in rows) + .04
    titles = {"Complete receiver": "Receiver · tiled FIR",
              "Satellite ranking": "Ranking · sparse projection",
              "Complete solver": "Solver · wider native blocks"}
    for ax, (group, title) in zip(axes, titles.items(), strict=True):
        ax.set_title(title, loc="left", fontweight="bold")
        ax.axvline(0, color="#718086", linewidth=.8)
        ax.set_yticks([])
        ax.set(xlim=(lo, hi), ylim=(-.65, 3.5))
        ax.xaxis.set_major_locator(mtick.MultipleLocator(.05))
        ax.xaxis.set_major_formatter(mtick.PercentFormatter(1, decimals=0))
        ax.grid(axis="x", alpha=.18)
        ax.spines[["top", "left", "right"]].set_visible(False)
        for i, (_, label, value) in enumerate(row for row in rows if row[0] == group):
            y = 2.6 - 1.25 * i
            ax.text(.01, y + .23, label, transform=ax.get_yaxis_transform(), fontsize=9)
            ax.hlines(y, 0, value, color="#137b78", linewidth=3)
            ax.scatter(value, y, color="#126c68", s=28, zorder=3)
            ax.annotate(f"{value:+.1%}", (max(0, value), y), xytext=(6, -3),
                        textcoords="offset points", fontsize=9)
    fig.suptitle("Single-core CPU saved by each change on saved inputs", x=.035, ha="left",
                 fontweight="bold", fontsize=17)
    fig.text(.035, .075, "Positive values mean less CPU. Receiver points use paired repeats. "
             "Ranking and solver points use one pair per input.", fontsize=9)
    fig.text(.035, .025, "DS26 and DS30 share a station. India and southern Africa are "
             "simulations. Austin supplies measured receiver I/Q.", fontsize=9)
    fig.savefig(MEASUREMENTS.parent / "saved-location-stage-speed.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record-controls", type=Path)
    args = parser.parse_args()
    if args.record_controls is not None:
        record_controls(args.record_controls)
    plot()
