"""Summarize complete ARMv7 stock and fifth-center detector results."""

import argparse
import csv
import json
from pathlib import Path
from statistics import median

import matplotlib

from ..__main__ import save_json
from . import fifth_arm, oracle_start
from .full_v5_check import _from_native, _sha

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

ARCH = ("host", "arm")


def endpoint(row, target):
    projected = [
        p for i, c in enumerate(row["candidates"]) if (p := _from_native(i, c)) is not None
    ]
    return oracle_start.endpoints(target, dict(candidates=projected), row)


def ordered_fractional(rows, mode):
    deltas = {key: 0.0 for key in ("offset_samples", "tracking_cfo_hz", "margin")}
    statuses, complete = 0, 0
    for item in rows.values():
        left, right = (item["study"][arch][mode]["rows"] for arch in ARCH)
        for host, arm in zip(left, right, strict=True):
            for a, b in zip(host["candidates"], arm["candidates"], strict=True):
                if (a["epoch"], a["coarse_bin"]) != (b["epoch"], b["coarse_bin"]):
                    raise ValueError("candidate order differs across builds")
                af, bf = a["fractional_epoch"], b["fractional_epoch"]
                if af["status"] != bf["status"]:
                    raise ValueError("fractional refinement status differs across builds")
                statuses += 1
                if af["status"] == "complete":
                    complete += 1
                    for key in deltas:
                        deltas[key] = max(deltas[key], abs(af[key] - bf[key]))
    return dict(equal_statuses=statuses, complete=complete, max_delta=deltas)


