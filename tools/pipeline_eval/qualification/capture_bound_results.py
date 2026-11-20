"""Audit bound selectivity and derive measured whole-detector costs."""

import argparse
import csv
import gzip
import json
from collections import Counter
from pathlib import Path
from statistics import median

import matplotlib

from ..__main__ import encoded, save_json
from . import capture_bound_trial as trial
from .full_v5_check import BULK, _load_case, _sha

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402


def csv_file(path, rows):
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def metrics(record, methods):
    pair = record["pairs"]
    return dict(
        pairs=len(pair),
        cpu_ms={m: median(r[m]["cpu_ns"] / 1e6 for r in pair) for m in methods},
        wall_ms={m: median(r[m]["wall_ns"] / 1e6 for r in pair) for m in methods},
        paired_cpu_median_improvement_percent=100
        * median(1 - r["bound"]["cpu_ns"] / r["stock"]["cpu_ns"] for r in pair),
    )


def positives(probes):
    return [[c for c in r["candidates"] if c["passed_fractional_margin_gate"]] for r in probes]


def summarize(work):
    lock = trial.verified(work)
    stages, audits, by_case = [], [], {}
    genuine_probes = 0
    names = {ident: _sha(work / f"{ident}.json.gz") for ident in trial.CASES}
    save_json(
        work / "prediction-lock.json",
        dict(
            files={
                "input-lock.json": _sha(work / "input-lock.json"),
                **{f"{i}.json.gz": s for i, s in names.items()},
            }
        ),
    )
    for ident in trial.CASES:
        data = json.loads(gzip.decompress((work / f"{ident}.json.gz").read_bytes()))
        case = _load_case(ident)
        archive = BULK / case["native"]["path"]
        if _sha(archive) != lock["cases"][ident]["archive_sha256"]:
            raise ValueError("signed original native content differs")
        frozen = {
            (p["visit_index"], p["receiver_id"]): p
            for p in json.loads(archive.read_bytes())["source"]["probes"]
        }
        originals = [row for row in data["cases"] if "pairs" in row]
        visits = {r["visit"]: r for r in lock["cases"][ident]["windows"] if "visit" in r}
        control_orig = visits[originals[-1]["visit"]]["meta"]
        cfo_center = (
            control_orig["target"]["rf_center_hz"]
            - control_orig["target"]["lnb_lo_hz"]
            - control_orig["acquisition"]["actual_if_center_hz"]
        )
        for row in originals:
            probes = row["pairs"][0]["stock"]["probes"]
            for p in probes:
                if encoded(p) != encoded(frozen[row["visit"], p["receiver_id"]]):
                    raise ValueError("original detector no longer reproduces archive factors")
            genuine_probes += len(probes)
        controls = {}
        for name, row in data["controls"].items():
            seen = positives(row["pairs"][0]["stock"]["probes"])
            plant = row["plant"]
            if plant:
                t, f, _ = plant[0]
                match = [
                    any(
                        abs(c["integer_epoch_sample"] + c["fractional_epoch_offset_samples"] - t)
                        <= 2
                        and abs(c["fractional_tracking_cfo_hz"] - f - cfo_center) <= 1000
                        for c in lane
                    )
                    for lane in seen
                ]
            else:
                match = None
            controls[name] = dict(gated_counts=list(map(len, seen)), matches_plant=match)
        all_rows = [(str(r["visit"]), "saved", r) for r in originals] + [
            (k, k, r) for k, r in data["controls"].items()
        ]
        for name, label, row in all_rows:
            for repeat, paired in enumerate(row["pairs"], 1):
                for mode, m in paired.items():
                    stages.append(
                        dict(
                            case=ident,
                            scope=label,
                            sample=name,
                            repeat=repeat,
                            method=mode,
                            cpu_ms=m["cpu_ns"] / 1e6,
                            wall_ms=m["wall_ns"] / 1e6,
                            omitted_cells=sum(r["omitted_cells"] for r in m["preflight"]),
                            preflight_cpu_ms=sum(
                                r["preflight"]["cpu_ns"] for r in m["preflight"] if r["preflight"]
                            )
                            / 1e6,
                            gated_count=sum(map(len, positives(m["probes"]))),
                        )
                    )
            for attempt in row["audit"]:
                for method, results in attempt["methods"].items():
                    report = dict(results)
                    if "cpu_ns" in report:
                        report["bound_cpu_ms"] = report.pop("cpu_ns") / 1e6
                    audits.append(
                        dict(
                            case=ident,
                            scope=label,
                            sample=name,
                            method=method,
                            **{k: v for k, v in attempt.items() if k != "methods"},
                            **report,
                        )
                    )
        by_case[ident] = dict(
            saved=metrics(dict(pairs=[p for r in originals for p in r["pairs"]]), trial.MODES),
            controls={
                k: dict(metrics(v, trial.MODES), **controls[k]) for k, v in data["controls"].items()
            },
            saved_visits=len(originals),
            excluded=len(data["cases"]) - len(originals),
        )
    csv_file(work / "stage.csv", stages)
    csv_file(work / "bound-audit.csv", audits)
    totals = {}
    for name in ("blocks", "per_tap"):
        rows = [r for r in audits if r["method"] == name and "cells" in r]
        nonzero = [r for r in rows if r["scope"] != "empty"]
        totals[name] = dict(
            audited_attempts=len(rows),
            cells=sum(r["cells"] for r in rows),
            nonzero_cells=sum(r["cells"] for r in nonzero),
            violations=sum(r["violations"] for r in rows),
            rank_mismatches=sum(not r["retained_exact_equal"] for r in rows),
            audited_nominal_terms=sum(r["bound_terms"] for r in rows),
            optimistic_nonzero_cut=sum(r["optimistic_cut_cells"] for r in nonzero),
            median_saved_bound_cpu_ms=median(
                r["bound_cpu_ms"] for r in nonzero if r["scope"] == "saved"
            ),
        )
    result = dict(
        cases=by_case,
        methods=totals,
        archived_exact_native_probes=genuine_probes,
        true_skipped_cells_by_scope=dict(
            Counter(
                {
                    k: sum(x["omitted_cells"] for x in stages if x["scope"] == k)
                    for k in {r["scope"] for r in stages}
                }
            )
        ),
    )
    save_json(work / "summary.json", result)
    return by_case, audits, totals


