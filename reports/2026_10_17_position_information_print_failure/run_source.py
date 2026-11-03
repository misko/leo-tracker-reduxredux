"""Audit local position information in immutable blind satellite families."""

import hashlib
import json
from pathlib import Path

import analyze_dsx01_fixed_site as matching
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from associate_merged_track_catalogue import write
from transfer_fixed_satellite_families import ROOT, FixedFamilies

from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)
from leo.analysis.research.projected_position_information import projected_position_information

REPORT = ROOT / "reports/2026_10_17_position_information"
SOURCE = ROOT / "reports/2026_10_17_fixed_family_transfer/search"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(case, fitted_c, merged):
    arm = "fitted_c" if fitted_c else "c0"
    name = f"{'merged' if merged else 'unmerged'}_default_{arm}"
    source = SOURCE / case / name / "fit.json"
    fit = json.loads(source.read_text())["endpoint"]
    study = FixedFamilies(case, fitted_c, merged)
    beta, phases = np.asarray(fit["beta"]), np.asarray(fit["phases_s"])
    latitude, longitude = fit["latitude_deg"], fit["longitude_deg"]
    geometry = prepare_phase_geometry(study.sky, study.times, phases)
    f, _, h = phase_linear_frequency(geometry, latitude, longitude)

    def derivative(step):
        columns = []
        for dlat, dlon in ((0, step / (111.32 * np.cos(np.deg2rad(latitude)))), (step / 111, 0)):
            plus = phase_linear_frequency(geometry, latitude + dlat, longitude + dlon)[0]
            minus = phase_linear_frequency(geometry, latitude - dlat, longitude - dlon)[0]
            columns.append((plus - minus) / (2 * step))
        return np.stack(columns, axis=-1)

    d = derivative(0.05)
    fine = derivative(0.025)
    discrepancy = float(np.max(np.abs(d - fine)))
    if discrepancy > 1e-3:
        raise ValueError("position finite differences are unstable")
    rows, nuisance, weights, ids = [], [], [], []
    nb, ns, nc = len(beta), len(study.norads), len(study.groups)
    prior = np.zeros(nb + ns + nc)
    prior[4:8] = 1 / (150 * 0.5) ** 2
    prior[nb : nb + ns] = 1 / study.sigma**2
    for ci, (_, members) in enumerate(study.groups):
        count = sum(len(t["times"]) for t in members)
        weight = min(1, 50 / count)
        prior[nb + ns + ci] = weight / 1000**2
        j = study.labels[ci]
        for track in members:
            ix = np.searchsorted(study.times, track["times"])
            q, g, n = track["rf_hz"] / 11.5e9, matching.group(track), len(ix)
            rows.extend(q * d[j, ix])
            features = np.zeros((n, nb + ns + nc))
            features[:, g] = 1
            features[:, g + 4] = (track["times"] - 150) / 150
            if fitted_c:
                features[:, 8] = track["rf_hz"] / 1e9 - 11.5
            features[:, nb + j] = q * h[j, ix]
            features[:, nb + ns + ci] = 1
            nuisance.extend(features)
            weights.extend([weight] * n)
            ids.extend(track["observation_ids"])
    a, b, weights = np.asarray(rows), np.asarray(nuisance), np.asarray(weights)
    if sorted(ids) != study.observation_ids or len(set(ids)) != len(ids):
        raise ValueError("information audit changed the original fixed population")
    stages = [
        ("all_nuisance_fixed", []),
        ("component_constants", list(range(nb + ns, nb + ns + nc))),
        ("plus_hardware_offsets", list(range(4)) + list(range(nb + ns, nb + ns + nc))),
        ("plus_hardware_drifts_c", list(range(nb)) + list(range(nb + ns, nb + ns + nc))),
        ("plus_satellite_phases", list(range(len(prior)))),
    ]
    results = []
    for stage, columns in stages:
        result = projected_position_information(
            a, b[:, columns], weights=weights, prior_precision=prior[columns]
        )
        results.append(dict(stage=stage, **result))
    results.append(
        dict(
            stage="all_nuisance_no_priors", **projected_position_information(a, b, weights=weights)
        )
    )
    folder = REPORT / case / name
    folder.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(
        folder / "jacobians.npz",
        position_hz_per_km=a,
        nuisance=b,
        weights=weights,
        prior_precision=prior,
    )
    write(folder / "information.json", results)
    write(
        folder / "protocol.json",
        dict(
            source_sha256=digest(Path(__file__)),
            kernel_sha256=digest(
                ROOT / "src/leo/analysis/research/projected_position_information.py"
            ),
            source_fit=str(source.relative_to(ROOT)),
            source_fit_sha256=digest(source),
            source_blind_fit_sha256=study.source_digest,
            source_blind_association_sha256=study.association_digest,
            observation_ids=ids,
            candidates=study.norads,
            labels=study.labels,
            no_position_or_hardware_refit=True,
            no_evaluation_position_used_in_information=True,
            all_individually_measured_curved_points_retained=True,
            noise_hz=150,
            capped_component_point_weight=50,
            phase_sigma_s=study.sigma,
            phase_bounds_s=study.bounds,
            drift_sigma_hz_s=0.5,
            component_bias_sigma_hz=1000,
            local_gaussian_mean_model_not_full_score_hessian=True,
            conditional_volume_derivatives_and_active_bounds_not_in_covariance=True,
            independent_noise_assumption_not_validated=True,
            fixed_alias_branches_and_identities=True,
            finite_difference_steps_km=[0.05, 0.025],
            maximum_derivative_discrepancy_hz_per_km=discrepancy,
        ),
    )
    # Evaluation is attached only after the information calculation is saved.
    evaluation = json.loads(source.with_name("evaluation.json").read_text())
    if evaluation["fit_sha256"] != digest(source):
        raise ValueError("evaluation is not bound to the independent fit")
    full = results[-2]
    summary = dict(
        case=case,
        fitted_c=fitted_c,
        merged=merged,
        points=len(ids),
        families=nc,
        satellites=ns,
        position_error_km=evaluation["position_error_km"],
        nuisance_adjusted_one_sigma_axes_km=full["one_sigma_axes_km"],
        no_prior_one_sigma_axes_km=results[-1]["one_sigma_axes_km"],
        raw_one_sigma_axes_km=results[0]["one_sigma_axes_km"],
        phase_near_bounds=int(np.count_nonzero(np.abs(phases) >= 0.99 * study.bounds)),
        drift_near_bounds=int(np.count_nonzero(np.abs(beta[4:8]) >= 149)),
        conditional_covariance_not_accuracy_claim=True,
    )
    write(folder / "summary.json", summary)
    print(json.dumps(summary), flush=True)
    return summary, results


