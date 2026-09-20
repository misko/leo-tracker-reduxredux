"""Local track geometry at an inferred position, with no evaluation-site input.

Bounds assume correct frozen identities/orbits and independent 60 Hz noise.
They are sensitivity diagnostics, not measured positioning accuracy.
"""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from replay_regional_doppler import digest, write_json

from leo.analysis.research.doppler_error_budget import information, nuisance_project, profile
from leo.analysis.research.regional_doppler import LIGHT_KM_S, REFERENCE_RF_HZ, Region


def analyse(data, latitude, longitude):
    region = Region(latitude, longitude, 200, 200)
    train = data["training"].astype(bool)
    group = data["segment"]
    p = data["p"] if "p" in data else data["p0.0"]
    v = data["v"] if "v" in data else data["v0.0"]

    def prediction(east=0, north=0, pp=p, vv=v):
        receiver = region.points([east], [north], 0).ecef_km[0]
        delta = pp - receiver
        return (
            -REFERENCE_RF_HZ
            / LIGHT_KM_S
            * np.sum(delta * vv, axis=1)
            / np.linalg.norm(delta, axis=1)
        )

    predicted = prediction()
    derivatives = np.column_stack(
        [
            (prediction(0.01, 0) - prediction(-0.01, 0)) / 0.02,
            (prediction(0, 0.01) - prediction(0, -0.01)) / 0.02,
            prediction(pp=data["p0.5"], vv=data["v0.5"])
            - prediction(pp=data["p-0.5"], vv=data["v-0.5"]),
        ]
    )
    j = profile(derivatives, group, train)
    residual = profile(data["y"] - predicted, group, train)
    rows, matrices = [], []
    for segment in np.unique(group):
        mask = (group == segment) & train
        t = data["time"][mask]
        t = t - t.mean()
        curved = nuisance_project(predicted[mask, None], np.column_stack([np.ones(len(t)), t]))
        jj = j[mask]
        fixed = information(jj[:, :2], 60)
        free = information(nuisance_project(jj[:, :2], jj[:, 2:]), 60)
        eig = np.linalg.eigvalsh(jj[:, :2].T @ jj[:, :2] / 60**2)
        matrix = jj.T @ jj / 60**2
        matrices.append(matrix)
        rows.append(
            dict(
                segment=int(segment),
                norad=int(data["norad"][mask][0]),
                session=int(data["session"][mask][0]),
                observations=int(mask.sum()),
                span_s=float(np.ptp(t)),
                curvature_rms_hz=float(np.sqrt(np.mean(curved**2))),
                training_rms_hz=float(np.sqrt(np.mean(residual[mask] ** 2))),
                information_eigenvalues_per_km2=eig.tolist(),
                fixed_clock=fixed,
                free_track_clock=free,
            )
        )
    all_j = j[train]
    shared = nuisance_project(all_j[:, :2], all_j[:, 2:])
    result = dict(
        inference_position=dict(latitude_deg=latitude, longitude_deg=longitude),
        reference_used=False,
        training_only=True,
        conditional_on_frozen_identities=True,
        independent_noise_sigma_hz=60,
        systematic_orbit_and_correlated_errors_included=False,
        fixed_clock=information(all_j[:, :2], 60),
        free_shared_clock=information(shared, 60),
        tracks=rows,
    )
    return result, np.asarray(matrices)


