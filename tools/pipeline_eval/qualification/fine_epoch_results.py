"""Publish exact per-lane refinement reuse and complete paired CPU evidence."""

import argparse
import csv
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from struct import pack

import matplotlib
import numpy as np

from ..__main__ import save_json
from . import fine_epoch_benchmark as bench
from . import fine_epoch_trial as trial
from .capture_runtime import checked, read
from .full_v5_check import _sha
from .prefix_figures import csv_file

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402


def frequency_key(values):
    return tuple(pack("=d", v) for v in values)


def traffic(trace):
    seen, previous = defaultdict(set), defaultdict(set)
    counts = Counter()
    visits = Counter()
    for row in trace:
        port = row["kind"]
        stage = "original_pass" if row["pass_number"] == 0 else "direct_recheck"
        if port == "coarse":
            counts[f"{stage}_{row['anchors']}_coarse"] += 1
            continue
        visits[port] += 1
        key = (
            port,
            *row["lane"],
            row["epoch"],
            tuple(row["starts"]),
            tuple(row["symbols"] or ()),
            row["template_sha256"],
        )
        physical = (key[0], *key[1:3], *key[4:])
        bins = frequency_key(row["grid"])
        counts[f"{port}_cells"] += len(bins)
        if key in previous:
            counts[f"{port}_repeated_epoch"] += 1
            counts[f"{port}_overlapping_cells"] += len(previous[key].intersection(bins))
        if bins in seen[key]:
            counts[f"{port}_repeated_exact"] += 1
            counts[f"{port}_repeated_exact_{stage}"] += 1
        if physical in seen and bins in seen[physical] and bins not in seen[key]:
            counts[f"{port}_additional_peer_exact_repeats"] += 1
        seen[key].add(bins)
        seen[physical].add(bins)
        previous[key].update(bins)
        counts[f"{port}_{len(row['starts'])}_frames"] += 1
    counts.update({f"{p}_calls": n for p, n in visits.items()})
    return counts


def audit(work):
    profiles = []
    timings = []
    lock = read(work / "timing-lock.json")
    resources = {}
    for name in trial.CASES:
        cfg = lock["cases"][name]
        prev = trial.prior.read_gzip(
            checked(work / f"{name}-profile.json.gz", cfg["profile_sha256"])
        )
        timing = trial.prior.read_gzip(work / f"{name}-timing.json.gz")
        if (
            timing["timing_lock_sha256"] != _sha(work / "timing-lock.json")
            or timing["case"] != name
        ):
            raise ValueError("timings lost their frozen input and source")
        resources[name] = dict(
            init=timing["init"], peak_rss_kib=timing["peak_rss_kib"], cpu=timing["cpu"]
        )
        iq = {p["visit"]: (p["iq_sha256"], p["cohort"]) for p in prev["rows"]}
        for row in prev["rows"]:
            weights = traffic(row["trace"])
            profiles.append(
                dict(case=name, visit=row["visit"], cohort=row["cohort"], counts=dict(weights))
            )
        if sorted(q["visit"] for q in timing["rows"]) != sorted(cfg["held"] + cfg["stress"]):
            raise ValueError("whole detector omitted a timed visit")
        for i, row in enumerate(timing["rows"]):
            ident = dict(
                case=name, visit=row["visit"], cohort=row["cohort"], iq_sha256=row["iq_sha256"]
            )
            if (row["iq_sha256"], row["cohort"]) != iq[row["visit"]]:
                raise ValueError("full output verification used another physical waveform")
            modes = bench.MODES if row["cohort"] == trial.ONE else ("original", "guard")
            for mode in modes:
                results = row["clocks"][mode]
                if [r["repeat"] for r in results] != list(range(-1, trial.REPEATS)):
                    raise ValueError("timings lost repetitions of the authentic visit")
                for result in results:
                    repeat = result["repeat"]
                    if result["order"] != (modes.index(mode) - i - repeat) % len(modes):
                        raise ValueError("timing order did not follow the frozen interleave")
                    timings.append(
                        dict(
                            **ident,
                            mode=mode,
                            **{k: v for k, v in result.items() if k != "cache_hits"},
                            **{
                                f"{kind}_hits": result["cache_hits"].get(kind, 0)
                                for kind in ("coarse", "fine", "verify")
                            },
                        )
                    )
    return profiles, timings, resources


def analyze(profiles, timings):
    census, summary = {}, {}
    for cohort in (trial.ONE, trial.GUARD):
        population = [r for r in profiles if r["cohort"] == cohort]
        total = Counter()
        for row in population:
            total.update(row["counts"])
        census[cohort] = dict(visits=len(population), **total)
        cl = [r for r in timings if r["cohort"] == cohort and r["repeat"] >= 0]
        ref = {(r["case"], r["visit"], r["repeat"]): r for r in cl if r["mode"] == "original"}
        summary[cohort] = {}
        for mode in sorted({r["mode"] for r in cl}):
            data = [r for r in cl if r["mode"] == mode]
            before = [ref[r["case"], r["visit"], r["repeat"]] for r in data]
            values = [(r["cpu_ns"] - p["cpu_ns"]) * 1e-6 for r, p in zip(data, before, strict=True)]
            ref_cpu = sum(p["cpu_ns"] for p in before)
            summary[cohort][mode] = dict(
                calls=len(data),
                mean_cpu_ms=mean(r["cpu_ns"] for r in data) * 1e-6,
                mean_wall_ms=mean(r["wall_ns"] for r in data) * 1e-6,
                paired_median_cpu_delta_ms=median(values),
                paired_min_cpu_delta_ms=min(values),
                paired_max_cpu_delta_ms=max(values),
                cpu_delta_pct=100 * (sum(r["cpu_ns"] for r in data) / ref_cpu - 1),
                max_retained_bytes=max(r["retained_bytes"] for r in data),
                **{
                    k: sum(r[k] for r in data)
                    for k in (
                        "aperture_hits",
                        "coarse_hits",
                        "fine_hits",
                        "verify_hits",
                        "conditioned_searches",
                        "direct_tie_scores",
                    )
                },
            )
    return census, summary


