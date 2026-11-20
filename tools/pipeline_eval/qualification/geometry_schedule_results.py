"""Validate withheld-window forecast scores and score the frozen acquisition replay."""

import argparse
from collections import Counter
from pathlib import Path
from statistics import mean
from unittest.mock import patch

import matplotlib.pyplot as plt

from .. import whole_iq
from ..__main__ import local_output, save_json
from ..scoring import ARMS, ROLES, distribution
from . import adaptive_visits_results as previous
from . import geometry_schedule_trial as trial
from . import study_benchmark
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file

REPORT = trial.REPORT
MODES = (*trial.MODES, "fast", "original")
METHODS = tuple(f"geometry_schedule_{mode}" for mode in MODES)
LABELS = ("Geographic information", "Matched hash", "Full fast", "Full original")
COLORS = ("#795878", "#2b6c77")
fixed = trial.base.fixed


def measurements(source, witnesses):
    metrics = []
    for ident, case in source["cases"].items():
        slots = whole_iq.read(
            whole_iq.checked(REPORT / "slots" / (ident + ".json"), case["slots_sha256"])
        )
        windows = []
        for mode in trial.MODES:
            selected = [row for row in witnesses[ident, mode] if row["rx"] == 0]
            expected = slots[mode]
            if any(
                any(actual[k] != value for k, value in target.items())
                for actual, target in zip(selected, expected, strict=True)
            ):
                raise ValueError("a held measurement witness changes a locked geometry decision")
            windows.append(Counter((r["rf_hz"], r["token"]) for r in expected))
            metrics.append(
                dict(
                    id=ident,
                    mode=mode,
                    sampled_calls=len(selected),
                    foreseen=sum(r["gain"] > 0 for r in selected),
                    high_gain_triggers=sum(r["trigger"] == "novelty" for r in selected),
                    supported=sum(r["supported"] for r in selected),
                    favors_nominal=sum(r["gauge"] > 0 for r in selected),
                    favors_shifted=sum(r["gauge"] < 0 for r in selected),
                    mean_projected_gain=mean(r["gain"] for r in selected),
                    mean_held_advantage_hz=mean(r["gauge"] for r in selected),
                    mean_assignment_mass=mean(r["posterior_mass"] for r in selected),
                    selector_cpu_s=case["selector"]["total_selector_cpu_s"],
                    selector_wall_s=case["selector"]["total_selector_wall_s"],
                    tles_cpu_s=case["selector"]["orbit_prepare_cpu_s"],
                    association_projection_cpu_s=case["selector"]["cpu_s"],
                    association_projection_wall_s=case["selector"]["wall_s"],
                    block_rf_forecasts=case["selector"]["predicted_rf_blocks"],
                    tracked_hypotheses=case["selector"]["tracked_hypotheses"],
                )
            )
        if windows[0] != windows[1] or any(n != 1 for n in windows[0].values()):
            raise ValueError("RF/token budget changed between geometry and null")
    return metrics


def original_validation(source):
    """Check original Doppler at the already sealed slots under both offer forecasts."""
    _, archives, _, extensions, release = trial.base.roster.inventory()
    if release != source["release"]:
        raise ValueError("original validation requires the same archived compact release")
    rule = whole_iq.read(REPORT / "rule-lock.json")
    index = trial.QUANTILES.index(rule["chosen"]["quantile"])
    output = []
    for ident, case in source["cases"].items():
        fast, features, forecasts, work = trial.prepare(ident, archives, extensions)
        if work["snapshot_sha256"] != case["selector"]["snapshot_sha256"]:
            raise ValueError("original validation used different causal elements")
        path = whole_iq.checked(REPORT / "slots" / (ident + ".json"), case["slots_sha256"])
        slots = whole_iq.read(path)
        if trial.choices(fast, features, index) != slots:
            raise ValueError("original validation must reproduce the signal-only slot seal")
        known = {key: case[key] for key in fixed.BINDINGS}
        _, _, _, _, original, _ = trial.base.paired.bind(
            ident, archives, {ident: known}, extensions
        )
        trial.model.visits.same_support(fast, original)
        for mode in trial.MODES:
            estimates = trial.model.check_selected(original, forecasts, slots[mode])
            output.append(
                dict(
                    id=ident,
                    mode=mode,
                    scheduled=len(estimates),
                    supported=sum(r["supported"] for r in estimates),
                    favors_nominal=sum(r["gauge"] > 0 for r in estimates),
                    favors_shifted=sum(r["gauge"] < 0 for r in estimates),
                    mean_held_advantage_hz=mean(r["gauge"] for r in estimates),
                )
            )
    return output


def plot(rows):
    ids = list(dict.fromkeys(r["id"] for r in rows))
    fig, axes = plt.subplots(2, 1, figsize=(11.7, 7), layout="constrained")
    for i, mode in enumerate(trial.MODES):
        values = [r for r in rows if r["mode"] == mode]
        x = [n + (i - 0.5) * 0.4 for n in range(len(ids))]
        axes[0].bar(
            x,
            [r["mean_held_advantage_hz"] for r in values],
            width=0.39,
            color=COLORS[i],
            label=LABELS[i],
        )
    axes[0].set(
        title="Held Doppler forecast at the nominal and 30 km east offers",
        ylabel="Mean nominal advantage (Hz)",
    )
    axes[0].axhline(0, color="#333333", lw=0.9)
    a, b = axes[0].get_legend_handles_labels()
    fig.legend(a, b, loc="outside upper center", ncols=2, frameon=False)
    geometry = [r for r in rows if r["mode"] == "geometry"]
    tles = [r["tles_cpu_s"] for r in geometry]
    assoc = [r["association_projection_cpu_s"] for r in geometry]
    axes[1].bar(range(len(ids)), tles, label="Causal catalogue and orbit bank", color="#726d85")
    axes[1].bar(
        range(len(ids)), assoc, bottom=tles, label="Association and projection", color="#90a584"
    )
    axes[1].scatter(
        range(len(ids)),
        [r["selector_wall_s"] for r in geometry],
        color="#222222",
        marker="_",
        s=130,
        label="Total selector wall",
    )
    axes[1].set(title="Measured selector work on parsed fast factors", ylabel="Seconds")
    axes[1].legend(loc="upper right")
    for ax in axes:
        ax.set(xticks=range(len(ids)), xticklabels=ids, axisbelow=True)
        ax.grid(axis="y", alpha=0.25)
    fig.savefig(REPORT / "stage.png", dpi=160)
    fig.savefig(REPORT / "stage.pdf", metadata=dict(CreationDate=None, ModDate=None))
    plt.close(fig)


