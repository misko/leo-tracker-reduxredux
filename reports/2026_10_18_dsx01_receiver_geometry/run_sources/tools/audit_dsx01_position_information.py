"""Conditional linear sensitivity of blind fits; never empirical confidence."""

import argparse
import json

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, ROOT, Scan
from iterate_dsx01_position_nominations import AnchoredFamilies

OUTPUT = ROOT / "reports/2026_10_18_dsx01_model_iterations"
NOMINATIONS = ROOT / "reports/2026_10_18_dsx01_nomination_iteration/seeds_32"


def information(position, nuisance):
    """Project nuisance columns out after scaling their disparate physical units."""
    norms = np.linalg.norm(nuisance, axis=0)
    active = norms > 1e-12
    scaled = nuisance[:, active] / norms[active]
    remainder = position - scaled @ np.linalg.lstsq(scaled, position, rcond=1e-10)[0]
    matrix = remainder.T @ remainder
    values = np.maximum(0, np.linalg.eigvalsh(matrix))
    return dict(
        information_matrix_per_km2=matrix,
        information_eigenvalues_per_km2=values,
        conditional_axis_scales_km=np.divide(
            1, np.sqrt(values), out=np.full(2, np.inf), where=values > 1e-12
        ),
    )


def audit(scan, fit, method, arm):
    p = AnchoredFamilies(
        scan,
        dict(rows=fit["rows"], state=fit["state"]),
        method,
        arm == "fitted_c",
        fit["east_north_km"],
    )
    x = np.array(min(fit["fits"], key=lambda r: r["score"])["parameters"])
    count = sum(len(scan.tracks[i]["times"]) for i in p.members)
    constants = np.zeros((count, len(p.members)))
    constant_prior = []
    offset = 0
    for k, i in enumerate(p.members):
        t = scan.tracks[i]
        w = (scan.ou if method == "correlated_noise" else scan.white)[i][0]
        scale = np.sqrt(min(1, 50 / len(t["times"])))
        constants[offset : offset + len(t["times"]), k] = scale * (w @ np.ones(len(t["times"])))
        constant_prior.append(scale / 1000)
        offset += len(t["times"])

    def raw(params):
        state = p.decode(params)
        f, _ = p.predicted(params)
        data = []
        for i, block in zip(p.members, p.slices, strict=True):
            t = scan.tracks[i]
            q = t["rf_hz"] / 11.5e9
            residual = t["values"] - scan.hardware(t, state["beta"]) - q * f[block]
            if method == "receiver_smooth":
                residual -= q * scan.rx_basis[i] @ state["smooth"][t["receiver"] - 1]
            w = (scan.ou if method == "correlated_noise" else scan.white)[i][0]
            data.append(np.sqrt(min(1, 50 / len(residual))) * (w @ residual))
        return np.concatenate(data)

    # Subdivision's separate constants need an additional column for its tail.
    if method == "penalized_split":
        for k, (i, row) in enumerate(zip(p.members, p.rows, strict=True)):
            cut = row["split_at"]
            if cut > 0:
                column = constants[:, k].copy()
                first = sum(len(scan.tracks[j]["times"]) for j in p.members[:k])
                column[: first + cut] = 0
                constants[first + cut : first + len(scan.tracks[i]["times"]), k] = 0
                constants = np.column_stack([constants, column])
                constant_prior.append(constant_prior[k])
    columns = []
    for k in range(len(x)):
        a, b = x.copy(), x.copy()
        a[k] -= 1e-3
        b[k] += 1e-3
        columns.append((raw(b) - raw(a)) / 0.002)
    jac = np.array(columns).T
    nprior = 4 + len(p.labels) + sum(1 if method == "family_rate" else 2 for _ in p.extra_labels)
    if method == "receiver_smooth":
        nprior += p.starts["smooth"].size
    prior_columns = []
    for k in range(len(x)):
        a, b = x.copy(), x.copy()
        a[k] -= 1e-3
        b[k] += 1e-3
        prior_columns.append((p.residual(b)[-nprior:] - p.residual(a)[-nprior:]) / 0.002)
    prior_jac = np.array(prior_columns).T
    nuisance = np.column_stack([jac[:, 2:], constants])
    zeros = np.zeros((nprior, len(constant_prior)))
    nuisance_priors = np.column_stack([prior_jac[:, 2:], zeros])
    constant_priors = np.column_stack(
        [np.zeros((len(constant_prior), len(x) - 2)), np.diag(constant_prior)]
    )
    return dict(
        data_only=information(jac[:, :2], nuisance),
        with_gaussian_priors=information(
            np.vstack([jac[:, :2], prior_jac[:, :2], np.zeros((len(constant_prior), 2))]),
            np.vstack([nuisance, nuisance_priors, constant_priors]),
        ),
        native_noise_hz=150,
        curved_points=count,
        families=len(p.labels),
        active_parameter_bounds=[
            list(key)
            for (key, _scale), value, lo, hi in zip(p.coordinates, x, p.lower, p.upper, strict=True)
            if abs(value - lo) < 1e-3 or abs(value - hi) < 1e-3
        ],
        robust_loss_and_active_hard_bounds_not_in_information=True,
        labels_conditioned_on_not_verified=True,
        empirical_confidence=False,
    )


def run(cases):
    OUTPUT.mkdir(exist_ok=True)
    path = OUTPUT / "conditional_information.json"
    result = json.loads(path.read_text()) if path.exists() else {}
    for case in cases:
        fits = json.loads((NOMINATIONS / case / "endpoints.json").read_text())
        scan = Scan(case)
        for method in METHODS:
            for arm in ("c0", "fitted_c"):
                key = f"{case}/{arm}/{method}"
                if key in result:
                    continue
                result[key] = audit(scan, fits[f"{arm}/{method}"], method, arm)
                write(path, result)
                print(
                    key,
                    result[key]["with_gaussian_priors"]["conditional_axis_scales_km"],
                    flush=True,
                )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", nargs="+", default=["DSX01-S01"])
    run(parser.parse_args().cases)
