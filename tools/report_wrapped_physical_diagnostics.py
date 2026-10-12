"""Retain bounded physical-model diagnostics without promoting frequency gains."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np

from leo.analysis.wrapped_glrt_likelihood import WrappedConfig, nuisance_design, wrapped_ratios
from tools.evaluate_sparse_glrt import local_output, write_json
from tools.evaluate_wrapped_fast_scan import load_bundle, load_phase_bank, phase_provider
from tools.report_glrt_relative_phase import surface_summary


def replay_endpoint(data, rf, prediction, opportunity, fit, config):
    """Rebuild the density and charged priors from saved parameters."""
    design, _, span = nuisance_design(
        data,
        rf,
        coefficient=fit["coefficient_enabled"],
        band_drift=config.band_drift_sigma_hz_s is not None,
    )
    weights = np.asarray(fit["weights"])
    if (
        weights.shape != (len(fit["active"]) + 1,)
        or (weights < 0).any()
        or not np.isclose(weights.sum(), 1, atol=1e-9, rtol=0)
    ):
        raise ValueError("endpoint activity weights are not normalized")
    ratios = wrapped_ratios(data, prediction, opportunity, design, fit["beta"], config)
    raw = float(np.log(weights[0] + ratios @ weights[1:]).sum())
    groups = int(data.group.max()) + 1
    beta = np.asarray(fit["beta"])
    prior = 0.5 * np.sum(
        (beta[groups : groups + groups // 2] / span / config.drift_sigma_hz_s) ** 2
    )
    if config.band_drift_sigma_hz_s is not None:
        prior += 0.5 * np.sum(
            (beta[groups + groups // 2 : 2 * groups] / span / config.band_drift_sigma_hz_s) ** 2
        )
    if fit["coefficient_enabled"]:
        prior += 0.5 * (beta[-1] / config.coefficient_sigma_hz_ghz) ** 2
    prior += 0.5 * (fit["phase_s"] / config.common_phase_sigma_s) ** 2
    if config.relative_phase_sigma_s is not None:
        prior += 0.5 * np.sum(
            (np.asarray(fit["satellite_phase_s"]) / config.relative_phase_sigma_s) ** 2
        )
    score = raw - prior - config.satellite_penalty * len(fit["active"])
    if not np.isclose(raw, fit["log_ratio"], atol=1e-6, rtol=0) or not np.isclose(
        score, fit["score"], atol=1e-6, rtol=0
    ):
        raise ValueError("saved endpoint density or prior accounting does not replay")
    return dict(log_ratio=raw, score=float(score), nuisance_prior_cost=float(prior))


def paired_summary(base, alternative, base_rows, alternative_rows):
    for key in (
        "input_digest",
        "orbit_digest",
        "candidate_norad",
        "seeds",
        "site",
        "phase_receipt",
        "candidate_pool_digest",
        "random_seed",
        "search_plan",
    ):
        if base[key] != alternative[key]:
            raise ValueError("diagnostic evidence, pool or starting states differ")
    base_config = dict(base["config"])
    alternative_config = dict(alternative["config"])
    # This report compares either this added nuisance or the orbital frame.
    base_config.pop("band_drift_sigma_hz_s", None)
    alternative_config.pop("band_drift_sigma_hz_s", None)
    if base_config != alternative_config:
        raise ValueError("paired diagnostic priors or iteration budgets differ")

    def keys(rows):
        return {(r["east_m"], r["north_m"]) for r in rows}

    if keys(base_rows) != keys(alternative_rows):
        raise ValueError("paired diagnostic locations differ")
    rows = []
    for arm in ("zero-c", "fitted-c"):
        reference = [r for r in base_rows if (r["east_m"], r["north_m"]) == (0.0, 0.0)][0]
        other_reference = [
            r for r in alternative_rows if (r["east_m"], r["north_m"]) == (0.0, 0.0)
        ][0]
        best = max(base_rows, key=lambda r: r["arms"][arm]["score"])
        other_best = max(alternative_rows, key=lambda r: r["arms"][arm]["score"])
        rows.append(
            dict(
                arm=arm,
                reference_gain=other_reference["arms"][arm]["score"]
                - reference["arms"][arm]["score"],
                base_best_distance_m=best["distance_m"],
                alternative_best_distance_m=other_best["distance_m"],
                base_reference_gap=best["arms"][arm]["score"] - reference["arms"][arm]["score"],
                alternative_reference_gap=other_best["arms"][arm]["score"]
                - other_reference["arms"][arm]["score"],
            )
        )
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--full-surface-directory", default="fixed-frame-full-v2")
    args = p.parse_args()
    local_output(args.output)
    args.output.mkdir(parents=True, exist_ok=True)
    summaries = []
    for session in (
        "fast-bf660cb5200c4a27c3a2181a6dfc7132",
        "fast-862e4fbdc0d1b5b03a0ef5e12422eaf0",
    ):
        root = args.data_root / session
        folders = (
            "band-drift-restricted-probe-v1",
            "band-drift-expanded-probe-v1",
            "inertial-phase-probe-v1",
            "fixed-frame-local-v1",
        )
        results = {}
        rows = {}
        for folder in folders:
            source = root / folder
            results[folder] = json.loads((source / "result.json").read_text())
            rows[folder] = [
                json.loads(line) for line in (source / "evaluations.jsonl").read_text().splitlines()
            ]
            destination = args.output / session / folder
            destination.mkdir(parents=True, exist_ok=True)
            for filename in ("result.json", "protocol.json", "evaluations.jsonl"):
                shutil.copyfile(source / filename, destination / filename)
        for variant, folder in [
            ("band drift", "band-drift-expanded-probe-v1"),
            ("fixed reception frame", "inertial-phase-probe-v1"),
        ]:
            base = "band-drift-restricted-probe-v1"
            summary = paired_summary(results[base], results[folder], rows[base], rows[folder])
            summaries.extend(dict(r, session=session, variant=variant) for r in summary)
    write_json(args.output / "paired-comparison.json", summaries)
    diagnostic_files = (
        "development-band-drift-profile.json",
        "development-clock-shape-profiles.json",
        "development-satellite-bias-profiles.json",
        "development-height-profile.json",
        "past-tle-consistency-profile.json",
        "past-tle-aligned-frequency-profile.json",
        "cohort-common-grid-sum.json",
        "cohort-envelope-common-grid.json",
        "band-drift-development-protocol.json",
        "development-phase-age-consistency.json",
        "cross-provider-latest-inventory.json",
    )
    for name in diagnostic_files:
        shutil.copyfile(args.data_root / name, args.output / name)
    panel = json.loads((args.data_root / "panel.json").read_text())
    full_surfaces = []
    for row in panel["rows"]:
        source = args.data_root / row["session_id"] / "fixed-frame-validation-probe-v1"
        if row["split"] == "validation" and (source / "result.json").exists():
            shutil.copytree(
                source,
                args.output / row["session_id"] / "retrospective-fixed-frame-probe",
                dirs_exist_ok=True,
            )
        source = args.data_root / row["session_id"] / args.full_surface_directory
        if (source / "result.json").exists():
            result = json.loads((source / "result.json").read_text())
            evaluations = [
                json.loads(line) for line in (source / "evaluations.jsonl").read_text().splitlines()
            ]
            if result["phase_model"] != "fixed-reception-frame-orbital-phase":
                raise ValueError("fixed-reception-frame surface required")
            data, bank, meta, _ = load_bundle(args.data_root / row["session_id"] / "bundle")
            if (
                result["input_digest"] != meta["input_sha256"]
                or result["orbit_digest"] != meta["orbit_bank_sha256"]
            ):
                raise ValueError("full surface evidence does not match the recording")
            phases, receipt = load_phase_bank(args.data_root / row["session_id"] / "bundle", bank)
            if receipt != result["phase_receipt"]:
                raise ValueError("full surface phase-bank provenance changed")
            lookup = {int(n): i for i, n in enumerate(bank["norad"])}
            pool = np.asarray([lookup[int(n)] for n in result["candidate_norad"]])
            for evaluation in evaluations:
                provider = phase_provider(
                    phases,
                    bank,
                    data,
                    meta["site"],
                    (evaluation["east_m"], evaluation["north_m"]),
                    inertial_phase=True,
                )
                for fit in evaluation["arms"].values():
                    active = np.asarray(fit["active"], dtype=int)
                    delta = np.asarray(fit["satellite_phase_s"])[active]
                    if active.size:
                        prediction, opportunity, _, _ = provider.predict(
                            fit["phase_s"] + delta, pool[active]
                        )
                    else:
                        prediction = opportunity = np.empty((len(data.ids), 0))
                    replay_endpoint(
                        data,
                        bank["rf_hz"],
                        prediction,
                        opportunity,
                        fit,
                        WrappedConfig(**result["config"]),
                    )
            destination = args.output / row["session_id"] / args.full_surface_directory
            destination.mkdir(parents=True, exist_ok=True)
            for name in ("result.json", "protocol.json", "evaluations.jsonl"):
                shutil.copyfile(source / name, destination / name)
            full_surfaces.append(
                dict(
                    row,
                    arms={
                        arm: surface_summary(result, evaluations, arm)
                        for arm in ("zero-c", "fitted-c")
                    },
                )
            )
        else:
            full_surfaces.append(dict(row, status="not evaluated; original cohort retained"))
    write_json(
        args.output / "fixed-frame-full-summary.json",
        dict(
            rows=full_surfaces,
            validation_denominator=4,
            scope="Retrospective physical-model diagnostics; no fresh validation claim",
        ),
    )
    manifest = {}
    for source in [
        Path(__file__),
        Path("src/leo/analysis/glrt_orbit_phase.py"),
        Path("src/leo/analysis/wrapped_glrt_likelihood.py"),
        Path("tools/evaluate_wrapped_fast_scan.py"),
    ]:
        manifest[str(source)] = hashlib.sha256(source.read_bytes()).hexdigest()
    write_json(args.output / "publication-source-digests.json", manifest)

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
    labels = [r["session"][5:13] + " / " + r["variant"] for r in summaries[::2]]
    for j, arm in enumerate(("zero-c", "fitted-c")):
        selected = [r for r in summaries if r["arm"] == arm]
        x = np.arange(len(selected)) + (j - 0.5) * 0.35
        axes[0].bar(x, [r["reference_gain"] for r in selected], 0.35, label=arm)
        axes[1].bar(
            x,
            [r["alternative_reference_gap"] - r["base_reference_gap"] for r in selected],
            0.35,
            label=arm,
        )
    for ax in axes:
        ax.set_xticks(np.arange(len(labels)), labels, rotation=25, ha="right")
        ax.axhline(0, color="black", linewidth=0.8)
        ax.legend()
    axes[0].set(
        title="Frequency score change at fixed reference", ylabel="Alternative minus baseline"
    )
    axes[1].set(
        title="Reference gap on identical seven-point probes",
        ylabel="Alternative gap minus baseline gap (lower better)",
    )
    fig.savefig(args.output / "physical-model-comparison.png", dpi=160)
    plt.close(fig)
    forecasts = json.loads((args.output / "past-tle-aligned-frequency-profile.json").read_text())[
        "rows"
    ]
    fig, ax = plt.subplots(figsize=(10, 4.5), constrained_layout=True)
    ax.bar(np.arange(len(forecasts)), [r["after_constant_drift_timing_rms_hz"] for r in forecasts])
    ax.set_xticks(np.arange(len(forecasts)), [str(r["norad"]) for r in forecasts], rotation=65)
    ax.set(
        ylabel="Residual frequency RMS (Hz)",
        title="Past forecast disagreement after constant, drift and timing removal\n"
        "Consistency proxy; not measured error of the newest orbit",
    )
    fig.savefig(args.output / "past-forecast-shape-disagreement.png", dpi=160)
    plt.close(fig)
    measured = [row for row in full_surfaces if "arms" in row]
    if measured:
        fig, axes = plt.subplots(
            len(measured),
            2,
            figsize=(11, 4 * len(measured)),
            squeeze=False,
            constrained_layout=True,
        )
        for i, row in enumerate(measured):
            path = (
                args.output / row["session_id"] / args.full_surface_directory / "evaluations.jsonl"
            )
            evaluations = [json.loads(line) for line in path.read_text().splitlines()]
            for j, arm in enumerate(("zero-c", "fitted-c")):
                ax, summary = axes[i, j], row["arms"][arm]
                scatter = ax.scatter(
                    [r["east_m"] / 1000 for r in evaluations],
                    [r["north_m"] / 1000 for r in evaluations],
                    c=[summary["best_score"] - r["arms"][arm]["score"] for r in evaluations],
                    cmap="viridis_r",
                    vmin=0,
                    vmax=100,
                )
                ax.scatter(0, 0, marker="*", s=150, color="red", label="configured reference")
                ax.scatter(
                    summary["best_east_m"] / 1000,
                    summary["best_north_m"] / 1000,
                    marker="x",
                    s=80,
                    color="black",
                    label="best sampled point",
                )
                ax.set(
                    xlabel="East (km)",
                    ylabel="North (km)",
                    xlim=(-5.2, 5.2),
                    ylim=(-5.2, 5.2),
                    aspect="equal",
                    title=f"{row['session_id'][5:13]} / {arm}; "
                    f"{'completed' if summary['completed'] else 'incomplete'}\n"
                    f"best {summary['best_distance_m'] / 1000:.2f} km; "
                    f"gap {summary['reference_score_gap']:.2f}",
                )
                ax.legend(fontsize=7)
                fig.colorbar(scatter, ax=ax, label="Loss above best (clipped at 100)")
        fig.suptitle("Fixed reception frame: measured 5 km surfaces; no interpolated minimum")
        fig.savefig(args.output / "fixed-frame-full-surfaces.png", dpi=160)
        plt.close(fig)
    for path in args.output.rglob("*.json"):
        path.write_text(
            json.dumps(json.loads(path.read_text()), separators=(",", ":"), allow_nan=False) + "\n"
        )
    print(json.dumps(dict(paired_rows=len(summaries), past_forecast_pairs=len(forecasts))))


if __name__ == "__main__":
    main()
