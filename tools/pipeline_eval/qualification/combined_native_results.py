"""Publish the combined detector study and the independently bound paced fit."""

import argparse
import csv
import gzip
import shutil
from pathlib import Path

import matplotlib
import numpy as np

from .. import whole_iq
from ..__main__ import encoded, local_output, save_json, write
from . import combined_native_build as build
from . import combined_native_eval as evaluate
from . import combined_native_pace as live
from .full_v5_check import _sha
from .native_hotpath_results import distribution

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

TITLE = "Fifth-center GLRT with two persistent lanes and a shared fractional grid"
DISPLAY = {
    "serial": "Released serial",
    "parallel": "Parallel",
    "fused": "Parallel + fractional reuse",
}


def csv_file(path, rows):
    with path.open("w", newline="") as f:
        result = csv.DictWriter(f, fieldnames=list(rows[0]))
        result.writeheader()
        result.writerows(rows)


def summarize_stage(work):
    lock_path = build.REPORT / "native-source-lock.json"
    lock = whole_iq.read(lock_path)
    result = whole_iq.read(work / "native-results.json")
    if result["source_lock_sha256"] != _sha(lock_path):
        raise ValueError("stage timing differs from its fixed IQ roster")
    records, resources, exact = [], [], []
    for case, capture in result["cases"].items():
        roster = [r for r in lock["roster"][case] if r["status"] == "valid"]
        edge = roster[0]["edge"]
        if [r["fixture"] for r in capture["rows"]] != roster + lock["roster"][edge]:
            raise ValueError("combined replay did not process the complete scheduled panel")
        for role, end in capture["end"].items():
            start = capture["start"][role]
            mem = end["memory"]
            if (
                end["membership"] != start["membership"]
                or int(mem["memory.max"]) != whole_iq.MEMORY
                or int(mem["memory.swap.max"])
                or dict(line.split() for line in mem["memory.events"].splitlines())["oom_kill"]
                != "0"
            ):
                raise ValueError("short stage exceeded its declared cgroup")
            resources.append(
                dict(
                    case=case,
                    role=role,
                    memory_peak_bytes=int(mem["memory.peak"]),
                    rss_peak_kib=end["peak_rss_kib"],
                    cgroup_cpu_s=(end["cpu_stat"]["usage_usec"] - start["cpu_stat"]["usage_usec"])
                    / 1e6,
                    memory_limit_bytes=int(mem["memory.max"]),
                    swap_limit_bytes=int(mem["memory.swap.max"]),
                )
            )
        for row in capture["rows"]:
            fixture = row["fixture"]
            for mode, pairs in row["modes"].items():
                if len(pairs) != 3 or not all(evaluate.same_roles(pair) for pair in pairs):
                    raise ValueError("combined replay differs from its typed comparator")
                out = pairs[0]["serial"]
                exact.append(
                    dict(
                        case=case,
                        kind=fixture["kind"],
                        fixture=fixture["name"],
                        mode=mode,
                        candidates=sum(out["counts"]),
                        gates=sum(out["gates"]),
                        sha256=out["sha256"],
                    )
                )
                for rep, pair in enumerate(pairs):
                    for role, r in pair.items():
                        c = r["clocks"]
                        lane = c.get("lanes") or [None, None]
                        records.append(
                            dict(
                                case=case,
                                kind=fixture["kind"],
                                fixture=fixture["name"],
                                mode=mode,
                                rep=rep,
                                role=role,
                                cpu_ms=c["cpu_ns"] / 1e6,
                                wall_ms=c["wall_ns"] / 1e6,
                                typed_wall_ms=c["typed_ns"] / 1e6,
                                caller_cpu=lock["cpus"][0],
                                helper_cpu=None if role == "serial" else lock["cpus"][1],
                                lane0_cpu_ms=(lane[0]["cpu_ns"] / 1e6) if lane[0] else None,
                                lane1_cpu_ms=(lane[1]["cpu_ns"] / 1e6) if lane[1] else None,
                                within_20ms=c["wall_ns"] <= 20_000_000,
                            )
                        )
    summary = {}
    for scope in ("all", *evaluate.CASES):
        summary[scope] = {}
        for mode in ("stock", "fifth"):
            summary[scope][mode] = {}
            for role in evaluate.ROLES:
                rows = [
                    r
                    for r in records
                    if r["kind"] == "genuine"
                    and r["mode"] == mode
                    and r["role"] == role
                    and (scope == "all" or scope == r["case"])
                ]
                base = [
                    r
                    for r in exact
                    if r["kind"] == "genuine"
                    and r["mode"] == mode
                    and (scope == "all" or scope == r["case"])
                ]
                summary[scope][mode][role] = dict(
                    real=len(base),
                    pairs=len(rows),
                    deadline=sum(r["within_20ms"] for r in rows),
                    records=sum(r["candidates"] for r in base),
                    gates=sum(r["gates"] for r in base),
                    **{
                        k: distribution([r[k] for r in rows])
                        for k in ("cpu_ms", "wall_ms", "typed_wall_ms")
                    },
                )
    report = build.REPORT
    csv_file(report / "native-timing.csv", records)
    csv_file(report / "native-resources.csv", resources)
    csv_file(report / "native-parity.csv", exact)
    save_json(report / "native-summary.json", summary)
    write(report / "native-measurements.json.gz", gzip.compress(encoded(result), mtime=0))
    shutil.copyfile(work / "build/build.json", report / "native-build.json")
    shutil.copyfile(work / "build/detector/build-receipt.json", report / "detector-build.json")
    return summary


