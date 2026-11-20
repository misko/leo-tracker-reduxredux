"""Render full resident detector timings and process image RSS."""

import argparse

from .. import whole_iq
from ..__main__ import local_output, save_json
from .full_v5_check import _sha
from .prefix_figures import csv_file
from .verifier_integration_trial import MODES, REPORT

NAME = "verifier-integration-stage"
LABELS = {
    "installed": "Installed",
    "prepared": "Prepared",
    "portable_installed": "Portable on installed coarse",
    "portable_prepared": "Portable on prepared coarse",
}
COLORS = {
    "installed": "#74899b",
    "prepared": "#756ea4",
    "portable_installed": "#4b9d99",
    "portable_prepared": "#215f5d",
}


def measurements(report):
    manifest = whole_iq.read(report / "manifest.json")
    result = []
    for ident, case in manifest["cases"].items():
        for mode in MODES:
            source = case["arms"][mode]["summary"]
            result.append(
                dict(
                    recording=ident,
                    arm=mode,
                    cpu=case["cpu"],
                    visits=source["visits"],
                    replay_samples=source["replay_samples"],
                    setup_wall_ms=source["setup_wall_ms"],
                    first_resident_wall_ms=source["first_resident_wall_ms"],
                    median_warm_wall_ms=source["median_warm_wall_ms"],
                    median_warm_cpu_ms=source["median_warm_cpu_ms"],
                    peak_process_rss_mib=source["peak_rss_kib"] / 1024,
                    native_probe_attempts=source["native_routes"].get("portable", 0),
                    peer_retry_attempts=source["peer_attempts"],
                )
            )
    return result


def draw(report, rows):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    from matplotlib.patches import Patch

    plt.rcParams.update({"font.size": 9.5, "axes.spines.right": False, "axes.spines.top": False})
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.5))
    fig.subplots_adjust(top=0.76, bottom=0.31, left=0.13, right=0.95, wspace=0.24)
    fig.suptitle(
        "Portable verifier in the original live detector path", y=0.963, weight="bold", fontsize=16
    )
    fig.text(0.5, 0.893, "Twelve held stereo visits  ·  three installed producers", ha="center")
    groups = tuple(dict.fromkeys(r["recording"] for r in rows))
    fields = (
        ("median_warm_cpu_ms", "Warm detector CPU", "Median ms per visit"),
        ("median_warm_wall_ms", "Warm detector elapsed", "Median ms per visit"),
        ("peak_process_rss_mib", "Peak process RSS", "MiB"),
    )
    for ax, (field, title, unit) in zip(axes, fields, strict=True):
        for row in rows:
            i = groups.index(row["recording"])
            mode = row["arm"]
            y = i + (MODES.index(mode) - 1.5) * 0.17
            ax.barh(y, row[field], color=COLORS[mode], height=0.14)
        ax.set(
            title=title,
            xlabel=unit,
            yticks=range(len(groups)),
            yticklabels=groups if ax is axes[0] else [],
        )
        ax.set_ylim(len(groups) - 0.54, -0.47)
        ax.grid(axis="x", color="#e2e8f0")
        ax.set_axisbelow(True)
        ax.tick_params(axis="y", length=0)
    fig.legend(
        handles=[Patch(color=COLORS[m], label=LABELS[m]) for m in MODES],
        loc="lower center",
        bbox_to_anchor=(0.55, 0.128),
        ncol=4,
        frameon=False,
    )
    fig.text(
        0.05,
        0.063,
        "Each arm used its own process and the same assigned core for a recording. "
        "IQ authentication preceded timing.",
        fontsize=8.5,
        color="#475569",
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
            title="Portable verifier in the original live detector path",
            sample="Twelve held complete stereo visits and three warm repeats per visit and arm",
            boundary="Full host resident detector including live coarse selection and peer retry",
            note="RSS includes the producer, the staged visits and each arm’s reusable context.",
            image=f"{NAME}.png",
            pdf=f"{NAME}.pdf",
            csv="stage.csv",
            seal="stage-figure-lock.json",
        ),
    )
    names = ("manifest.json", "stage-figure.json", "stage.csv", f"{NAME}.png", f"{NAME}.pdf")
    save_json(report / "stage-figure-lock.json", dict(files={n: _sha(report / n) for n in names}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=local_output, default=REPORT)
    generate(parser.parse_args().report)