def run():
    REPORT.mkdir(exist_ok=False)
    all_results = []
    for case, merged in (("DSX01-S01", False), ("DSX01-S01", True), ("DS22-001", False)):
        for fitted_c in (False, True):
            all_results.append(audit(case, fitted_c, merged))
    write(REPORT / "summary.json", [r[0] for r in all_results])
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), layout="constrained")
    for ax, offset in zip(axes, (0, 2, 4), strict=True):
        for k, label in ((0, "c=0"), (1, "fitted-c")):
            summary, stages = all_results[offset + k]
            values = [
                r["one_sigma_axes_km"][0] if r["one_sigma_axes_km"] is not None else np.nan
                for r in stages
            ]
            ax.semilogy(range(len(values)), values, "o-", label=label)
        ax.set(
            title=f"{summary['case']} / {'merged' if summary['merged'] else 'separate'}",
            xticks=range(6),
            xticklabels=["Fixed", "+Bias", "+Offsets", "+Drifts/c", "+Phase", "No priors"],
            ylabel="Conditional major 1σ axis (km)",
        )
        ax.tick_params(axis="x", rotation=35)
        ax.grid(alpha=0.2)
        ax.legend()
    fig.suptitle("Local information loss to nuisance parameters; not an accuracy guarantee")
    fig.savefig(REPORT / "nuisance_information.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    run()
