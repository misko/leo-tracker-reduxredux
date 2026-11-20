"""Export saved-packet parity, selective grid writes and paired native timing."""

import argparse
import csv
import gzip
import shutil
from pathlib import Path

import matplotlib

from .. import whole_iq
from ..__main__ import encoded, local_output, save_json, write
from . import native_pruning_build as build
from . import native_pruning_eval as trial
from .full_v5_check import _sha
from .native_hotpath_results import distribution

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

COUNT = 13333
BINS = 21
STRIDE = 24


def work_counts(epochs):
    if len(epochs) > 15 or any(not 0 <= x < COUNT for x in epochs) or epochs != sorted(set(epochs)):
        raise ValueError("observed regional epochs violate the exact scratch guard")
    n = len(epochs)
    neighbors = sum(
        int(x > 0 and (i == 0 or epochs[i - 1] < x - 1))
        + int(x + 1 < COUNT and (i + 1 == n or epochs[i + 1] > x + 1))
        for i, x in enumerate(epochs)
    )
    return dict(
        cleared_bytes=4 * (STRIDE + 1) * n,
        dense_cleared_bytes=4 * (STRIDE + 1) * COUNT,
        grid_cells=BINS * (n + neighbors),
        dense_grid_cells=BINS * COUNT,
        active_cfo_cells=BINS * n,
    )


def csv_file(path, rows):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def observations(work):
    report = build.REPORT
    lock = report / "source-lock.json"
    sources = whole_iq.read(lock)
    measured = whole_iq.read(work / "measurements.json")
    if measured["source_lock_sha256"] != _sha(lock):
        raise ValueError("the measured roster was not frozen")
    cases, timings, proofs, outputs = {}, [], [], []
    for ident, item in measured["cases"].items():
        valid = [row for row in sources["roster"][ident] if row["status"] == "valid"]
        edge = valid[0]["edge"]
        whole = valid + sources["roster"][edge]
        if [row["fixture"] for row in item["rows"]] != whole:
            raise ValueError("one or more scheduled held visits disappeared")
        cases[ident] = dict(scheduled=len(sources["roster"][ident]), measured=len(valid))
        for capture in item["rows"]:
            fixture = capture["fixture"]
            identity = dict(case=ident, fixture=fixture["name"], kind=fixture["kind"], edge=edge)
            genuine = fixture["kind"] == "genuine"
            for mode, repetitions in capture["modes"].items():
                if len(repetitions) != (3 if genuine else 1) or not all(
                    trial.exact(p) for p in repetitions
                ):
                    raise ValueError("the recorded roles changed a result or missed a repetition")
                public = repetitions[0]["candidate"]["science"]
                if genuine:
                    totals = {
                        k: a + b
                        for (k, a), (_, b) in zip(
                            work_counts(public["active"][0]).items(),
                            work_counts(public["active"][1]).items(),
                            strict=True,
                        )
                    }
                    proofs.append(
                        dict(
                            **identity,
                            mode=mode,
                            sha256=public["sha256"],
                            candidates=public["candidates"],
                            gates=sum(public["gains"]),
                            **totals,
                        )
                    )
                else:
                    outputs.append(dict(**identity, mode=mode, scientific=public))
                for rep, pair in enumerate(repetitions):
                    for role, row in pair.items():
                        clocks = row["clocks"]
                        timings.append(
                            dict(
                                **identity,
                                mode=mode,
                                rep=rep,
                                role=role,
                                cpu_ms=clocks["cpu_ns"] / 1e6,
                                wall_ms=clocks["wall_ns"] / 1e6,
                                typed_wall_ms=clocks["typed_ns"] / 1e6,
                                within_20ms=clocks["wall_ns"] <= 20_000_000,
                                **row["stages"],
                            )
                        )
    return cases, timings, proofs, outputs, measured


