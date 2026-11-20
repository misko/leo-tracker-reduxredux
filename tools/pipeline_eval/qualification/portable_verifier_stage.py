"""Render native portable verification cost and numeric threshold evidence."""

import argparse

from .. import whole_iq
from ..__main__ import local_output, save_json
from .full_v5_check import _sha
from .portable_verifier_fixture import REPORT
from .prefix_figures import csv_file

NAME = "portable-verifier-stage"
LABELS = {"acquire": "Fine, conditioned, held pilots", "glrt": "Circular and continuous GLRT"}
COLORS = {"acquire": "#24786e", "glrt": "#586aa9"}


def measurements(report):
    manifest = whole_iq.read(report / "manifest.json")
    rows = []
    for ident, case in manifest["cases"].items():
        native = case["targets"]["x86"]
        raw = native["resources"]
        timing = whole_iq.read(whole_iq.checked(report / raw, manifest["files"][raw]))
        counts = native["counts"]
        if timing["candidates"] != counts["candidates"]:
            raise ValueError("reported timing has a different candidate denominator")
        rows.append(
            dict(
                recording=ident,
                visits=counts["visits"],
                candidates=counts["candidates"],
                complete=counts["complete"],
                unbracketed=counts["candidates"] - counts["complete"],
                fractional_pass=counts["fractional_pass"],
                fractional_no_pass=counts["complete"] - counts["fractional_pass"],
                acquire_ms_per_candidate=timing["acquire_cpu_ns"] / 1e6 / counts["candidates"],
                glrt_ms_per_candidate=timing["glrt_cpu_ns"] / 1e6 / counts["candidates"],
                process_ms_per_candidate=timing["process_cpu_ns"] / 1e6 / counts["candidates"],
                peak_rss_kib=timing["peak_rss_kib"],
            )
        )
    return rows


def draw(report, rows):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    from matplotlib.patches import Patch

    plt.rcParams.update({"font.size": 10, "axes.spines.right": False, "axes.spines.top": False})
    fig, (time, gates) = plt.subplots(1, 2, figsize=(10.9, 4.6))
    fig.subplots_adjust(top=0.77, bottom=0.30, left=0.135, right=0.95, wspace=0.26)
    fig.suptitle("Portable original candidate verifier", y=0.95, fontsize=17, weight="bold")
    fig.text(0.5, 0.88, "Six authenticated stereo visits  ·  112 retained candidates", ha="center")
    outcomes = (
        ("unbracketed", "Unbracketed", "#c7cfd5"),
        ("fractional_no_pass", "Below gate", "#bc785f"),
        ("fractional_pass", "Passed", "#24786e"),
    )
    for i, row in enumerate(rows):
        left = 0
        for mode in LABELS:
            value = row[f"{mode}_ms_per_candidate"]
            time.barh(i, value, left=left, color=COLORS[mode], height=0.53)
            left += value
        time.text(left + 0.12, i, f"{left:.1f}", va="center", fontsize=9)
        left = 0
        for key, _, color in outcomes:
            value = row[key]
            gates.barh(i, value, left=left, color=color, height=0.53)
            if value:
                gates.text(left + value / 2, i, str(value), va="center", ha="center", fontsize=9)
            left += value
    time.set(
        yticks=range(len(rows)),
        yticklabels=[row["recording"] for row in rows],
        title="Native x86 process CPU",
        xlabel="Mean ms per candidate",
        xlim=(0, 11),
    )
    gates.set(
        yticks=[],
        ylim=time.get_ylim(),
        title="Fractional GLRT outcomes",
        xlabel="Candidates evaluated",
        xlim=(0, 66),
    )
    for ax in (time, gates):
        ax.invert_yaxis()
        ax.set_axisbelow(True)
        ax.grid(axis="x", color="#e2e8f0")
        ax.tick_params(axis="y", length=0)
    for ax, entries in (
        (time, [(COLORS[k], label) for k, label in LABELS.items()]),
        (gates, [(color, label) for _, label, color in outcomes]),
    ):
        ax.legend(
            handles=[Patch(color=color, label=label) for color, label in entries],
            loc="upper left",
            bbox_to_anchor=(0, -0.26),
            frameon=False,
            ncol=len(entries),
            fontsize=8,
            handlelength=1.1,
            columnspacing=0.8,
        )
    fig.text(
        0.06,
        0.072,
        "Timings start with supplied coarse seeds. ARM binaries were verified under QEMU.",
        color="#475569",
        fontsize=9,
    )
    fig.savefig(report / f"{NAME}.png", dpi=175)
    fig.savefig(report / f"{NAME}.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


def generate(report):
    rows = measurements(report)
    draw(report, rows)
    csv_file(report / "stage.csv", rows)
    save_json(
        report / "stage-figure.json",
        dict(
            version=1,
            id=NAME,
            title="Portable original candidate verifier",
            sample="Six checksum-bound stereo visits and 112 retained candidates",
            boundary="Fine CFO to bracketed fractional GLRT after supplied coarse epochs",
            note="Candidate groups include the original peer verification groups when offered.",
            image=f"{NAME}.png",
            pdf=f"{NAME}.pdf",
            csv="stage.csv",
            seal="stage-figure-lock.json",
        ),
    )
    names = ("manifest.json", "stage-figure.json", "stage.csv", f"{NAME}.png", f"{NAME}.pdf")
    save_json(
        report / "stage-figure-lock.json", dict(files={name: _sha(report / name) for name in names})
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=local_output, default=REPORT)
    generate(parser.parse_args().report)
