"""Postfit-only evaluation of structured orbital and residual alternatives."""

import argparse
import csv
import hashlib
import json

import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import ROOT, Scan
from dsx01_joint_exact_mean import exact_conditional_frequency
from dsx01_robust_joint import RobustJoint
from dsx01_structured_joint import StructuredJoint, covariance_whitener
from localize_merged_track_catalogue import distance_km
from prototype_dsx01_remeasured_position import apply_measurements
from report_dsx01_joint_marginal import EvaluationAdapter
from report_dsx01_model_iterations import REFERENCE, nominated_metrics
from run_dsx01_clock_transfer import measurement_path
from run_dsx01_joint_marginal import OUTPUT as BASE
from run_dsx01_robust_empirical import RobustEmpirical
from run_dsx01_structured_joint import OUTPUT

matplotlib.use("Agg")
import matplotlib.pyplot as plt

CASES = tuple(f"DSX01-S0{k}" for k in range(1, 6))
VARIANTS = ("baseline", "learned", "eccentric", "colored", "eccentric_colored")


def records(case, variant):
    if variant == "identity":
        path = ROOT / "reports/2026_10_18_dsx01_integrated_labels" / case / "selected.json"
        if not path.exists():
            raise ValueError(f"no completed label-update selection: {case}")
        return path, [dict(iteration=0, fits=json.loads(path.read_text())["fits"])]
    path = (
        BASE / case / "robust/rounds.json"
        if variant == "baseline"
        else BASE / "robust_empirical" / case / "empirical/rounds.json"
        if variant == "learned"
        else OUTPUT / case / variant / "rounds.json"
    )
    data = json.loads(path.read_text())
    if len(data) != 3 or any(len(row["fits"]) != 2 for row in data):
        raise ValueError(f"incomplete three-round comparison: {case}/{variant}")
    return path, data


def problem_for(scan, fit, variant):
    cls = (
        RobustJoint
        if variant in ("baseline", "identity")
        else RobustEmpirical
        if variant == "learned"
        else StructuredJoint
    )
    configuration = (
        "robust"
        if variant in ("baseline", "identity")
        else "empirical"
        if variant == "learned"
        else variant
    )
    return cls(
        scan,
        dict(rows=fit["rows"], state=fit["state"]),
        len(fit["state"]["beta"]) == 9,
        variant=configuration,
        sigma=fit["diagnostics"]["noise_sigma_hz"],
        reference=np.array(fit["diagnostics"]["phase_reference_s"]),
        aliases=fit["aliases"],
    )


def csv_write(path, rows):
    with path.open("w") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def plot(rows, variants):
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for ax, arm in zip(axes, ("c0", "fitted_c"), strict=True):
        values = np.array(
            [
                [
                    next(
                        r["position_error_km"]
                        for r in rows
                        if r["case"] == case
                        and r["variant"] == variant
                        and r["arm"] == arm
                        and r["final"]
                    )
                    for case in CASES
                ]
                for variant in variants
            ]
        )
        im = ax.imshow(values, vmin=0, vmax=5, cmap="YlOrRd", aspect="auto")
        ax.set(
            xticks=range(5),
            xticklabels=[c[-3:] for c in CASES],
            yticks=range(len(variants)),
            yticklabels=variants,
            title=arm,
        )
        for (i, j), value in np.ndenumerate(values):
            ax.text(
                j,
                i,
                f"{value:.3f}",
                ha="center",
                va="center",
                color="white" if value > 3 else "black",
            )
    fig.subplots_adjust(left=0.14, right=0.84, wspace=0.5, bottom=0.15)
    fig.colorbar(im, cax=fig.add_axes([0.9, 0.15, 0.015, 0.7]), label="Position error (km)")
    fig.savefig(OUTPUT / "structured_position_errors.png", dpi=170)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    for variant in variants:
        data = [
            next(
                r
                for r in rows
                if r["case"] == case and r["variant"] == variant and r["arm"] == "c0" and r["final"]
            )
            for case in CASES
        ]
        axes[0].plot(range(5), [r["white_gate_points"] for r in data], "o-", label=variant)
        axes[1].plot(range(5), [r["mean_linearization_rms_hz"] for r in data], "o-", label=variant)
    for ax in axes:
        ax.set(xticks=range(5), xticklabels=[c[-3:] for c in CASES])
    axes[0].set(ylabel="Accepted curved points (original white gates)")
    axes[1].set(ylabel="Tangent vs exact combined SGP4 mean RMS (Hz)", yscale="log")
    axes[-1].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(OUTPUT / "coverage_and_mean_approximation.png", dpi=170)
    plt.close(fig)
    path = ROOT / "reports/2026_10_18_dsx01_reception_doppler/blind_endpoint_corrections.json"
    corrections = json.loads(path.read_text())
    fig, ax = plt.subplots(figsize=(9, 4))
    for key, label in (
        ("native_RMS_hz", "Raw correction"),
        ("curve_centered_RMS_hz", "After curve mean"),
        ("curve_nonaffine_RMS_hz", "After curve affine term"),
    ):
        ax.plot(range(5), [corrections[c]["relativistic"][key] for c in CASES], "o-", label=label)
    ax.set(
        xticks=range(5),
        xticklabels=[c[-3:] for c in CASES],
        ylabel="Correction RMS (Hz)",
        yscale="log",
        title="Reception-time + c⁻² corrections at blind endpoints",
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUTPUT / "reception_correction_scale.png", dpi=170)
    plt.close(fig)


