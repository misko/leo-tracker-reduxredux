"""Publish the original fractional candidate and paired spectrum work ledgers."""

import argparse
import gzip
import json
from pathlib import Path
from statistics import median

from matplotlib import pyplot as plt

from ..__main__ import local_output, save_json, write
from ..scoring import distribution
from . import winner_bound_trial as trial
from .full_v5_check import _sha
from .prefix_figures import csv_file
from .scout_stage_figures import canvas

LABELS = dict(
    integer="Integer-reference energy",
    exact_only="Exact fractional score",
    parseval="Exact minus control mean",
    sparse_control="Exact minus sampled control",
)
CASES = ("all", *trial.CPUS)


def compressed(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def candidate_rows(work, freeze):
    rows = []
    for ident, cfg in freeze["cases"].items():
        visits = compressed(work / f"{ident}.json.gz")
        for trace, fixture in zip(visits, cfg["rows"], strict=True):
            if (trace["visit"], trace["iq_sha256"]) != (fixture["visit"], fixture["iq_sha256"]):
                raise ValueError("candidate observation changed the frozen IQ fixture")
            for attempt, candidates in enumerate(trace["attempts"]):
                for candidate in candidates:
                    item = dict(
                        id=ident,
                        visit=trace["visit"],
                        edge=trace["edge"],
                        attempt=attempt,
                        rank=candidate["rank"],
                        epoch=candidate["epoch"],
                        acquired_cfo_hz=candidate["acquired_cfo_hz"],
                        offset=candidate["offset"],
                        incumbent=candidate["incumbent"],
                        original_margin=candidate.get("margin"),
                        integer_support=candidate.get("integer_disposition"),
                        frames=candidate.get("frames"),
                    )
                    for policy in trial.POLICIES:
                        item[f"{policy}_upper"] = candidate.get("bounds", {}).get(policy)
                        item[f"{policy}_certified"] = candidate.get("skip", {}).get(policy)
                    rows.append(item)
    return rows


def counts(rows):
    report = []
    for ident in CASES:
        all_rows = [r for r in rows if ident == "all" or r["id"] == ident]
        measured = [r for r in all_rows if r["offset"] is not None]
        eligible = [r for r in measured if r["incumbent"] is not None]
        losers = sum(r["original_margin"] < r["incumbent"] for r in eligible)
        unit = sum(r["integer_upper"] == 1.0 for r in measured)
        for policy in trial.POLICIES:
            certified = [r for r in eligible if r[f"{policy}_certified"]]
            bad = sum(r["original_margin"] >= r["incumbent"] for r in certified)
            if bad:
                raise ValueError("a candidate certificate could remove the original margin winner")
            slack = distribution(r[f"{policy}_upper"] - r["original_margin"] for r in measured)
            report.append(
                dict(
                    id=ident,
                    bound=policy,
                    original_ranks=len(all_rows),
                    unbracketed_ranks=len(all_rows) - len(measured),
                    terminal=len(measured),
                    incumbent_eligible=len(eligible),
                    true_losers=losers,
                    certified_losers=len(certified),
                    certified_pct_terminal=100 * len(certified) / len(measured),
                    false_discards=bad,
                    integer_unit_bounds=unit,
                    slack_min=slack["min"],
                    slack_p50=slack["p50"],
                    slack_p95=slack["p95"],
                )
            )
    return report


def spectrum_rows(path, freeze):
    seal = trial.read(path / "spectrum-lock.json")
    if seal["input_lock_sha256"] != _sha(trial.REPORT / "input-lock.json"):
        raise ValueError("paired CPU timings used different IQ")
    rows = []
    for ident, cfg in freeze["cases"].items():
        name = f"{ident}-spectra.json.gz"
        visits = compressed(trial.checked(path / name, seal["files"][name]))
        for visit, fixture in zip(visits, cfg["rows"], strict=True):
            if visit["visit"] != fixture["visit"]:
                raise ValueError("spectrum measurement lost a frozen physical visit")
            for index, attempt in enumerate(visit["attempts"]):
                if len(attempt["samples"]) != seal["repeats"]:
                    raise ValueError("spectrum measurement lacks matched pairs")
                for repeat, sample in enumerate(attempt["samples"]):
                    rows.append(
                        dict(
                            id=ident,
                            visit=visit["visit"],
                            attempt=index,
                            repeat=repeat,
                            cpu_pin=seal["cpu"],
                            original_ranks=attempt["rank_count"],
                            terminal=attempt["fractional_calls"],
                            skipped_control=attempt["skipped"],
                            winner_retained=attempt["winner"] is not None,
                            **{
                                f"{kind}_{key}": value
                                for kind, timings in sample.items()
                                for key, value in timings.items()
                            },
                        )
                    )
    return rows


def timing_summary(rows):
    results = []
    for ident in CASES:
        all_rows = [r for r in rows if ident == "all" or r["id"] == ident]
        for cohort in ("all_attempts", "certified_attempts"):
            group = (
                all_rows
                if cohort == "all_attempts"
                else [r for r in all_rows if r["skipped_control"]]
            )
            if not group:
                continue
            for baseline in ("paired", "split_all"):
                fields = dict(id=ident, cohort=cohort, baseline=baseline, matched_pairs=len(group))
                for clock in ("cpu", "wall"):
                    before = [r[f"{baseline}_{clock}_ns"] for r in group]
                    after = [r[f"split_{clock}_ns"] for r in group]
                    pairs = list(zip(before, after, strict=True))
                    fields.update(
                        {
                            f"baseline_{clock}_p50_ms": median(before) / 1e6,
                            f"split_{clock}_p50_ms": median(after) / 1e6,
                            f"median_paired_{clock}_saving_ms": median(a - b for a, b in pairs)
                            / 1e6,
                            f"median_paired_{clock}_saving_pct": median(
                                100 * (a - b) / a for a, b in pairs
                            ),
                            f"total_{clock}_saving_pct": 100
                            * (sum(before) - sum(after))
                            / sum(before),
                        }
                    )
                results.append(fields)
    return results


def stage_figure(report, stats, times, freeze, files):
    fig, axes = canvas(
        "Bounding the winning fractional GLRT margin",
        "Ten authentic stereo visits · original lower and upper edges",
        "A certificate retains the current passing winner and preserves the any-pass decision. "
        "Spectrum timing starts with resident fractional correlations.",
    )
    pooled = [r for r in stats if r["id"] == "all"]
    for index, row in enumerate(pooled):
        percent = row["certified_pct_terminal"]
        axes[0].barh(index, percent, color=("#6B8291" if index == 0 else "#146C5F"), height=0.56)
        axes[0].text(
            percent + 0.7, index, f"{row['certified_losers']}/{row['terminal']}", va="center"
        )
    axes[0].set(
        title="Certified after an earlier passing winner",
        xlabel="Percent of terminal fractional candidates",
        yticks=range(len(pooled)),
        yticklabels=[LABELS[r["bound"]] for r in pooled],
        xlim=(0, 33),
    )
    axes[0].invert_yaxis()
    controls = (
        ("paired", -0.16, "#456F9C", "Versus original paired FFT"),
        ("split_all", 0.16, "#A96124", "Versus unpruned split FFT"),
    )
    for baseline, offset, color, label in controls:
        overall = [r for r in times if r["cohort"] == "all_attempts" and r["baseline"] == baseline]
        for i, row in enumerate(overall):
            value = row["median_paired_cpu_saving_pct"]
            axes[1].barh(
                i + offset,
                value,
                height=0.25,
                color=color,
                label=label if i == 0 else None,
            )
    axes[1].axvline(0, color="#495B64", linewidth=0.8)
    axes[1].set(
        title="Split exact and control spectra",
        xlabel="Median paired process CPU savings (%)",
        yticks=range(len(overall)),
        yticklabels=[r["id"] for r in overall],
    )
    axes[1].invert_yaxis()
    handles, labels = axes[1].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="lower center",
        bbox_to_anchor=(0.72, 0.125),
        ncol=2,
        frameon=False,
        fontsize=9,
    )
    for ext in ("png", "pdf"):
        fig.savefig(
            report / f"stage.{ext}",
            dpi=160,
            metadata={"CreationDate": None} if ext == "pdf" else {},
        )
    plt.close(fig)
    source_files = (*files, "stage.png", "stage.pdf")
    save_json(
        report / "stage-figure-lock.json",
        dict(cases=list(freeze["cases"]), files={n: _sha(report / n) for n in source_files}),
    )
    save_json(
        report / "stage-figure.json",
        dict(
            version=1,
            id="winner-bound",
            title="Bounding the winning fractional GLRT margin",
            boundary="Original capture candidates and measured fractional spectrum CPU",
            sample="Ten saved stereo visits and matched spectral repeats",
            note="Paired times start with fractional correlations already resident.",
            seal="stage-figure-lock.json",
            image="stage.png",
            pdf="stage.pdf",
            csv="bound-summary.csv",
        ),
    )


