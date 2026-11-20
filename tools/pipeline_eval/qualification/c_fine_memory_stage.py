"""Render complete raw-detector timing and allocation from held native replays."""

import argparse
import csv
import json
from pathlib import Path
from statistics import median

from .c_fine_memory_build import ROOT, digest
from .c_fine_memory_trial import ARMS, REPORT, write_json

NAME = "c-fine-memory"
LABELS = {"stock": "Stock C", "compact": "Compact C"}
COLORS = {"stock": "#526982", "compact": "#037e70"}
MEASURES = (
    ("process_cpu_ms_per_visit", "Complete CPU", "ms / dual visit"),
    ("elapsed_ms_per_visit", "Complete wall", "ms / dual visit"),
    ("verify_cpu_ms_per_visit", "Verifier CPU", "ms / dual visit"),
    ("vm_hwm_mib", "Process peak RSS", "MiB"),
    ("verifier_workspace_mib", "Verifier workspace", "MiB"),
    ("fine_call_stack_kib", "Main-to-fine C stack", "KiB"),
)
STACK_PATH = (
    "main",
    "run",
    "portable_verifier_acquire",
    "portable_fine_score",
    "fine_search_transform",
)


def measurement_rows(evidence):
    rows = []
    for arm in ARMS:
        sample = [
            r
            for r in evidence["timings"]
            if (r["target"], r["fixture"], r["arm"]) == ("x86", "held", arm)
        ]
        if len(sample) < 5 or len({r["candidates"] for r in sample}) != 1:
            raise ValueError("Held measurements need five complete matched replays")
        compiler = evidence["builds"][f"x86-{arm}-full"]["stack"]
        frame = {location.split(":")[-1]: size for location, (size, _) in compiler.items()}
        stack = sum(frame[name] for name in STACK_PATH) / 1024
        metrics = {
            "process_cpu_ms_per_visit": [
                row["process_cpu_ns"] / 1e6 / row["visits"] for row in sample
            ],
            "elapsed_ms_per_visit": [row["elapsed_ns"] / 1e6 / row["visits"] for row in sample],
            "verify_cpu_ms_per_visit": [
                row["verify_cpu_ns"] / 1e6 / row["visits"] for row in sample
            ],
            "vm_hwm_mib": [row["vm_hwm_kib"] / 1024 for row in sample],
            "verifier_workspace_mib": [row["verifier_workspace_bytes"] / 2**20 for row in sample],
            "fine_call_stack_kib": [stack] * len(sample),
        }
        row = dict(
            arm=arm,
            runs=len(sample),
            visits=sample[0]["visits"],
            groups=sample[0]["groups"],
            candidates=sample[0]["candidates"],
        )
        for key, values in metrics.items():
            row.update(
                {
                    f"{key}_median": median(values),
                    f"{key}_min": min(values),
                    f"{key}_max": max(values),
                }
            )
        rows.append(row)
    return rows


def draw(report, rows):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(2, 3, figsize=(10.8, 5.55))
    fig.subplots_adjust(left=0.14, right=0.975, top=0.78, bottom=0.16, wspace=0.60, hspace=1.00)
    fig.suptitle(
        "Compact C verifier in the full portable detector", fontsize=17, weight="bold", y=0.96
    )
    item = rows[0]
    fig.text(
        0.5,
        0.878,
        f"{item['visits']} held stereo visits from three recordings  ·  "
        f"{item['candidates']} verified candidates per run  ·  {item['runs']} native timing pairs",
        ha="center",
        color="#475569",
    )
    for i, (ax, (key, title, units)) in enumerate(zip(axes.flat, MEASURES, strict=True)):
        end = 0
        for position, row in enumerate(rows):
            arm = row["arm"]
            mid, low, high = (row[f"{key}_{field}"] for field in ("median", "min", "max"))
            ax.barh(position, mid, height=0.55, color=COLORS[arm])
            ax.errorbar(
                mid, position, xerr=[[mid - low], [high - mid]], capsize=3, color="#111827", lw=1.2
            )
            end = max(end, high)
        ax.set(
            title=title,
            xlabel=units,
            xlim=(0, end * 1.19),
            yticks=[0, 1],
            yticklabels=[LABELS[row["arm"]] for row in rows] if i in (0, 3) else ["", ""],
        )
        ax.invert_yaxis()
        ax.tick_params(axis="y", length=0)
        ax.set_axisbelow(True)
        ax.grid(axis="x", color="#e2e8f0")
    fig.text(
        0.04,
        0.055,
        "Bars show medians and whiskers show observed ranges. "
        "Stack values sum compiler-reported C frames. Position accuracy was unmeasured.",
        color="#475569",
        fontsize=8.5,
    )
    fig.savefig(report / f"{NAME}.png", dpi=165)
    fig.savefig(report / f"{NAME}.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


def generate(report, evidence_file):
    report.mkdir(parents=True, exist_ok=True)
    evidence = json.loads(evidence_file.read_text())
    rows = measurement_rows(evidence)
    evidence["trial_source_sha256"] = {
        str(path.relative_to(ROOT)): digest(path.read_bytes())
        for directory in (ROOT / "tools/pipeline_eval/qualification", ROOT / "tests/pipeline_eval")
        for path in sorted(directory.glob("*c_fine_memory*.py"))
    }
    write_json(report / "qualification.json", evidence)
    with (report / "stage.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    draw(report, rows)
    write_json(
        report / "stage-figure.json",
        dict(
            version=1,
            id=NAME,
            title="Compact C verifier in the full portable detector",
            sample="12 held stereo CI16 replays from DS26-0237, DS29-0082 and DS29-0519",
            boundary="Raw saved IQ through full portable dual-lane detection and conditional retry",
            note=(
                "Native x86 on CPUs 10 and 11. Matching stage decisions. "
                "Position accuracy unmeasured."
            ),
            image=f"{NAME}.png",
            pdf=f"{NAME}.pdf",
            csv="stage.csv",
            seal="stage-figure-lock.json",
        ),
    )
    names = ("stage-figure.json", "stage.csv", "qualification.json", f"{NAME}.png", f"{NAME}.pdf")
    write_json(
        report / "stage-figure-lock.json",
        dict(files={name: digest((report / name).read_bytes()) for name in names}),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--report", type=Path, default=REPORT)
    args = parser.parse_args()
    generate(args.report, args.evidence)