def summarize(timings, proof):
    scopes = {}
    for case in ("all", *trial.source.CASES):
        scope = scopes[case] = {}
        for mode in trial.MODES:
            cells = scope[mode] = {}
            retained = [
                r
                for r in timings
                if r["kind"] == "genuine"
                and r["mode"] == mode
                and (case == "all" or r["case"] == case)
            ]
            paired = {}
            for role in trial.ROLES:
                rows = [r for r in retained if r["role"] == role]
                paired[role] = {(r["fixture"], r["rep"]): r for r in rows}
                cells[role] = dict(
                    calls=len(rows),
                    deadline=sum(r["within_20ms"] for r in rows),
                    **{
                        k: distribution([row[k] for row in rows])
                        for k in rows[0]
                        if k.endswith("_ms")
                    },
                )
            cells["paired_delta"] = {
                k: distribution(
                    [row[k] - paired["control"][key][k] for key, row in paired["candidate"].items()]
                )
                for k in ("cpu_ms", "wall_ms", "coarse_cpu_ms")
            }
            rows = [r for r in proof if r["mode"] == mode and (case == "all" or r["case"] == case)]
            cells["work"] = {
                key: sum(r[key] for r in rows)
                for key in (
                    "candidates",
                    "gates",
                    "cleared_bytes",
                    "dense_cleared_bytes",
                    "grid_cells",
                    "dense_grid_cells",
                    "active_cfo_cells",
                )
            }
    return scopes


def figures(report, scopes):
    fig, axes = plt.subplots(1, 2, figsize=(9.9, 4.5))
    for sign, role, color in ((-0.17, "control", "#5c7186"), (0.17, "candidate", "#0d8375")):
        for axis, metric in zip(axes, ("wall_ms", "coarse_cpu_ms"), strict=True):
            stats = [scopes["all"][mode][role][metric] for mode in trial.MODES]
            spots = [i + sign for i in range(3)]
            axis.bar(
                spots, [r["p50"] for r in stats], width=0.31, label=role.capitalize(), color=color
            )
            axis.scatter(
                spots,
                [r["p95"] for r in stats],
                color=color,
                marker="D",
                edgecolor="white",
                zorder=4,
            )
    axes[0].axhline(20, linestyle="--", color="#888888", linewidth=0.8)
    for axis, ylabel in zip(
        axes, ("Complete call wall (ms)", "Both lanes' coarse CPU (ms)"), strict=True
    ):
        axis.set_xticks(range(3), ("Four", "Five", "Staggered"))
        axis.set_ylabel(ylabel)
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="y", alpha=0.18)
    handles, names = axes[0].get_legend_handles_labels()
    fig.legend(
        handles, names, frameon=False, loc="lower center", ncol=2, bbox_to_anchor=(0.5, 0.018)
    )
    fig.text(
        0.06,
        0.95,
        "Write only the GLRT grid cells the search reads",
        fontsize=16,
        fontweight="bold",
    )
    fig.text(
        0.06,
        0.89,
        "96 authenticated dual-RX visits. Bars are medians. Diamonds are p95.",
        fontsize=10,
    )
    fig.subplots_adjust(left=0.09, right=0.98, top=0.83, bottom=0.18, wspace=0.28)
    fig.savefig(report / "stage.png", dpi=170)
    fig.savefig(report / "stage.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


def publish(work):
    report = build.REPORT
    cases, timings, proofs, controls, measured = observations(work)
    scopes = summarize(timings, proofs)
    save_json(report / "summary.json", dict(cases=cases, timing=scopes, controls=controls))
    csv_file(report / "stage.csv", timings)
    csv_file(report / "work-parity.csv", proofs)
    write(report / "measurements.json.gz", gzip.compress(encoded(measured), mtime=0))
    canonical = work / "build/build.json"
    row = whole_iq.read(canonical)
    shutil.copyfile(canonical, report / "build.json")
    shutil.copyfile(
        whole_iq.checked(work / "build/detector/build-receipt.json", row["detector_build_sha256"]),
        report / "detector-build.json",
    )
    figures(report, scopes)
    candidate = {
        name: dict(
            path=str(whole_iq.checked(work / "build/candidate" / name, digest)), sha256=digest
        )
        for name, digest in row["library_sha256"]["candidate"].items()
    }
    save_json(
        report / "feature-gate.json",
        dict(
            passed=True,
            scope="complete matched stock, fifth and one-fifth detector rows on saved IQ",
            control=row["library_sha256"]["control"],
            candidate=candidate,
            cases=cases,
            matched_science=True,
            files={
                n: _sha(report / n)
                for n in ("build.json", "source-lock.json", "work-parity.csv", "summary.json")
            },
        ),
    )
    files = (
        "source-lock.json",
        "summary.json",
        "stage.csv",
        "work-parity.csv",
        "measurements.json.gz",
        "build.json",
        "detector-build.json",
        "stage.png",
        "stage.pdf",
        "feature-gate.json",
    )
    save_json(
        report / "result-lock.json",
        dict(files={n: _sha(report / n) for n in files}, publisher_sha256=_sha(Path(__file__))),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    publish(parser.parse_args().work)