def run(*, include_labels=False):
    variants = VARIANTS + (("identity",) if include_labels else ())
    rows, ablations, details, bindings = [], [], {}, {}
    for case in CASES:
        scan = Scan(case)
        apply_measurements(
            scan, json.loads(measurement_path(case).read_text())["points"], "glrt300"
        )
        original_white = list(scan.white)
        for variant in variants:
            path, data = records(case, variant)
            bindings[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
            for record in data:
                fits = record["fits"]
                assert fits["c0"]["rows"] == fits["fitted_c"]["rows"]
                assert fits["c0"]["aliases"] == fits["fitted_c"]["aliases"]
                assert fits["c0"]["starts"] == fits["fitted_c"]["starts"]
                assert (
                    fits["c0"]["diagnostics"]["phase_reference_s"]
                    == fits["fitted_c"]["diagnostics"]["phase_reference_s"]
                )
                pair_metrics = {}
                for arm, fit in fits.items():
                    p = problem_for(scan, fit, variant)
                    x = np.array(fit["parameters"])
                    z = p.residual(x)
                    error = abs(float(z @ z) - fit["frequency_prior_score"])
                    if error > 1e-5:
                        raise ValueError(
                            f"objective mismatch: {case}/{variant}/"
                            f"{record['iteration']}/{arm}: {error}"
                        )
                    adapter = EvaluationAdapter(p)
                    item = dict(fit=fit, method="receiver_smooth", arm=arm)

                    def factory(*args, adapter=adapter):
                        return adapter

                    scan.white = original_white
                    metrics = nominated_metrics(scan, item, problem_factory=factory)
                    pair_metrics[arm] = metrics
                    colored_metrics = metrics
                    if "colored" in variant:
                        scan.white = [covariance_whitener(t["times"], p.sigma) for t in scan.tracks]
                        try:
                            colored_metrics = nominated_metrics(scan, item, problem_factory=factory)
                        finally:
                            scan.white = original_white
                    final = record is data[-1]
                    linearization_error = None
                    exact_parameters = None
                    if final:
                        exact, _, exact_parameters = exact_conditional_frequency(p, x)
                        tangent, _ = p.conditional_frequency(x)
                        linearization_error = float(
                            np.sqrt(np.mean((p.q * (exact - tangent)) ** 2))
                        )
                    row = dict(
                        case=case,
                        variant=variant,
                        arm=arm,
                        round=record["iteration"],
                        final=final,
                        position_error_km=distance_km(
                            (fit["latitude_deg"], fit["longitude_deg"]), REFERENCE
                        ),
                        frequency_prior_score=fit["frequency_prior_score"],
                        total_score=fit["score"],
                        white_gate_points=metrics["accepted_nominated_curved_points"],
                        white_gate_curves=sum(t["compatible"] for t in metrics["tracks"]),
                        white_gate_native_rms_hz=metrics["accepted_native_rms_hz"],
                        colored_gate_points=colored_metrics["accepted_nominated_curved_points"],
                        mean_linearization_rms_hz=linearization_error,
                        objective_replay_error=error,
                        original_curved_points=metrics["curved_points"],
                        alias_changes_at_gate=metrics["aliases_changed"],
                    )
                    rows.append(row)
                    details[f"{case}/{variant}/{record['iteration']}/{arm}"] = dict(
                        native=metrics,
                        colored_gate=colored_metrics if "colored" in variant else None,
                        exact_conditional_parameters=exact_parameters,
                    )
                common = {
                    t["component"] for t in pair_metrics["c0"]["tracks"] if t["compatible"]
                } & {t["component"] for t in pair_metrics["fitted_c"]["tracks"] if t["compatible"]}
                ablation = dict(
                    case=case, variant=variant, round=record["iteration"], common_points=0
                )
                for arm in ("c0", "fitted_c"):
                    tracks = [t for t in pair_metrics[arm]["tracks"] if t["component"] in common]
                    n = sum(t["points"] for t in tracks)
                    ablation["common_points"] = n
                    ablation["native_rms_" + arm + "_hz"] = float(
                        np.sqrt(sum(t["native_square_hz2"] for t in tracks) / max(1, n))
                    )
                ablations.append(ablation)
    selection = []
    for case in CASES:
        choices = [r for r in rows if r["case"] == case and r["arm"] == "c0" and r["final"]]
        chosen = min(choices, key=lambda r: r["total_score"])
        partner = next(
            r
            for r in rows
            if r["case"] == case
            and r["arm"] == "fitted_c"
            and r["final"]
            and r["variant"] == chosen["variant"]
        )
        selection.append(
            dict(
                case=case,
                selected_by_c0_score=chosen["variant"],
                error_c0_km=chosen["position_error_km"],
                error_fitted_c_km=partner["position_error_km"],
            )
        )
    write(OUTPUT / "evaluation_summary.json", rows)
    csv_write(OUTPUT / "evaluation_summary.csv", rows)
    write(OUTPUT / "frequency_details.json", details)
    write(OUTPUT / "c_ablation.json", ablations)
    csv_write(OUTPUT / "c_ablation.csv", ablations)
    write(OUTPUT / "c0_model_selection.json", selection)
    write(OUTPUT / "evaluation_bindings.json", bindings)
    plot(rows, variants)
    print(
        json.dumps(
            dict(
                fit_records=len(rows),
                matched_c_pairs=len(ablations),
                max_replay_error=max(r["objective_replay_error"] for r in rows),
                selection=selection,
            )
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-labels", action="store_true")
    run(include_labels=parser.parse_args().include_labels)
