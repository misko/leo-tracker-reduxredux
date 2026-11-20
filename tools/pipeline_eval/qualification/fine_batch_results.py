"""Seal and chart the matched fine-CFO frame batching comparison."""

import argparse
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

import matplotlib
import numpy as np

from ..__main__ import local_output, save_json, write
from ..variants import fine_batch
from . import fine_batch_trial as trial
from .capture_runtime import checked, decompress, read
from .fine_search_results import spread
from .full_v5_check import _sha
from .prefix_figures import csv_file

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

STAGES = ("detector", "fine", "conditioned")


def paired(raw, clock):
    old = [r[0][clock] for r in raw]
    new = [r[1][clock] for r in raw]
    delta = [a - b for a, b in zip(old, new, strict=True)]
    return dict(
        scalar=spread(old),
        batched=spread(new),
        saved=spread(delta),
        saved_percent=100 * median(d / a for d, a in zip(delta, old, strict=True)),
    )


def modes(row):
    clocks = ("cpu", "wall")
    for stage in STAGES:
        if stage == "detector":
            records = row["timings"]
            for rep in range(trial.REPEATS):
                calls = [
                    next(c for c in records if c["mode"] == m and c["repetition"] == rep)
                    for m in trial.MODES
                ]
                if calls[0]["first"] == calls[1]["first"]:
                    raise ValueError("paired passes did not alternate")
                yield (
                    stage,
                    rep,
                    [
                        dict(
                            {clock: c[f"{clock}_ns"] / 1e6 for clock in clocks},
                            first=c["first"],
                        )
                        for c in calls
                    ],
                )
            continue
        yield (
            stage,
            "",
            [
                dict(
                    {
                        clock: sum(
                            r[f"{clock}_ns"] for r in row["ports"][mode] if r["port"] == stage
                        )
                        / 1e6
                        for clock in clocks
                    },
                    first="",
                )
                for mode in trial.MODES
            ],
        )


def verify_row(row, item, counts, cache_counts, fallback):
    if any(row[key] != item[key] for key in ("visit", "kind", "iq_sha256", "probes")):
        raise ValueError("worker output differs from the frozen archive")
    public = [c for rx in row["public"]["receivers"] for c in rx["candidates"]]
    factors = [c for rx in row["probes"] for c in rx["candidates"]]
    fine = [r for r in row["ports"]["scalar"] if r["port"] == "fine"]
    conditioned = [r for r in row["ports"]["scalar"] if r["port"] == "conditioned"]
    gap = min(r["rank_gap"] for r in conditioned)
    cases = dict(
        visits=1,
        factor_rows=len(row["probes"]),
        public_candidates=len(public),
        integer_positives=sum(c["passed_margin_gate"] for c in public),
        projected_candidates=len(factors),
        fractional_positives=sum(c["passed_fractional_margin_gate"] for c in factors),
        fine_calls=len(fine),
        fine_frames=sum(r["frames"] for r in fine),
        fine_frame_bins=sum(r["frames"] * r["bins"] for r in fine),
        conditioned_calls=len(conditioned),
        conditioned_frames=sum(r["frames"] for r in conditioned),
        conditioned_frame_bins=sum(r["frames"] * r["bins"] for r in conditioned),
        conditioned_ties=sum(r["rank_gap"] == 0 for r in conditioned),
    )
    counts.update(cases)
    for signal, calls in (("fine", fine), ("conditioned", conditioned)):
        data = row["repeated_keys"][signal]
        centers = {
            (r["receiver"], r["probe"], r["epoch"], (r["first_hz"] + r["last_hz"]) / 2)
            for r in calls
        }
        cache_counts[signal].update(data)
        cache_counts[signal]["repeated_centers"] += len(calls) - len(centers)
    fallback.update(r["conditioned_fallback"] or "certified" for r in conditioned)
    return gap


