"""Render native fine-CFO and complete original detector CPU timings."""

import argparse
from statistics import median

from .. import whole_iq
from ..__main__ import local_output, save_json
from .full_v5_check import _sha
from .portable_fine_fixture import REPORT
from .prefix_figures import csv_file

NAME = "portable-fine-stage"
MODES = ("installed", "pruned", "portable")
LABELS = {
    "installed": "Installed PocketFFT",
    "pruned": "Exact pruned host",
    "portable": "Portable C",
}
COLORS = {"installed": "#60768c", "pruned": "#7f70a6", "portable": "#19786f"}


def stage_rows(report):
    manifest = whole_iq.read(report / "manifest.json")

    def member(path):
        return whole_iq.read(whole_iq.checked(report / path, manifest["files"][path]))

    output = []
    for name, case in manifest["cases"].items():
        reference, normal = member(case["reference"]), member(case["normal_detector"])
        timings = [t for row in normal["rows"] for t in row["timings"]]
        scores = [row for visit in reference["visits"] for row in visit["rows"]]
        native = case["targets"]["x86"]["summary"]
        output.append(
            dict(
                recording=name,
                score_calls=len(scores),
                fine_installed_ms=sum(row["fft_cpu_ns"] for row in scores) / len(scores) / 1e6,
                fine_portable_ms=native["score_cpu_ns"] / native["calls"] / 1e6,
                workspace_bytes=native["workspace_bytes"],
                **{
                    f"detector_{mode}_ms": median(t["cpu_ns"] for t in timings if t["mode"] == mode)
                    / 1e6
                    for mode in MODES
                },
            )
        )
    return output


def draw(report, rows):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    from matplotlib.patches import Patch

    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, (fine, total) = plt.subplots(1, 2, figsize=(11, 4.4))
    fig.subplots_adjust(left=0.13, right=0.95, top=0.77, bottom=0.28, wspace=0.26)
    fig.suptitle("Portable original fine CFO on captured IQ", y=0.96, weight="bold", fontsize=17)
    fig.text(
        0.5,
        0.886,
        "Native x86-64 process CPU  ·  four captured stereo visits per recording",
        ha="center",
        color="#475569",
    )
    for index, row in enumerate(rows):
        for mode, offset in (("installed", -0.15), ("portable", 0.15)):
            value = row[f"fine_{mode}_ms"]
            fine.barh(index + offset, value, color=COLORS[mode], height=0.25)
            fine.text(value + 0.12, index + offset, f"{value:.1f}", va="center", fontsize=8)
        for mode, offset in zip(MODES, (-0.24, 0, 0.24), strict=True):
            total.barh(index + offset, row[f"detector_{mode}_ms"], color=COLORS[mode], height=0.21)
    fine.set(
        yticks=range(len(rows)),
        yticklabels=[row["recording"] for row in rows],
        title="Fine CFO scoring",
        xlabel="Mean CPU ms per call",
        xlim=(0, 1.12 * max(row["fine_installed_ms"] for row in rows)),
    )
    total.set(
        yticks=[],
        ylim=fine.get_ylim(),
        title="Complete host detector",
        xlabel="Median CPU ms per stereo visit",
    )
    for ax in (fine, total):
        ax.invert_yaxis()
        ax.set_axisbelow(True)
        ax.grid(axis="x", color="#e2e8f0")
        ax.tick_params(axis="y", length=0)
    fig.legend(
        handles=[Patch(color=COLORS[mode], label=LABELS[mode]) for mode in MODES],
        loc="lower center",
        bbox_to_anchor=(0.54, 0.115),
        ncol=3,
        frameon=False,
    )
    fig.text(
        0.06,
        0.062,
        "Fine scorer CPU uses separate reference and standalone runs. Detector CPU uses "
        "paired warm replays.",
        fontsize=8.5,
        color="#475569",
    )
    fig.text(
        0.06,
        0.026,
        "ARM emulation qualifies numerical behavior. Physical ARM speed remains unmeasured.",
        fontsize=8.5,
        color="#475569",
    )
    fig.savefig(report / f"{NAME}.png", dpi=175)
    fig.savefig(report / f"{NAME}.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


def generate(report):
    rows = stage_rows(report)
    csv_file(report / "stage.csv", rows)
    draw(report, rows)
    save_json(
        report / "stage-figure.json",
        dict(
            version=1,
            id=NAME,
            title="Portable fine CFO scoring and original host detection",
            sample="16 authenticated stereo visits, 312 actual fine CFO grids",
            boundary="Native x86-64 fine scorer and guarded normal host detector",
            note="ARM builds agree numerically under QEMU. CPU timings describe the native host.",
            image=f"{NAME}.png",
            pdf=f"{NAME}.pdf",
            csv="stage.csv",
            seal="stage-figure-lock.json",
        ),
    )
    names = (f"{NAME}.png", f"{NAME}.pdf", "stage.csv", "stage-figure.json", "manifest.json")
    save_json(
        report / "stage-figure-lock.json", dict(files={name: _sha(report / name) for name in names})
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=local_output, default=REPORT)
    generate(parser.parse_args().report)
