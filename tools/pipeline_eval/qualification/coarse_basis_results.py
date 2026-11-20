"""Summarize paired timings, retained keys and full capture output for coarse basis."""

import argparse
import csv
import gzip
import json
from pathlib import Path
from statistics import median

from ..__main__ import ROOT, save_json, write
from .coarse_basis_eval import CASES
from .full_v5_check import _sha

BANKS = (
    ("prepared", "Prepared 512"),
    ("shift250", "Shared 250"),
    ("shift500", "Shared 500"),
    ("shift1000", "Shared 1,000"),
    ("rank20", "SVD rank 20"),
    ("rank24", "SVD rank 24"),
)
DETECTORS = BANKS[0], ("shifted", "Shared 500")
STAGE_DESCRIPTOR = dict(
    version=1,
    id="coarse-basis",
    title="Share the original coarse GLRT filter bank",
    sample="Three development and six separate held stereo IQ visits across three recordings",
    boundary="Saved stereo CI16 through complete coarse search and original detector gates",
    note=(
        "The 500-point shared spectrum preserved all 96 held public candidate records and "
        "all 21 gate-positive fractional candidates. Median full detector CPU rose from "
        "417.0 to 475.0 ms across five alternating runs per visit."
    ),
    seal="stage-figure-lock.json",
    image="stage.png",
    pdf="stage.pdf",
    csv="stage.csv",
)