def render(out, census, summary):
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.1), layout="constrained")
    ports = ("fine", "conditioned", "verify")
    held = census[trial.ONE]
    vals = [[held[f"{p}_calls"] for p in ports], [held[f"{p}_repeated_exact"] for p in ports]]
    x = np.arange(3)
    axes[0].bar(x, vals[0], color="#476285", label="All calls")
    axes[0].bar(x, vals[1], color="#d18c54", label="Repeated exact key")
    axes[0].set_xticks(x, ["Fine grid", "Conditioned\ngrid", "Held score"])
    axes[0].set_title("40 held IQ visits")
    for i, (total, repeat) in enumerate(zip(*vals, strict=True)):
        axes[0].text(i, total + 25, f"{repeat}/{total}", ha="center", fontsize=9)
    for ax, cohort, title, modes in (
        (axes[1], trial.ONE, "20 held benchmark visits", bench.MODES),
        (axes[2], trial.GUARD, "Eight actual recheck witnesses", ("original", "guard")),
    ):
        labels = {"original": "Original", "aperture": "Shared\naperture", "guard": "Guarded\nreuse"}
        palette = {"original": "#476285", "aperture": "#a9755d", "guard": "#47897b"}
        values = [summary[cohort][m]["mean_cpu_ms"] for m in modes]
        ax.bar(np.arange(len(modes)), values, color=[palette[m] for m in modes])
        ax.set_xticks(np.arange(len(modes)), [labels[m] for m in modes])
        ax.set_title(title)
        ax.set_ylabel("Mean complete CPU (ms)")
        ax.set_ylim(0, max(values) * 1.16)
        for i, v in enumerate(values):
            ax.text(i, v + max(values) * 0.023, f"{v:.1f}", ha="center", fontsize=9)
    axes[0].legend(loc="upper left", fontsize=8, frameon=False)
    axes[0].set_ylim(0, max(vals[0]) * 1.18)
    for ax in axes:
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_axisbelow(True)
        ax.grid(axis="y", alpha=0.23)
    fig.suptitle("Exact reuse of original capture refinement work")
    for suf in ("png", "pdf"):
        fig.savefig(out / f"stage.{suf}", dpi=165)
    plt.close(fig)


def complete_guard_census(work):
    paths = read(work / "input-lock.json")["sources"]
    evidence = {}
    for name, filename in (("DS26-0237", "cache.csv"), ("DS29-0082", "coarse.csv")):
        (source,) = (Path(p) for p in paths if Path(p).name == filename)
        checked(source, paths[str(source)])
        totals = Counter()
        with source.open(newline="") as stream:
            for row in csv.DictReader(stream):
                if row["status"] != "processed":
                    continue
                calls, inverses = int(row["calls"]), int(row["inverse_ffts"])
                wide, remainder = divmod(inverses - calls * 104_286, 86_751)
                if remainder or not 0 <= wide <= 2 or calls - wide < 2:
                    raise ValueError("complete coarse ledger changed geometry")
                direct_primary, direct_retry = calls - wide - 2, max(0, wide - 1)
                totals.update(
                    dict(
                        valid_visits=1,
                        rechecked_visits=int(direct_primary + direct_retry > 0),
                        primary_rechecks=direct_primary,
                        retry_rechecks=direct_retry,
                    )
                )
        evidence[name] = dict(totals)
    return evidence


def publish(work):
    out = trial.REPORT
    profiles, timing, resources = audit(work)
    census, summary = analyze(profiles, timing)
    save_json(out / "profile-counts.json", profiles)
    save_json(
        out / "summary.json",
        dict(
            census=census,
            timing=summary,
            resources=resources,
            complete_guard_census=complete_guard_census(work),
        ),
    )
    csv_file(out / "stage.csv", timing)
    render(out, census, summary)
    save_json(
        out / "stage-figure.json",
        dict(
            version=1,
            id="fine-epoch-reuse-stage",
            title="Exact reuse across fine-refinement epochs",
            image="stage.png",
            pdf="stage.pdf",
            csv="stage.csv",
            seal="qualification-lock.json",
            boundary="Resident dual CI16 through complete detector and projection",
            sample="40 new held profiles, 20 timed held visits and eight timed recheck witnesses",
            note="Recheck witnesses are kept separate from held prevalence and cost.",
        ),
    )
    names = [
        "input-lock.json",
        "timing-lock.json",
        *(f"{name}-{tag}.json.gz" for name in trial.CASES for tag in ("profile", "timing")),
    ]
    for name in names:
        shutil.copyfile(work / name, out / name)
    names.extend(
        (
            "profile-counts.json",
            "summary.json",
            "stage.csv",
            "stage.pdf",
            "stage.png",
            "stage-figure.json",
            "PROTOCOL.md",
        )
    )
    save_json(
        out / "qualification-lock.json",
        dict(files={n: _sha(out / n) for n in names}, generator_sha256=_sha(Path(__file__))),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    publish(parser.parse_args().work)