def plots(result, matrices, output):
    rows = result["tracks"]
    curvature = np.array([r["curvature_rms_hz"] for r in rows])
    weak = np.array([r["information_eigenvalues_per_km2"][0] for r in rows])
    rms = np.array([r["training_rms_hz"] for r in rows])
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), layout="constrained")
    p = axes[0].scatter(curvature, weak, c=np.clip(rms, 0, 300), s=15, alpha=0.65)
    axes[0].set(
        xscale="log",
        yscale="log",
        xlabel="Predicted departure from straight line (RMS Hz)",
        ylabel="Information in weaker horizontal direction (1/km²)",
        title="Curvature does not uniquely determine position information",
    )
    fig.colorbar(p, ax=axes[0], label="Training residual RMS (Hz; clipped at 300)")
    orders = {
        "Stronger weakest-direction information first": np.argsort(-weak),
        "Greater curvature first": np.argsort(-curvature),
        "Random order (fixed seed)": np.random.default_rng(20260920).permutation(len(rows)),
    }
    result["cumulative"] = {}
    for label, order in orders.items():
        bounds = []
        for normal in np.cumsum(matrices[order], axis=0):
            # Marginalize a single common clock after combining track information.
            marginal = normal[:2, :2].copy()
            if normal[2, 2] > 0:
                marginal -= np.outer(normal[:2, 2], normal[2, :2]) / normal[2, 2]
            eig = np.linalg.eigvalsh(marginal)
            bound = float(1000 * np.sqrt(np.sum(1 / eig))) if eig[0] > 1e-12 else None
            bounds.append(bound)
        result["cumulative"][label] = dict(
            segments=[rows[i]["segment"] for i in order], rms_m=bounds
        )
        axes[1].plot(np.arange(5, len(rows) + 1), [b or np.nan for b in bounds[4:]], label=label)
    axes[1].set(
        yscale="log",
        xlabel="Number of source tracks included (first four omitted)",
        ylabel="Ideal horizontal RMS bound (m)",
        title="Unknown shared clock; offsets fitted separately per track",
    )
    axes[1].legend(fontsize=8)
    for ax in axes:
        ax.grid(alpha=0.2)
    fig.suptitle(
        "Local sensitivity only · fixed satellite identities · IID 60 Hz · no orbit-error floor"
    )
    fig.savefig(output / "track-information.png", dpi=160)
    plt.close(fig)


def refit_subsets(data, result, cohort, initial):
    """Report all predeclared geometry variants; do not select using true location."""
    from compare_positioning_cohorts import fit

    data = dict(data)
    if "p" not in data:
        data["p"], data["v"] = data["p0.0"], data["v0.0"]
    if "episode" not in data:
        data["episode"] = data["segment"]
    eligible = [r for r in result["tracks"] if r["training_rms_hz"] <= 100 and r["span_s"] >= 15]
    models = []
    for metric in ["weak_direction", "curvature"]:
        ordered = sorted(
            eligible,
            key=lambda r: (
                r["information_eigenvalues_per_km2"][0]
                if metric == "weak_direction"
                else r["curvature_rms_hz"]
            ),
            reverse=True,
        )
        for cap in [30, 100]:
            segments = [r["segment"] for r in ordered[:cap]]
            if len(segments) < 3:
                continue
            row = fit(
                data,
                Region(**cohort["region"]),
                initial,
                "observation",
                True,
                subset=np.isin(data["segment"], segments),
                fit_clock=True,
            )
            models.append(dict(metric=metric, cap=cap, segments=segments, **row))
    return dict(
        minimum_training_span_s=15,
        maximum_training_rms_hz=100,
        eligible_segments=len(eligible),
        evaluation_location_used=False,
        shared_clock_bound_s=0.5,
        exploratory_not_independent_validation=True,
        models=models,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--states", type=Path, required=True)
    parser.add_argument("--inference", type=Path, required=True)
    parser.add_argument("--cohort", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--refit-subsets", action="store_true")
    a = parser.parse_args()
    parent = json.loads(a.inference.read_text())
    model = next(
        r
        for r in parent["cohorts"][a.cohort]["models"]
        if r["weighting"] == "observation" and r["robust"] and not r["clock_fitted"]
    )
    a.output.mkdir(parents=True, exist_ok=False)
    result, matrices = analyse(
        dict(np.load(a.states)), model["latitude_deg"], model["longitude_deg"]
    )
    result["source_digests"] = {str(p): digest(p) for p in [a.states, a.inference]}
    result["identity_provenance"] = parent["identity_provenance"][a.cohort]
    plots(result, matrices, a.output)
    if a.refit_subsets:
        result["subset_inference"] = refit_subsets(
            dict(np.load(a.states)), result, parent["cohorts"][a.cohort], model["x_km"][:2]
        )
    write_json(a.output / "information.json", result)
    print(json.dumps({k: result[k] for k in ["fixed_clock", "free_shared_clock"]}, indent=2))


if __name__ == "__main__":
    main()