def figures(work, by_case, audits, totals):
    fig, (left, right) = plt.subplots(1, 2, figsize=(10.8, 4.8))
    usable = [r for r in audits if r.get("threshold") is not None and r["method"] == "per_tap"]
    for j, (label, values, color) in enumerate(
        (
            ("Exact 8th score", [r["threshold"] for r in usable], "#324d70"),
            ("Tightest magnitude-only bound", [r["bound_min"] for r in usable], "#8f532a"),
            (
                "Four-block Cauchy bound",
                [
                    r["bound_min"]
                    for r in audits
                    if r.get("threshold") is not None and r["method"] == "blocks"
                ],
                "#187d75",
            ),
        )
    ):
        positions = [j + (i % 5 - 2) * 0.047 for i in range(len(values))]
        left.scatter(values, positions, color=color, s=22, alpha=0.67, label=label)
    left.set_yticks(range(3), ["Eighth score", "Per-tap minimum bound", "Four-block minimum bound"])
    left.invert_yaxis()
    left.set_xlabel("Folded coarse score")
    left.set_title("Each attempt’s safest exclusion test", loc="left", fontweight="bold")
    left.set_xlim(0.1, 1.0)
    entries = [
        ("Legacy saved", by_case["DS26-0036"]["saved"]["cpu_ms"]),
        ("Screened saved", by_case["DS29-0174"]["saved"]["cpu_ms"]),
        ("Legacy empty", by_case["DS26-0036"]["controls"]["empty"]["cpu_ms"]),
        ("Screened empty", by_case["DS29-0174"]["controls"]["empty"]["cpu_ms"]),
    ]
    for mode, shift, color, label in (
        ("stock", -0.14, "#324d70", "Installed capture"),
        ("bound", 0.14, "#187d75", "Bound preflight"),
    ):
        right.scatter(
            [i + shift for i in range(4)],
            [x[1][mode] for x in entries],
            color=color,
            s=47,
            label=label,
        )
    right.set_yscale("log")
    right.set_xticks(range(4), [x[0].replace(" ", "\n") for x in entries])
    right.set_ylabel("Median detector CPU (ms, log scale)")
    right.set_title("Whole detector after loading IQ", loc="left", fontweight="bold")
    right.legend(loc="upper center", bbox_to_anchor=(0.5, -0.25), ncol=2, frameon=False)
    for ax in (left, right):
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(alpha=0.20)
    fig.suptitle(
        "Magnitude bounds could not prune nonzero capture IQ",
        x=0.092,
        y=0.986,
        ha="left",
        fontweight="bold",
        fontsize=16,
    )
    count = totals["per_tap"]["nonzero_cells"]
    fig.text(
        0.092,
        0.895,
        f"0 / {count:,} nonzero cells excluded, even with the original cutoff supplied for free.",
        fontsize=10,
    )
    fig.subplots_adjust(left=0.245, right=0.98, wspace=0.38, top=0.817, bottom=0.26)
    fig.savefig(work / "stage.png", dpi=175)
    fig.savefig(work / "stage.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


def publish(work):
    figures(work, *summarize(work))
    files = (
        "input-lock.json",
        "prediction-lock.json",
        *(f"{id}.json.gz" for id in trial.CASES),
        "summary.json",
        "stage.png",
        "stage.pdf",
        "stage.csv",
        "bound-audit.csv",
    )
    save_json(
        work / "result-lock.json",
        dict(files={f: _sha(work / f) for f in files}, source_sha256=_sha(Path(__file__))),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    publish(parser.parse_args().work)