def publish(work, spectrum):
    report = trial.REPORT
    path = trial.checked(work / "input-lock.json", _sha(report / "input-lock.json"))
    freeze = trial.read(path)
    for file, sha in freeze["sources"].items():
        trial.checked(Path(file), sha)
    candidate = candidate_rows(work, freeze)
    stats = counts(candidate)
    times = spectrum_rows(spectrum, freeze)
    summary = timing_summary(times)
    for ident in freeze["cases"]:
        number = sum(r["skipped_control"] for r in times if r["id"] == ident and r["repeat"] == 0)
        archived = next(
            r["certified_losers"] for r in stats if r["id"] == ident and r["bound"] == "exact_only"
        )
        if number != archived:
            raise ValueError("timed branch gives a different exact-score pruning decision")
    files = (
        "candidate-audit.csv",
        "bound-summary.csv",
        "spectrum-timing.csv",
        "spectrum-summary.csv",
    )
    for name, values in zip(files, (candidate, stats, times, summary), strict=True):
        csv_file(report / name, values)
    receipts = (
        *(work / f"{ident}.json.gz" for ident in freeze["cases"]),
        *sorted(spectrum.glob("*-spectra.json.gz")),
        spectrum / "spectrum-lock.json",
    )
    names = [str(Path("receipts") / p.name) for p in receipts]
    for src, dst in zip(receipts, names, strict=True):
        write(report / dst, src.read_bytes())
    evidence = ("input-lock.json", "PROTOCOL.md", *files, *names)
    save_json(
        report / "evidence-lock.json",
        dict(
            cases=list(freeze["cases"]),
            files={name: _sha(report / name) for name in evidence},
            exporter_sha256=_sha(Path(__file__)),
        ),
    )
    stage_figure(report, stats, summary, freeze, (*files, "evidence-lock.json"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("spectrum", type=local_output)
    args = parser.parse_args()
    publish(args.work, args.spectrum)