def result_data(folder):
    binding = folder / "source-lock.json"
    lock = json.loads(binding.read_bytes())
    observed = json.loads((folder / "measurements.json").read_bytes())
    if _sha(binding) != observed["source_lock_sha256"]:
        raise ValueError("measured and sealed detector inputs differ")
    rows = observed["rows"]
    if rows.keys() != lock["input"].keys():
        raise ValueError("measured and sealed detector rosters differ")
    totals, stages = {}, []
    for mode in fifth_arm.MODES:
        pairs = [r["comparison"][mode] for r in rows.values()]
        lanes = [lane for p in pairs for lane in p["lanes"]]
        hits = [hit for lane in lanes for hit in lane["positive_matches"]]
        timings = {}
        for arch in ARCH:
            current = [r["study"][arch][mode] for r in rows.values()]
            timings[arch] = {
                stage: {
                    key.removesuffix("_ns"): median(c[stage][key] / 1e6 for c in current)
                    for key in ("cpu_ns", "wall_ns")
                }
                for stage in ("read", "detector_context", "scout_context")
            }
            for stage in ("scout", "detector"):
                timings[arch][stage] = {
                    key.removesuffix("_ns"): median(
                        c["calls"][0][stage][key] / 1e6 for c in current
                    )
                    for key in ("cpu_ns", "wall_ns")
                }
            timings[arch]["process"] = {
                k: median(c["process_ms"][k] for c in current) for k in ("cpu", "wall")
            }
            for title, record in rows.items():
                data = record["study"][arch][mode]
                stages.append(
                    dict(
                        fixture=title,
                        edge=record["edge"],
                        kind=record["kind"],
                        architecture=arch,
                        mode=mode,
                        process_cpu_ms=data["process_ms"]["cpu"],
                        process_wall_ms=data["process_ms"]["wall"],
                        **{
                            f"{stage}_{clock}_ms": data[stage][f"{clock}_ns"] / 1e6
                            for stage in ("read", "detector_context", "scout_context")
                            for clock in ("cpu", "wall")
                        },
                        **{
                            f"{stage}_{clock}_ms": data["calls"][0][stage][f"{clock}_ns"] / 1e6
                            for stage in ("scout", "detector")
                            for clock in ("cpu", "wall")
                        },
                        **{
                            f"rx{rx}_{stage}_cpu_ms": lane["timings_ms"][stage]
                            for rx, lane in enumerate(data["rows"])
                            for stage in ("coarse", "fine_fft", "fractional_epoch")
                        },
                    )
                )
        totals[mode] = dict(
            exact_payloads=sum(p["exact_payload"] for p in pairs),
            lane_integer_order=sum(lane["ordered_integer_keys_match"] for lane in lanes),
            trace_exact=sum(p["support_trace_exact"] for p in pairs),
            exact_rank16_lanes=sum(sum(p["full16_matches"]) for p in pairs),
            ordered_fractional=ordered_fractional(rows, mode),
            full_candidates={
                "host": sum(lane["production_complete"] for lane in lanes),
                "arm": sum(lane["native_complete"] for lane in lanes),
            },
            positives={
                "host": sum(lane["production_positive"] for lane in lanes),
                "arm": sum(lane["native_positive"] for lane in lanes),
                "matched": len(hits),
            },
            max_matched_delta={
                k: max((abs(h[k]) for h in hits), default=0.0)
                for k in (
                    "epoch_delta_samples",
                    "raw_cfo_delta_hz",
                    "aliased_cfo_delta_hz",
                    "margin_delta",
                )
            },
            timing_median_ms=timings,
        )
    target_endpoints = {}
    for title, source in lock["input"].items():
        row = rows[title]
        if (
            not all(row["host_matches_previous"].values())
            or not row["host_rank_one_matches_previous"]
        ):
            raise ValueError(
                "standalone native x86 diverged from the sealed identical-source detector"
            )
        if "target" in source:
            target_endpoints[title] = {
                arch: {
                    mode: endpoint(
                        row["study"][arch][mode]["rows"][source["receiver"]], source["target"]
                    )
                    for mode in fifth_arm.MODES
                }
                for arch in ARCH
            }
        elif source["kind"] == "noise":
            if any(
                lane[k]
                for data in row["comparison"].values()
                for lane in data["lanes"]
                for k in ("production_positive", "native_positive")
            ):
                raise ValueError("a signed detector boundary produced a noise false positive")
        elif source["kind"] == "strong":
            target = dict(
                integer_epoch_sample=source["synthetic"]["epoch"],
                fractional_epoch_offset_samples=0,
                fractional_tracking_cfo_hz=source["synthetic"]["cfo_hz"],
                fractional_margin=0,
            )
            if not all(
                endpoint(lane, target)["physical_passes"]
                for arch in ARCH
                for mode in fifth_arm.MODES
                for lane in row["study"][arch][mode]["rows"]
            ):
                raise ValueError("signed control missed its physical CFO or fractional epoch")
    with (folder / "stage.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(stages[0]))
        writer.writeheader()
        writer.writerows(stages)
    summary = dict(
        fixtures=len(rows),
        real=len(target_endpoints),
        modes=totals,
        targets=target_endpoints,
        affinity=observed["affinity"],
        host_previous_payloads=2 * len(rows),
        qemu=lock["qemu_version"],
        null_abi_checks=sum("off" in row["study"][a] for row in rows.values() for a in ARCH),
    )
    save_json(folder / "summary.json", summary)
    return summary


def figure(folder, summary):
    fig, ax = plt.subplots(figsize=(9.6, 4.5))
    stages = (
        ("Stock detector", "stock", "detector"),
        ("Union scout", "union", "scout"),
        ("Union detector", "union", "detector"),
        ("Whole stock process", "stock", "process"),
        ("Whole union process", "union", "process"),
    )
    for arch, label, delta, color in (
        ("host", "Native x86-64", -0.19, "#355d77"),
        ("arm", "Cortex-A9 QEMU", 0.19, "#198574"),
    ):
        times = [
            summary["modes"][mode]["timing_median_ms"][arch][stage]["cpu"]
            for _, mode, stage in stages
        ]
        x = [i + delta for i in range(len(stages))]
        ax.bar(x, times, color=color, width=0.34, label=label)
        for loc, y in zip(x, times, strict=True):
            ax.text(loc, y * 1.12, f"{y:.1f}", ha="center", fontsize=9)
    ax.set_yscale("log")
    ax.set_ylim(3, 2600)
    ax.set_ylabel("Median CPU (ms, log scale)")
    ax.set_xticks(range(len(stages)), [label.replace(" ", "\n", 1) for label, _, _ in stages])
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.22)
    ax.legend(loc="upper center", bbox_to_anchor=(0.50, -0.19), frameon=False, ncol=2)
    fig.suptitle(
        "The complete fifth-center detector on ARMv7",
        x=0.095,
        y=0.99,
        ha="left",
        fontweight="bold",
        fontsize=16,
    )
    stock = summary["modes"]["stock"]["positives"]
    union = summary["modes"]["union"]["positives"]
    fig.text(
        0.095,
        0.88,
        f"{summary['real']} genuine and {summary['fixtures'] - summary['real']} control windows. "
        f"Matched gated stock {stock['matched']}/{max(stock['host'], stock['arm'])}, "
        f"union {union['matched']}/{max(union['host'], union['arm'])}. ARM timing is emulated.",
        fontsize=10,
    )
    fig.subplots_adjust(left=0.095, right=0.98, top=0.80, bottom=0.245)
    fig.savefig(folder / "stage.png", dpi=175)
    fig.savefig(folder / "stage.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


def publish(folder):
    extraction = json.loads((folder / "capsule-verification.json").read_bytes())
    if (
        extraction["archive_sha256"] != _sha(folder / "fifth-armv7.tar.gz")
        or extraction["modes"].keys() != set(fifth_arm.MODES)
        or not all(
            entry["exact_science"] and entry["exact_rank16"] and entry["exact_trace"]
            for entry in extraction["modes"].values()
        )
    ):
        raise ValueError("extracted capsule does not reproduce the measured ARM detector")
    figure(folder, result_data(folder))
    files = (
        "source-lock.json",
        "measurements.json",
        "capsule-verification.json",
        "summary.json",
        "stage.png",
        "stage.pdf",
        "stage.csv",
        "fifth-armv7.tar.gz",
    )
    save_json(
        folder / "result-lock.json",
        dict(
            files={name: _sha(folder / name) for name in files}, source_sha256=_sha(Path(__file__))
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    publish(parser.parse_args().folder)