def stage_figure(report, summary):
    fig, axs = plt.subplots(1, 2, figsize=(10.4, 4.7))
    for delta, role, color in zip(
        (-0.23, 0, 0.23), evaluate.ROLES, ("#677988", "#9d8263", "#097d71"), strict=True
    ):
        modes = [summary["all"][m][role] for m in ("stock", "fifth")]
        xs = np.arange(2) + delta
        axs[0].bar(
            xs, [r["wall_ms"]["p50"] for r in modes], width=0.21, label=DISPLAY[role], color=color
        )
        axs[0].scatter(
            xs,
            [r["wall_ms"]["p95"] for r in modes],
            color=color,
            marker="D",
            edgecolor="white",
            zorder=3,
        )
        axs[1].bar(xs, [100 * r["deadline"] / r["pairs"] for r in modes], width=0.21, color=color)
    axs[0].axhline(20, color="#888888", linestyle="--", linewidth=0.9)
    for ax, label in zip(
        axs, ("Decoded call wall (ms)", "Calls at or below 20 ms (%)"), strict=True
    ):
        ax.set_xticks((0, 1), ("Stock", "Fifth center"))
        ax.set_ylabel(label)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.18)
    handles, names = axs[0].get_legend_handles_labels()
    fig.legend(
        handles, names, loc="lower center", ncol=3, bbox_to_anchor=(0.5, 0.018), frameon=False
    )
    fig.text(
        0.06, 0.96, "Two GLRT lanes and a shared fractional grid", fontsize=16, fontweight="bold"
    )
    fig.text(
        0.06,
        0.90,
        "96 held dual-RX windows. Wall bars are medians. Diamonds are 95th percentiles.",
        fontsize=10,
    )
    fig.subplots_adjust(left=0.08, right=0.97, top=0.84, bottom=0.19, wspace=0.30)
    fig.savefig(report / "stage.png", dpi=170)
    fig.savefig(report / "stage.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


def stage(work):
    report = build.REPORT
    stage_figure(report, summarize_stage(work))
    files = (
        "native-source-lock.json",
        "native-build.json",
        "detector-build.json",
        "native-measurements.json.gz",
        "native-summary.json",
        "native-resources.csv",
        "native-parity.csv",
        "native-timing.csv",
        "stage.png",
        "stage.pdf",
    )
    save_json(
        report / "native-lock.json",
        dict(files={k: _sha(report / k) for k in files}, publisher_sha256=_sha(Path(__file__))),
    )


def finish_staged(work):
    """Authenticate the staged compact request and adapt its digest field name."""
    from . import support_cross_trial as receiver
    from .phase_support_results import pack

    report = live.PACED
    plan = live.pace.plan(work, report)
    staged = whole_iq.read(report / "position-input-lock.json")
    stats = whole_iq.read(report / "raw-summary.json")
    if stats["status"] != "complete" or stats["native_packets_emitted"] != staged["row"]["emitted"]:
        raise ValueError("the planned numerical run lacks its complete real paced stream")
    row = staged["row"]
    folder = work / live.CASE / row["condition"]
    request = whole_iq.checked(folder / "recording/request.json", row["request_sha256"])
    raw = whole_iq.read(folder / "raw.json")
    witness = whole_iq.read(report / "raw-witness.json")
    original = work / live.CASE / live.MODE / "visits.jsonl"
    whole_iq.checked(original, row["verified_raw_envelope_sha256"])
    if (
        _sha(request) != raw["request_sha256"]
        or raw["native_sha256"].removeprefix("sha256:") != row["native_sha256"]
        or witness["output_sha256"] != row["verified_raw_envelope_sha256"]
    ):
        raise ValueError("staged raw or request digest changed before compact launch")
    measured = receiver.service(work, row | {"prepared_request_sha256": row["request_sha256"]})
    pack(report / "positions.jsonl.gz", [measured])
    events = plan["cases"][live.CASE]["modes"][live.MODE]["events"]
    files = (
        "source-lock.json",
        "raw-summary.json",
        "raw-service.json",
        "raw-witness.json",
        "trace.json.gz",
        "position-input-lock.json",
        "positions.jsonl.gz",
        events,
    )
    save_json(
        report / "position-lock.json",
        dict(
            cases=[live.CASE],
            files={n: _sha(report / n) for n in files},
            request_digest_adapter_sha256=_sha(Path(__file__)),
        ),
    )


def endpoint():
    from ..scoring import ARMS
    from . import fresh_adaptive as historical
    from .full_held_scores import held_references
    from .margin_admission_results import fit, sealed
    from .phase_support_results import pack

    report = live.PACED
    current = sealed(report, "position-lock.json", "positions.jsonl.gz")
    old = [
        r
        for r in sealed(historical.REPORT, "prediction-lock.json", "predictions.jsonl.gz")
        if r["id"] == live.CASE and r["condition"] in ("adaptive", "fifth")
    ]
    if len(current) != 1 or len(old) != 2 or current[0]["method"] != live.METHOD:
        raise ValueError("position series roster changed")
    keys = ("paired_capture_sha256", "original_request_sha256", "catalog_sha256", "tile")
    if any(any(current[0][k] != r[k] for k in keys) for r in old):
        raise ValueError("historical runs used a different physical source or offered tile")
    rows = current + old
    (truth,) = held_references(None, [live.CASE])[1]
    scores = [fit(row, truth, arm) for row in rows for arm in ARMS]
    csv_file(report / "scores.csv", scores)
    pack(report / "overlay-positions.jsonl.gz", rows)
    cap = whole_iq.read(report / "raw-summary.json")
    history = historical.REPORT / "raw-budget.csv"
    before = [r for r in csv.DictReader(history.open()) if r["id"] == live.CASE]
    trace = live.pace.readgz(report / "trace.json.gz")
    live_rows = [r for r in trace if r["outcome"] == "emitted"]
    summary = dict(
        actual=cap
        | dict(
            native_within_20ms=sum(r["native_wall_ns"] <= 20_000_000 for r in live_rows),
            age_within_20ms=sum(r["emitted_ns"] - r["arrival_ns"] <= 20_000_000 for r in live_rows),
            cpus=[live.MAIN, live.HELPER],
            run_order="one fused replay",
        ),
        historical=before,
        historical_order=["adaptive", "fifth"],
        historical_cpu=18,
        historical_raw_budget_sha256=_sha(history),
        historical_position_lock_sha256=_sha(historical.REPORT / "prediction-lock.json"),
        position_resources=current[0].get("position_resources"),
    )
    save_json(report / "paced-comparison.json", summary)
    files = (
        "overlay-positions.jsonl.gz",
        "position-lock.json",
        "scores.csv",
        "paced-comparison.json",
        "raw-summary.json",
        "raw-witness.json",
    )
    save_json(
        report / "figure-lock.json",
        dict(cases=[live.CASE], files={n: _sha(report / n) for n in files}),
    )
    series = [
        dict(
            key=key,
            label=label,
            file=files[0],
            value=method,
            native_field="paired_capture_sha256",
            match=list(keys),
        )
        for key, label, method in (
            ("one", "Fused paced fifth · CPUs 20/21", live.METHOD),
            ("one_native_factors", "Earlier paced fifth · CPU18 second", "fresh_adaptive_fifth"),
            ("stock", "Earlier paced adaptive · CPU18 first", "fresh_adaptive_adaptive"),
        )
    ]
    save_json(
        report / "figures.json",
        dict(
            version=2,
            charts=[
                dict(
                    id="combined-native-paced",
                    method=live.METHOD,
                    scope="roof",
                    cases="sealed",
                    title="Combined fifth-center receiver at the original arrival pace",
                    caption=(
                        "The fused replay uses CPUs 20/21. Earlier CPU18 runs used adaptive first "
                        "and fifth second. The four v5 options use their capture-era factors."
                    ),
                    seal="figure-lock.json",
                    provenance=list(files[1:]),
                    series=series,
                )
            ],
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("stage", "finish-staged", "endpoint"))
    parser.add_argument("work", type=local_output)
    args = parser.parse_args()
    if args.action == "endpoint":
        endpoint()
    else:
        {"stage": stage, "finish-staged": finish_staged}[args.action](args.work)