def figure(out, cases):
    ypos = np.arange(len(cases))
    labels = [f"{case}\n{row['edge']}" for case, row in cases.items()]
    plots = (
        ("Complete detector", "detector", "20 paired timed calls per recording"),
        ("Fine CFO", "fine", "Four independent port audits"),
        ("Conditioned CFO", "conditioned", "Four independent port audits"),
    )
    fig, axes = plt.subplots(1, len(plots), figsize=(12, 4.8), sharey=True, layout="constrained")
    for ax, (title, stage, caption) in zip(axes, plots, strict=True):
        for mode, label, offset, color in (
            ("scalar", "Scalar prefix FFT", -0.12, "#405a77"),
            ("batched", "Four-frame prefix FFT", 0.12, "#087a70"),
        ):
            rows = [r[stage]["cpu"][mode] for r in cases.values()]
            mid = np.array([r["median"] for r in rows])
            err = [mid - [r["min"] for r in rows], [r["max"] for r in rows] - mid]
            ax.errorbar(mid, ypos + offset, xerr=err, fmt="o", capsize=3, color=color, label=label)
        ax.set_title(f"{title}\n{caption}", pad=12, fontsize=10)
        ax.set_xlabel("Process CPU time per dual visit (ms)")
        ax.set_yticks(ypos, labels)
        ax.grid(axis="x", color="#dee4ea")
        ax.set_axisbelow(True)
    axes[0].invert_yaxis()
    handles, labels = axes[-1].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", ncols=2, frameon=False)
    fig.suptitle("Batch independent frames in the exact fine CFO transform", fontsize=14)
    fig.savefig(out / "stage.png", dpi=160)
    fig.savefig(out / "stage.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


def report(work, out=trial.REPORT):
    lockfile = work / "input-lock.json"
    lock = read(lockfile)
    for path, digest in lock["sources"].items():
        checked(Path(path), digest)
    write(out / lockfile.name, lockfile.read_bytes())
    cases, data, source_files = {}, [], []
    all_pairs, counts = defaultdict(list), Counter()
    cache_counts, fallback = defaultdict(Counter), Counter()
    gaps = []
    for name, cfg in lock["cases"].items():
        receipt = work / f"{name}.json.gz"
        source_files.append(receipt.name)
        result = decompress(receipt)
        if result["input_lock_sha256"] != _sha(lockfile) or result["cpu"] != cfg["cpu"]:
            raise ValueError("worker did not use its frozen CPU and input lock")
        write(out / receipt.name, receipt.read_bytes())
        valid = defaultdict(list)
        for row, item in zip(result["rows"], cfg["rows"], strict=True):
            gaps.append(verify_row(row, item, counts, cache_counts, fallback))
            for stage, repeat, pair in modes(row):
                valid[stage].append(pair)
                all_pairs[stage].append(pair)
                for mode, entry in zip(trial.MODES, pair, strict=True):
                    data.append(
                        dict(
                            stage=stage,
                            case=name,
                            edge=cfg["edge"],
                            visit=row["visit"],
                            kind=row["kind"],
                            mode=mode,
                            repetition=repeat,
                            first=entry["first"],
                            cpu_ms=entry["cpu"],
                            wall_ms=entry["wall"],
                        )
                    )
        cases[name] = dict(
            edge=cfg["edge"],
            peak_rss_kib=result["peak_rss_kib"],
            workspace_bytes=result["workspace_bytes"],
            rotation_cache=result["rotation_cache"],
            **{k: {clock: paired(v, clock) for clock in ("cpu", "wall")} for k, v in valid.items()},
        )
    pooled = {
        k: {clock: paired(v, clock) for clock in ("cpu", "wall")} for k, v in all_pairs.items()
    }
    best = pooled["detector"]["cpu"]
    qualified = best["saved"]["median"] >= 10 and best["saved_percent"] >= 3
    save_json(
        out / "summary.json",
        dict(
            qualified=qualified,
            cases=cases,
            pooled=pooled,
            counts=dict(counts),
            exact_probe_cache_opportunities={k: dict(v) for k, v in cache_counts.items()},
            conditioned_dispatch=dict(fallback),
            smallest_conditioned_gap=min(gaps),
            binary_bytes=Path(lock["libs"]["batch"]["path"]).stat().st_size,
            added_sources={
                p.name: dict(lines=len(p.read_text().splitlines()), bytes=p.stat().st_size)
                for p in (fine_batch.SOURCE, Path(fine_batch.__file__))
            },
        ),
    )
    csv_file(out / "stage.csv", data)
    figure(out, cases)
    save_json(
        out / "stage-figure.json",
        dict(
            version=1,
            id="batched-fine-cfo-frames",
            title="Batch independent frames in the exact fine CFO transform",
            sample="16 dual IQ visits, four recordings, five paired repeats per mode",
            boundary="Resident saved IQ through the complete detector and factor projection",
            note="Ranges show observed min and max. Port clocks come from separate audits.",
            seal="qualification-lock.json",
            image="stage.png",
            pdf="stage.pdf",
            csv="stage.csv",
        ),
    )
    sealed = (
        "PROTOCOL.md",
        "input-lock.json",
        "summary.json",
        "stage.csv",
        "stage.png",
        "stage.pdf",
        "stage-figure.json",
        *source_files,
    )
    save_json(
        out / "qualification-lock.json",
        dict(
            files={name: _sha(out / name) for name in sealed},
            report_generator_sha256=_sha(Path(__file__)),
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    args = parser.parse_args()
    report(args.work)
