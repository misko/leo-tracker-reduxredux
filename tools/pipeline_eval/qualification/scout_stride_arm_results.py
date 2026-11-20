"""Seal ARM stage results, binary identity tests and matched timing figures."""

import argparse
import csv
import json
import os
import subprocess
from statistics import median

import matplotlib.pyplot as plt

from ..__main__ import ROOT, save_json, write
from . import scout_stride_arm_build as build
from . import scout_stride_arm_eval as replay
from .full_v5_check import PRODUCERS, _sha
from .scout_budget_results import unpack

REPORT = replay.REPORT
MODES = replay.MODES


def unit(work, bank):
    source = ROOT / "tests/pipeline_eval/test_scout_stride_coarse.c"
    frozen = json.loads((replay.HOST / "test-lock.json").read_bytes())
    if _sha(source) != frozen[source.name]:
        raise ValueError("ARM unit is not using the common frozen arithmetic fixture")
    kernel = work / "arm-control-source/kernel/private/native_presence/coarse_fp32.h"
    prefix = kernel.read_text().split("static void coarse_float_add", 1)[0]
    header = work / "stock-magnitude.h"
    header.write_text(prefix + "#endif\n#pragma GCC pop_options\n")
    cc = json.loads((work / "arm-control/build-receipt.json").read_bytes())["compiler"]
    binary = work / "test-scout-stride-arm"
    subprocess.run(
        [
            cc,
            "-std=c11",
            "-O3",
            "-fno-fast-math",
            "-mcpu=cortex-a9",
            "-mfpu=neon",
            "-mfloat-abi=hard",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-include",
            str(header),
            "-I",
            str(ROOT / "tools/pipeline_eval/variants"),
            str(source),
            "-o",
            str(binary),
            "-lm",
        ],
        env={**os.environ, "TMPDIR": str(work / "compiler-temp")},
        check=True,
    )
    found = subprocess.run(
        ["qemu-arm", "-cpu", "cortex-a9", "-L", bank["sysroot"], str(binary)],
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    return dict(
        exit_code=found.returncode,
        binary_sha256=_sha(binary),
        unit_source_sha256=_sha(source),
        stock_magnitude_source_sha256=_sha(header),
        stdout=found.stdout,
        stderr=found.stderr,
    )


def compute(tables, controls):
    rows = [(p["id"], r) for p in tables for r in p["rows"] if r["status"] == "processed"]
    scoring = {}
    matches = {}
    for mode in MODES:
        visits = [(case, r["visit"], p) for case, r in rows for p in r["archive_comparison"]]
        fits = [p["fits"][mode] for _, _, p in visits]
        matches[mode] = {
            (case, visit, p["receiver"], m["production_rank"])
            for case, visit, p in visits
            for m in p["fits"][mode]["positive_matches"]
        }
        calls = [c for _, r in rows for c in r["timings"][mode]]
        host = [h for _, r in rows for h in r["host_comparison"][mode]["host_as_reference"]]
        scoring[mode] = dict(
            calls=len(calls),
            native_positive=sum(f["native_positive"] for f in fits),
            archived_positive=sum(f["production_positive"] for f in fits),
            archive_matches=len(matches[mode]),
            archive_raw_cfo_matches=sum(
                abs(m["raw_cfo_delta_hz"]) < 1000 for f in fits for m in f["positive_matches"]
            ),
            cpu_ms=sum(c["detector_cpu_ms"] for c in calls),
            coarse_ms=sum(s["coarse"] for c in calls for s in c["rows"]),
            external_s=sum(c["external_wall_s"] for c in calls),
            median_cpu_ms=median(c["detector_cpu_ms"] for c in calls),
            emulator_peak_kib=max(c["emulator_peak_kib"] for c in calls),
            host_positive=sum(h["production_positive"] for h in host),
            host_matches=sum(len(h["positive_matches"]) for h in host),
            host_raw_cfo_matches=sum(
                abs(m["raw_cfo_delta_hz"]) < 1000 for h in host for m in h["positive_matches"]
            ),
            numeric_equal_host_rows=sum(
                r["host_comparison"][mode]["exact_public_rows"] for _, r in rows
            ),
            numeric_equal_host_control_rows=sum(
                r["host_comparison"][mode]["exact_public_rows"] for r in controls.values()
            ),
            warm={
                t["id"]: dict(
                    start_ms=t["warm_profile"][mode]["init_wall_ms"],
                    first_cpu_ms=t["warm_profile"][mode]["calls"][0]["cpu_ms"],
                    steady_cpu_ms=median(c["cpu_ms"] for c in t["warm_profile"][mode]["calls"][1:]),
                    steady_fine_fft_ms=median(
                        c["fine_fft_cpu_ms"] for c in t["warm_profile"][mode]["calls"][1:]
                    ),
                    rss_kib=t["warm_profile"][mode]["emulator_peak_kib"],
                )
                for t in tables
            },
        )
    return dict(
        admitted=len(rows),
        scheduled=sum(len(x["rows"]) for x in tables),
        same_arms_native_payloads=sum(r["exact"] for _, r in rows),
        architecture="qemu-arm cortex-a9",
        position_attempted=False,
        modes=scoring,
        gained_archive=sorted(matches["stride"] - matches["control"]),
        lost_archive=sorted(matches["control"] - matches["stride"]),
        changed_plants={
            name: dict(arm=v["planted_matches"], host=v["host_planted_matches"])
            for name, v in controls.items()
            if v["planted_matches"] != v["host_planted_matches"]
            or v["planted_matches"]["control"] != v["planted_matches"]["stride"]
        },
        control_positive_counts={
            name: {m: [len(rx) for rx in r["positives"][m]] for m in MODES}
            for name, r in controls.items()
        },
    )


def figure(tables):
    rows = []
    for table in tables:
        ident = table["id"]
        host = {r["visit"]: r for r in replay.host_receipt(f"{ident}-held.json.gz")["rows"]}
        for r in table["rows"]:
            if r["status"] != "processed":
                continue
            for arch, panel in (("x86 native", host[r["visit"]]), ("Cortex-A9 QEMU", r)):
                for mode in MODES:
                    series = panel["timings"][mode]
                    rows.append(
                        dict(
                            architecture=arch,
                            case=ident,
                            visit=r["visit"],
                            mode=mode,
                            detector_cpu_ms=median(c["detector_cpu_ms"] for c in series),
                            coarse_cpu_ms=median(
                                sum(b["coarse"] for b in c["rows"]) for c in series
                            ),
                        )
                    )
    csv_path = REPORT / "stage.csv"
    with csv_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    fig, axes = plt.subplots(2, 2, figsize=(9.7, 5.4), layout="constrained")
    for column, arch in enumerate(("x86 native", "Cortex-A9 QEMU")):
        for row_no, (quantity, label) in enumerate(
            (
                ("detector_cpu_ms", "Whole detector CPU (ms)"),
                ("coarse_cpu_ms", "Regional coarse CPU (ms)"),
            )
        ):
            ax = axes[row_no, column]
            for x, mode in enumerate(MODES):
                data = [
                    r[quantity] for r in rows if r["architecture"] == arch and r["mode"] == mode
                ]
                ax.scatter([x] * len(data), data, c=("#3465a4", "#b24c2e")[x], s=21, zorder=3)
            keys = [
                (r["case"], r["visit"])
                for r in rows
                if r["architecture"] == arch and r["mode"] == "control"
            ]
            for ident, visit in keys:
                pair = [
                    r[quantity]
                    for r in rows
                    if r["architecture"] == arch and r["case"] == ident and r["visit"] == visit
                ]
                ax.plot([0, 1], pair, color="#9b9b9b", linewidth=0.7, alpha=0.7)
            ax.set(
                xlim=(-0.25, 1.25),
                xticks=[0, 1],
                xticklabels=["Full bank", "Strided bank"],
                ylabel=label,
            )
            ax.grid(axis="y", alpha=0.25)
            if row_no == 0:
                ax.set_title(arch)
    fig.suptitle("Matched saved-IQ detector calls at 10 MS/s, Cortex-A9 emulated")
    for suffix in ("pdf", "png"):
        fig.savefig(REPORT / f"stage.{suffix}", dpi=175)
    plt.close(fig)


def publish(work):
    if replay.sources() != json.loads((REPORT / "source-lock.json").read_bytes()):
        raise ValueError("The ARM source lock changed after scoring")
    bank = replay.load_arm(work)
    tables = [unpack(REPORT / f"{c}.json.gz") for c in PRODUCERS]
    controls = unpack(REPORT / "controls.json.gz")["results"]
    table = compute(tables, controls)
    table["arm_component_unit"] = unit(work, bank)
    save_json(REPORT / "qualification.json", table)
    save_json(REPORT / "release.json", bank)
    for mode in MODES:
        write(REPORT / f"{mode}-build.json", (work / f"arm-{mode}/build-receipt.json").read_bytes())
    figure(tables)
    stage = ("stage.csv", "stage.pdf", "stage.png", "qualification.json")
    save_json(
        REPORT / "stage-figure-manifest.json",
        dict(
            id="scout-stride-cortex-a9-emulation",
            scope="detector stage",
            position_attempted=False,
            files={f: _sha(REPORT / f) for f in stage},
        ),
    )
    names = (
        "PROTOCOL.md",
        "AFFINITY.md",
        "source-lock.json",
        "affinity-receipt.json",
        "release.json",
        "control-build.json",
        "stride-build.json",
        "stage-figure-manifest.json",
        "controls.json.gz",
        "source/affinity-as-run.py.txt",
        *(f"{case}.json.gz" for case in PRODUCERS),
        *stage,
        *(f"released-cli-cpu0/{f}.json.gz" for f in (*PRODUCERS, "controls")),
    )
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=list(PRODUCERS),
            files={f: _sha(REPORT / f) for f in names},
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work", type=type(build.WORK), default=build.WORK)
    publish(p.parse_args().work)