def publish(work):
    source = whole_iq.read(
        whole_iq.checked(
            REPORT / "source-lock.json", whole_iq.read(work / "source-lock.json")["sha256"]
        )
    )
    whole_iq.checked(REPORT / "rule-lock.json", source["rule_lock_sha256"])
    with patch.object(previous, "REPORT", REPORT), patch.object(previous, "MODES", MODES):
        outcomes, witnesses = previous.route_rows(work, source)
    outcomes = [dict(row, method=f"geometry_schedule_{row['condition']}") for row in outcomes]
    pack(REPORT / "predictions.jsonl.gz", outcomes)
    prior = whole_iq.read(REPORT / "prediction-lock.json")
    prior["files"]["predictions.jsonl.gz"] = _sha(REPORT / "predictions.jsonl.gz")
    prior["exporter_sha256"] = _sha(Path(__file__))
    save_json(REPORT / "prediction-lock.json", prior)
    records = measurements(source, witnesses)
    csv_file(REPORT / "stage.csv", records)
    csv_file(REPORT / "original-forecast.csv", original_validation(source))
    with patch.object(previous.trial, "MODES", trial.MODES):
        csv_file(REPORT / "modeled-detector.csv", previous.costs(source, witnesses))
    plot(records)
    descriptor = dict(
        version=1,
        id="geometry-schedule-forecast",
        title="Predicted geographic gain and held forecast",
        sample="Six held recordings with matched RF and token windows",
        boundary="Previous-block causal orbit forecast and next-block measured fast CFO",
        note=(
            "Missing forecasts and fast winners keep their full-call denominator. "
            "Detector and compact timings have separate tables."
        ),
        seal="stage-lock.json",
        image="stage.png",
        csv="stage.csv",
        pdf="stage.pdf",
    )
    save_json(REPORT / "stage-figure.json", descriptor)
    stage_assets = (
        "stage-figure.json",
        "stage.png",
        "stage.pdf",
        "stage.csv",
        "modeled-detector.csv",
        "original-forecast.csv",
    )
    save_json(REPORT / "stage-lock.json", dict(files={n: _sha(REPORT / n) for n in stage_assets}))
    ids = sorted(source["cases"])
    with patch.object(previous.previous, "REPORT", REPORT):
        refs, roof = previous.previous.references(ids)
    scores = fixed.scored(outcomes, refs)
    csv_file(REPORT / "scores.csv", scores)
    summary = []
    for arm in ARMS:
        for method in METHODS:
            arms = [r for r in scores if r["method"] == method and r["arm"] == arm]
            counts = Counter(r["status"] for r in arms)
            rf = distribution(r["rf_rms_hz"] for r in arms)
            summary.append(
                dict(
                    fixed.summary_row(arms, ids, "held", arm, method),
                    timed_out=counts["timed_out"],
                    failed=counts["failed"],
                    withheld=counts["withheld"],
                    rf_n=rf["n"],
                    rf_p50_hz=rf["p50"],
                    rf_p95_hz=rf["p95"],
                )
            )
    csv_file(REPORT / "summary.csv", summary)
    csv_file(
        REPORT / "v5-references.csv",
        [
            dict(
                id=ident,
                role=role,
                arm=arm,
                status=item["status"],
                error_km=item["error_km"],
                rf_rms_hz=item.get("rf_rms_hz"),
            )
            for ident in ids
            for role in ROLES
            for arm in ARMS
            if (item := refs[ident]["reference"][role][arm])
        ],
    )
    page = dict(
        id="geometry-schedule-held",
        method=METHODS[0],
        scope="roof",
        cases="sealed",
        title="Spend original detector calls on forecast geographic information",
        caption=(
            "Six measured recordings with matched physical RF/token windows. "
            "Held compact factors come from the scheduled archived original visits."
        ),
        seal="figure-lock.json",
        provenance=["prediction-lock.json", "summary.csv", "fit-resources.csv"],
        roof_references=roof,
        series=[
            dict(
                key=key,
                label=label,
                file="predictions.jsonl.gz",
                value=method,
                native_field="paired_capture_sha256",
                match=list(fixed.BINDINGS),
            )
            for key, label, method in zip(
                ("one", "stock", "one_native_factors", "all_visits"), LABELS, METHODS, strict=True
            )
        ],
    )
    save_json(REPORT / "figures.json", dict(version=2, charts=[page]))
    files = (
        "figures.json",
        "predictions.jsonl.gz",
        "prediction-lock.json",
        "scores.csv",
        "summary.csv",
        "stage-lock.json",
        "fit-resources.csv",
        "v5-references.csv",
        *roof.values(),
    )
    save_json(
        REPORT / "figure-lock.json",
        dict(cases=ids, files={name: _sha(REPORT / name) for name in files}),
    )
    study_benchmark.run(REPORT, REPORT)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=local_output, required=True)
    publish(parser.parse_args().work)