def unpack(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def ms(ns):
    return ns / 1e6


def collect(work):
    development = [unpack(work / f"{case}-development.json.gz") for case in CASES]
    held = [unpack(work / f"{case}-held.json.gz") for case in CASES]
    stages = []
    for receipt in development:
        for run in receipt["runs"]:
            for lane, measurements in enumerate(run["measurements"]):
                anchor_count = measurements["anchors"]
                for mode, cold in measurements["cold"].items():
                    repeated = [t["measurements"][mode] for t in measurements["timings"]]
                    accuracy = measurements["error"].get(
                        mode,
                        measurements["prepared_vs_installed"],
                    )
                    repair = measurements["offline_repair"].get(mode, {})
                    stages.append(
                        dict(
                            case=receipt["case"],
                            visit=run["witness"]["visit"],
                            receiver=lane // 2,
                            anchors=anchor_count,
                            mode=mode,
                            cpu_ms=ms(median(r["cpu_ns"] for r in repeated)),
                            wall_ms=ms(median(r["wall_ns"] for r in repeated)),
                            inverse_ffts=cold["inverse_ffts"],
                            first_filter_ffts=cold.get("filter_ffts"),
                            bytes=cold.get("buffer_bytes"),
                            reconstruction_fold_ms=ms(
                                median(r["kernel"].get("reconstruct_fold_ns", 0) for r in repeated)
                            ),
                            reconstruction_complex_multiply_adds=cold.get(
                                "reconstruction_complex_multiply_adds"
                            ),
                            score_cells=accuracy["cells"],
                            max_score_error=accuracy["max_abs"],
                            ordered_peaks=accuracy["ordered"],
                            original_peaks=len(accuracy["baseline_peaks"]),
                            matched_peaks=accuracy["common_peak_keys"],
                            repair_ordered=repair.get("ordered"),
                            repair_matched=repair.get("common_peak_keys"),
                            repair_cells=repair.get("rescored_cells"),
                        )
                    )
    detectors, decisions = [], []
    for receipt in held:
        for run in receipt["runs"]:
            label = str(run["witness"]["visit"]) if "witness" in run else run["control"]
            counters = run["installed_positive_matching"]
            decision = dict(
                case=receipt["case"],
                label=label,
                kind="radio" if "witness" in run else "synthetic",
                repeated_equal=run["repeated_equal"],
                equal_public=run["equal_public"],
                equal_coarse_path=run["equal_coarse_path"],
                equal_installed=run["equal_installed"],
                rejected_or_gated_fields=sum(
                    len(s["candidates"]) for s in run["outputs"]["installed"]["public"]["receivers"]
                ),
                installed_positive=sum(c["production_positive"] for c in counters),
                shared_positive=sum(c["native_positive"] for c in counters),
                lost_positive=sum(c["production_only"] for c in counters),
                extra_positive=sum(c["native_only"] for c in counters),
            )
            decisions.append(decision)
            for mode in ("prepared", "shifted"):
                values = [r["detectors"][mode] for r in run["timings"]]
                detectors.append(
                    dict(
                        case=receipt["case"],
                        label=label,
                        kind=decision["kind"],
                        mode=mode,
                        cpu_ms=ms(median(r["cpu_ns"] for r in values)),
                        wall_ms=ms(median(r["wall_ns"] for r in values)),
                        coarse_cpu_ms=ms(
                            median(r["stages_cpu_ns"]["coarse_inclusive"] for r in values)
                        ),
                        performed_grids=len(values[0]["grid_receipts"]),
                        fallback_22_grids=sum(
                            a["anchors"] == 22 for a in values[0]["grid_receipts"]
                        ),
                    )
                )
    return stages, detectors, decisions


def figure_rows(stages, detectors):
    rows = []
    for bank, name in BANKS:
        for anchors in (12, 22):
            values = [
                float(r["cpu_ms"])
                for r in stages
                if int(r["anchors"]) == anchors and r["mode"] == bank
            ]
            rows.append(
                dict(
                    panel="development",
                    recording="",
                    visit="",
                    series=name,
                    anchors=anchors,
                    metric="receiver_grid_cpu",
                    median_ms=median(values),
                    observations=len(values),
                    source="coarse-timing.csv",
                )
            )
    detector_names = dict(DETECTORS)
    for r in detectors:
        if r["kind"] != "radio":
            continue
        for metric, column in (("full_detector_cpu", "cpu_ms"), ("coarse_cpu", "coarse_cpu_ms")):
            rows.append(
                dict(
                    panel="held",
                    recording=r["case"],
                    visit=r["label"],
                    series=detector_names[r["mode"]],
                    anchors="",
                    metric=metric,
                    median_ms=float(r[column]),
                    observations=5,
                    source="detector-timing.csv",
                )
            )
    return rows


def plot(path, rows):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = [name for _, name in BANKS]
    fig, (left, right) = plt.subplots(1, 2, figsize=(11.2, 4.35), layout="constrained")
    x = list(range(len(labels)))
    for ns, displacement, color in ((12, -0.17, "#22577a"), (22, 0.17, "#468f74")):
        duration = [
            float(r["median_ms"])
            for r in rows
            if r["panel"] == "development" and int(r["anchors"]) == ns
        ]
        left.bar(
            [i + displacement for i in x],
            duration,
            width=0.30,
            label=f"{ns} anchors",
            color=color,
        )
    left.set_xticks(x, labels, rotation=32, ha="right")
    left.set_ylabel("Median CPU per receiver grid (ms)")
    left.set_title("Complete coarse bank on development IQ", loc="left")
    left.legend(frameon=False)

    real = [r for r in rows if r["panel"] == "held"]
    visits = list(dict.fromkeys((r["recording"], r["visit"]) for r in real))
    x = list(range(len(visits)))
    for (_, title), displacement, color in zip(
        DETECTORS,
        (-0.17, 0.17),
        ("#22577a", "#b45041"),
        strict=True,
    ):
        width, coarse = (
            [float(r["median_ms"]) for r in real if r["series"] == title and r["metric"] == metric]
            for metric in ("full_detector_cpu", "coarse_cpu")
        )
        positions = [i + displacement for i in x]
        right.bar(positions, width, width=0.30, label=title, color=color, alpha=0.4)
        right.bar(positions, coarse, width=0.30, color=color)
    right.set_xticks(
        x,
        [f"{case}\nvisit {label}" for case, label in visits],
        rotation=32,
        ha="right",
    )
    right.set_ylabel("Median CPU per dual-receiver detector (ms)")
    right.set_title("Full detector on held IQ", loc="left")
    right.set_ylim(0, 1.19 * max(float(r["median_ms"]) for r in real))
    right.legend(frameon=False)
    right.text(
        0.01,
        0.98,
        "Solid portion marks coarse search",
        transform=right.transAxes,
        va="top",
        fontsize=9,
        color="#454545",
    )
    for axis in (left, right):
        axis.spines[["top", "right"]].set_visible(False)
        axis.set_axisbelow(True)
        axis.grid(axis="y", alpha=0.2)
    fig.savefig(path.with_suffix(".png"), dpi=170)
    fig.savefig(path.with_suffix(".pdf"))
    plt.close(fig)


def csv_write(dest, rows):
    with dest.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def register_stage(out):
    """Seal the exact plotted medians with the already-rendered benchmark page."""
    stages, detectors = (
        list(csv.DictReader((out / name).read_text().splitlines()))
        for name in (
            "coarse-timing.csv",
            "detector-timing.csv",
        )
    )
    descriptor = out / "stage-figure.json"
    table, raster, pdf = (out / STAGE_DESCRIPTOR[key] for key in ("csv", "image", "pdf"))
    csv_write(table, figure_rows(stages, detectors))
    save_json(descriptor, STAGE_DESCRIPTOR)
    save_json(
        out / STAGE_DESCRIPTOR["seal"],
        dict(
            files={p.name: _sha(p) for p in (descriptor, table, raster, pdf)},
            publisher_sha256=_sha(Path(__file__)),
        ),
    )


def seal_evidence(out):
    artifacts = sorted(p for p in out.iterdir() if p.is_file() and p.name != "evidence-lock.json")
    save_json(out / "evidence-lock.json", {path.name: _sha(path) for path in artifacts})


def assemble(work, out):
    stages, detectors, decisions = collect(work)
    out.mkdir(parents=True, exist_ok=True)
    names = [work / "fixed-roster.json"]
    names.extend(work.glob("*-bank.json"))
    names.extend(work.glob("DS*-*.json.gz"))
    for path in sorted(names):
        write(out / path.name, path.read_bytes())
    csv_write(out / "coarse-timing.csv", stages)
    csv_write(out / "detector-timing.csv", detectors)
    save_json(out / "decisions.json", decisions)
    plot(out / "stage", figure_rows(stages, detectors))
    register_stage(out)
    held = [r for r in decisions if r["kind"] == "radio"]
    save_json(
        out / "qualification.json",
        dict(
            scope="capture coarse timing and published detector output",
            disposition="retain_prepared_512",
            comparison="shared_500",
            held_radio_visits=len(held),
            held_full_fields_equal=sum(r["equal_public"] and r["equal_installed"] for r in held),
            held_fractional_gate_matches=sum(
                r["installed_positive"] - r["lost_positive"] for r in held
            ),
            lost_fractional_gate_candidates=sum(r["lost_positive"] for r in held),
            extra_fractional_gate_candidates=sum(r["extra_positive"] for r in held),
            paired_repeats=5,
            median_radio_cpu_ms={
                mode: median(
                    r["cpu_ms"] for r in detectors if r["mode"] == mode and r["kind"] == "radio"
                )
                for mode in ("prepared", "shifted")
            },
            median_radio_wall_ms={
                mode: median(
                    r["wall_ms"] for r in detectors if r["mode"] == mode and r["kind"] == "radio"
                )
                for mode in ("prepared", "shifted")
            },
        ),
    )
    source_files = [
        *ROOT.glob("tools/pipeline_eval/variants/coarse_basis*"),
        *ROOT.glob("tools/pipeline_eval/qualification/coarse_basis*"),
        ROOT / "tests/pipeline_eval/test_coarse_basis.py",
        *[
            ROOT / "tools/pipeline_eval/variants" / name
            for name in (
                "original_kernel.py",
                "original_kernel_cache.h",
                "folded_bank.c",
                "capture_fft.py",
                "capture_fft.c",
                "capture_batched_fft.py",
            )
        ],
    ]
    compiled = [
        *work.glob("shift-*/*"),
        *work.glob("prepared/*"),
        *work.glob("*.so"),
    ]
    save_json(
        out / "source-lock.json",
        dict(
            current_sources={str(p.relative_to(ROOT)): _sha(p) for p in sorted(source_files)},
            measured_build_files={str(p.relative_to(work)): _sha(p) for p in sorted(compiled)},
        ),
    )
    seal_evidence(out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    assemble(args.work, args.out)
