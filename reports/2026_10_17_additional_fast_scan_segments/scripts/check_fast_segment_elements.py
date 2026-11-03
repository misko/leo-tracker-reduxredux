"""Conditional independent-element check; fixed observations and calibration."""

import argparse
import json
import time
from pathlib import Path

import numpy as np
from investigate_fast_scan_segments import grouped_folds, search_candidates

from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_bank import build_regional_bank
from leo.analysis.regional_position_bootstrap import observation_subset
from leo.application.shared_fast_position import prepare_views
from leo.cli.shared_fast_position import load_input
from leo.contracts.regional_position import RegionalPrior
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets
from leo.storage.shared_fast_scan import SharedFastScanStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plot-only", action="store_true")
    args = parser.parse_args()
    started = time.monotonic()
    summary = json.loads((args.output / "summary.json").read_bytes())
    baseline = np.load(args.output / "baseline.npz")
    store = SharedFastScanStore("/srv/bulk/leo", "shared-scan-q-v2")
    _, doc, terminal, _ = store.plot_evidence("075b34f9532dd9f7caf6c70830e4e8e8")
    source = load_input(doc)
    prepared, _ = prepare_views(source)
    obs = prepared["all"].observations
    np.testing.assert_allclose(obs.times_s, baseline["times_s"], atol=0, rtol=0)
    prior = RegionalPrior(**terminal["provenance"]["prior"])
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    cutoff = prepared["all"].start_utc_ns - 505_000_000_000
    snapshots = archive.list_snapshots()
    providers = sorted({s.provider for s in snapshots})
    print("providers", providers, flush=True)
    alternatives = [
        s
        for s in snapshots
        if s.collected_utc_ns < cutoff and s.provider != summary["snapshot_provider"]
    ]
    if not alternatives:
        raise ValueError("No causal independent-provider snapshot")
    snapshot = max(alternatives, key=lambda s: s.collected_utc_ns)
    payload, _ = exclude_labelled_starlink_debris(archive.read(snapshot))
    cat = parse_element_sets(payload)
    lookup = {int(n): i for i, n in enumerate(cat.satellite_numbers)}
    numbers = [n for n in summary["full_candidate_numbers"] if n in lookup]
    bank, _ = build_regional_bank(
        cat,
        [lookup[n] for n in numbers],
        prepared["all"].start_utc_ns,
        obs,
        prior,
        maximum_seconds=60,
    )
    grid = np.linspace(-5, 5, 201)
    result = dict(
        snapshot_provider=snapshot.provider,
        snapshot_sha256=snapshot.digest,
        collected_utc_ns=snapshot.collected_utc_ns,
        candidate_count=len(bank.numbers),
        missing_from_catalogue=sorted(set(summary["full_candidate_numbers"]) - set(numbers)),
        note="Frozen production position/calibration. Provider comparison includes any "
        "horizon-screen changes; no new position or calibration optimization.",
        targets=[],
    )
    if args.plot_only:
        result = json.loads((args.output / "independent-elements.json").read_bytes())
    epochs = cat.element_epoch_utc_ns()
    for target in [] if args.plot_only else summary["targets"]:
        rows = np.asarray(target["coherent_rows"], int)
        sub = observation_subset(obs, rows)
        predictions, visibility = [], []
        for shift in grid:
            values, visible, _, _ = predict_orbits(
                bank,
                sub,
                prior,
                baseline["vector"][:2],
                np.full(len(bank.numbers), shift),
                derivatives=False,
            )
            predictions.append(values)
            visibility.append(visible)
        predictions, visibility = np.asarray(predictions), np.asarray(visibility)
        folds = grouped_folds(sub.times_s)
        record = dict(label=target["label"], folds=[])
        for fold in (-1, 0, 1, 2, 3, 4):
            train = np.ones(len(rows), bool) if fold == -1 else folds != fold
            ranked = search_candidates(
                predictions,
                visibility,
                baseline["calibrated_hz"][rows],
                grid,
                train,
                allow_offset=False,
            )
            for r in ranked:
                n = int(bank.numbers[r.pop("index")])
                r.update(
                    satellite=n,
                    epoch_utc_ns=int(epochs[lookup[n]]),
                    epoch_age_hours=float(
                        (prepared["all"].start_utc_ns - epochs[lookup[n]]) / 3.6e12
                    ),
                )
            record["folds"].append(dict(fold=fold, ranked=ranked))
        result["targets"].append(record)
        print(
            json.dumps(
                dict(
                    label=target["label"],
                    best=record["folds"][0]["ranked"][:2],
                    cv=[f["ranked"][0] for f in record["folds"][1:]],
                )
            ),
            flush=True,
        )
    if not args.plot_only:
        result["elapsed_s"] = time.monotonic() - started
        (args.output / "independent-elements.json").write_text(json.dumps(result, indent=2) + "\n")

    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    from leo.analysis.regional_position_score import circular

    original_snapshot = next(s for s in snapshots if s.digest == summary["snapshot_sha256"])
    original_payload, _ = exclude_labelled_starlink_debris(archive.read(original_snapshot))
    original_cat = parse_element_sets(original_payload)
    original_lookup = {int(n): i for i, n in enumerate(original_cat.satellite_numbers)}
    best_numbers = [
        t["searches"][0]["folds"][0]["ranked"][0]["satellite"] for t in summary["targets"]
    ]
    original_bank, _ = build_regional_bank(
        original_cat,
        [original_lookup[n] for n in best_numbers],
        prepared["all"].start_utc_ns,
        obs,
        prior,
        maximum_seconds=60,
    )
    figure = Figure(figsize=(15, 10), layout="constrained")
    FigureCanvasAgg(figure)
    axes = figure.subplots(3, 2)
    for target, independent, (left, right) in zip(
        summary["targets"], result["targets"], axes, strict=True
    ):
        rows = np.asarray(target["interval_rows"], int)
        coherent = np.asarray(target["coherent_rows"], int)
        selected = np.isin(rows, coherent)
        sub = observation_subset(obs, rows)
        y = baseline["calibrated_hz"][rows]
        fit = target["searches"][0]["folds"][0]["ranked"][0]
        alt = independent["folds"][0]["ranked"][0]
        n = fit["satellite"]
        one = original_bank.select([list(original_bank.numbers).index(n)])
        value = predict_orbits(
            one, sub, prior, baseline["vector"][:2], np.array([fit["timing_s"]]), derivatives=False
        )[0][:, 0]
        alt_one = bank.select([list(bank.numbers).index(alt["satellite"])])
        alt_value = predict_orbits(
            alt_one,
            sub,
            prior,
            baseline["vector"][:2],
            np.array([alt["timing_s"]]),
            derivatives=False,
        )[0][:, 0]
        left.scatter(
            sub.times_s, circular(y) / 1000, s=18, color="0.7", label="All interval observations"
        )
        left.scatter(
            sub.times_s[selected],
            circular(y[selected]) / 1000,
            s=25,
            color="black",
            label="Fixed coherent subset",
        )
        for pred, color, label in (
            (value, "#0057b8", "Hugging Face target match"),
            (alt_value, "#d95f02", "Space-Track target match"),
        ):
            wrapped = circular(pred) / 1000
            wrapped[np.r_[False, abs(np.diff(wrapped)) > 100]] = np.nan
            left.plot(sub.times_s, wrapped, lw=1.5, color=color, label=label)
            right.scatter(
                sub.times_s[selected],
                circular(y[selected] - pred[selected]),
                s=18,
                color=color,
                label=label,
            )
        if n in list(baseline["numbers"]):
            k = list(baseline["numbers"]).index(n)
            old = predict_orbits(
                one,
                sub,
                prior,
                baseline["vector"][:2],
                baseline["shifts_s"][k : k + 1],
                derivatives=False,
            )[0][:, 0]
            wrapped = circular(old) / 1000
            wrapped[np.r_[False, abs(np.diff(wrapped)) > 100]] = np.nan
            left.plot(
                sub.times_s,
                wrapped,
                "--",
                lw=1.2,
                color="#b2182b",
                label="Published timing for candidate",
            )
        right.axhline(0, color="0.4", lw=0.6)
        right.axhline(375, color="0.6", lw=0.7, ls=":")
        right.axhline(-375, color="0.6", lw=0.7, ls=":")
        left.set(title=f"{target['label']} · candidate {n}", ylabel="Wrapped calibrated CFO (kHz)")
        right.set(
            title=f"Fixed {len(coherent)}-point subset · conditional residuals",
            ylabel="Measured − prediction (Hz)",
        )
        for axis in (left, right):
            axis.grid(alpha=0.18)
            axis.set_xlim(*target["interval_s"])
    for axis in axes[-1]:
        axis.set_xlabel("Receive time since capture start (s)")
    axes[0, 0].legend(fontsize=8)
    axes[0, 1].legend(fontsize=8)
    figure.suptitle(
        "Additional three segments · frozen production position and calibration\n"
        "Target-only timing proposals; no position refit or confirmed identities",
        fontsize=13,
    )
    figure.savefig(args.output / "candidate-matches.png", dpi=150)


if __name__ == "__main__":
    main()
