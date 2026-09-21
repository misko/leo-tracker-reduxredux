"""Fit frozen causal position candidates under predeclared cluster weightings.

This stage deliberately has no receiver-reference argument.  It emits sealed
fits and local, training-only sensitivity diagnostics for later evaluation by
``evaluate_uncertain_position.py``.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from compare_positioning_cohorts import fit, fitting_weights
from replay_regional_doppler import digest, write_json

from leo.analysis.research.doppler_error_budget import profile
from leo.analysis.research.regional_doppler import LIGHT_KM_S, REFERENCE_RF_HZ, Region

SCHEMA = "org.leo.research.position-weighting-benchmark/v1"
WEIGHTINGS = ("observation", "segment", "pass")
DELETION_GROUPS = ("satellite", "pass")
DELETION_FOLDS = 4
ROBUST_SCALE_HZ = 250.0


def _fold(label, values, folds=DELETION_FOLDS):
    """Map scalar or row keys to reproducible folds without Python hash state."""
    array = np.asarray(values)
    rows = array.reshape(-1, 1) if array.ndim == 1 else array
    return np.asarray(
        [
            int.from_bytes(
                hashlib.sha256(
                    (label + ":" + ":".join(str(int(value)) for value in row)).encode()
                ).digest()[:8],
                "big",
            )
            % folds
            for row in rows
        ],
        dtype=int,
    )


def add_pass_groups(data):
    result = dict(data)
    _, result["pass_group"] = np.unique(
        np.column_stack([result["session"], result["norad"]]),
        axis=0,
        return_inverse=True,
    )
    return result


def _predicted(data, region, position_km, clock_s):
    receiver = region.points([position_km[0]], [position_km[1]], 0).ecef_km[0]
    p, v = data["p"], data["v"]
    if clock_s:
        tau = float(clock_s)
        p = (
            p
            + (data["p0.5"] - data["p-0.5"]) * tau
            + 2 * (data["p0.5"] + data["p-0.5"] - 2 * p) * tau * tau
        )
        v = (
            v
            + (data["v0.5"] - data["v-0.5"]) * tau
            + 2 * (data["v0.5"] + data["v-0.5"] - 2 * v) * tau * tau
        )
    delta = p - receiver
    return -REFERENCE_RF_HZ / LIGHT_KM_S * np.sum(delta * v, axis=1) / np.linalg.norm(delta, axis=1)


def _objective(data, region, position_km, clock_s, weighting):
    train = data["training"].astype(bool)
    residual = profile(
        data["y"] - _predicted(data, region, position_km, clock_s),
        data["segment"],
        train,
    )
    transformed = residual * np.sqrt(2 / (np.sqrt(1 + (residual / ROBUST_SCALE_HZ) ** 2) + 1))
    return (transformed * fitting_weights(data, weighting))[train]


def _cluster_covariance(jacobian, residual, groups):
    bread = np.linalg.pinv(jacobian.T @ jacobian, rcond=1e-12)
    unique, inverse = np.unique(groups, return_inverse=True)
    scores = np.zeros((len(unique), jacobian.shape[1]))
    np.add.at(scores, inverse, jacobian * residual[:, None])
    meat = scores.T @ scores
    n, parameters = jacobian.shape
    correction = (
        len(unique) / (len(unique) - 1) * (n - 1) / (n - parameters)
        if len(unique) > 1 and n > parameters
        else 1.0
    )
    covariance = correction * bread @ meat @ bread
    return (covariance + covariance.T) / 2


def _covariance_summary(covariance):
    horizontal = covariance[:2, :2]
    eigenvalues = np.maximum(np.linalg.eigvalsh(horizontal), 0)
    return {
        "parameter_covariance": covariance.tolist(),
        "horizontal_covariance_km2": horizontal.tolist(),
        "horizontal_rms_m": float(1000 * np.sqrt(np.trace(horizontal))),
        "ellipse_1sigma_semiaxes_m": (1000 * np.sqrt(eigenvalues[::-1])).tolist(),
    }


def local_uncertainty(data, region, model, weighting):
    """Return local covariance, treating an active clock bound as fixed."""
    train = data["training"].astype(bool)
    position = np.asarray(model["x_km"][:2], dtype=float)
    clock_s = float(model["clock_s"] or 0.0)
    centre = _objective(data, region, position, clock_s, weighting)
    columns = []
    step_km = 0.01
    for axis in range(2):
        delta = np.zeros(2)
        delta[axis] = step_km
        columns.append(
            (
                _objective(data, region, position + delta, clock_s, weighting)
                - _objective(data, region, position - delta, clock_s, weighting)
            )
            / (2 * step_km)
        )
    clock_at_bound = bool(model["clock_at_bound"])
    clock_step_s = 1e-4
    if not clock_at_bound:
        columns.append(
            (
                _objective(data, region, position, clock_s + clock_step_s, weighting)
                - _objective(data, region, position, clock_s - clock_step_s, weighting)
            )
            / (2 * clock_step_s)
        )
    jacobian = np.column_stack(columns)
    bread = np.linalg.pinv(jacobian.T @ jacobian, rcond=1e-12)
    dof = max(len(centre) - jacobian.shape[1], 1)
    naive = np.sum(centre**2) / dof * bread
    train_data = {key: np.asarray(value)[train] for key, value in data.items()}
    clusters = {
        "episode": train_data["episode"],
        "pass": train_data["pass_group"],
        "satellite": train_data["norad"],
        "recording": train_data["session"],
    }
    weights_squared = fitting_weights(data, weighting)[train] ** 2
    return {
        "kind": (
            "local_training_sandwich_conditional_on_active_clock_bound"
            if clock_at_bound
            else "local_training_sandwich_joint_position_and_shared_clock"
        ),
        "parameters": ["east_km", "north_km"]
        if clock_at_bound
        else ["east_km", "north_km", "clock_s"],
        "clock_at_bound": clock_at_bound,
        "finite_difference_step_km": step_km,
        "clock_finite_difference_step_s": None if clock_at_bound else clock_step_s,
        "robust_scale_hz": ROBUST_SCALE_HZ,
        "training_observations": int(train.sum()),
        "weight_effective_observations": float(
            weights_squared.sum() ** 2 / np.sum(weights_squared**2)
        ),
        "iid_model_based": _covariance_summary(naive),
        "cluster_robust": {
            name: {
                "clusters": int(len(np.unique(values))),
                **_covariance_summary(_cluster_covariance(jacobian, centre, values)),
            }
            for name, values in clusters.items()
        },
        "interpretation": (
            "Dataset-conditional local sensitivity; excludes orbit bias, identity error, "
            "and site-to-site variation. An active clock bound is conditioned upon because "
            "the unconstrained local covariance is not valid at that boundary."
        ),
    }


def _source_model(document, method):
    matches = [
        row
        for row in document["models"]
        if row.get("selection") == "all"
        and row.get("clock_model") == "shared_recorded"
        and (row.get("orbit_model", "baseline") == method)
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one all/shared_recorded source model for {method!r}")
    return matches[0]


def benchmark_candidate(name, method, inference_path, states_path, parent, config):
    document = json.loads(inference_path.read_text())
    source = _source_model(document, method)
    if not document.get("strictly_causal") or document.get("evaluation_location_used"):
        raise ValueError(f"{name}: candidate is not sealed causal inference")
    if document.get("states_digest") != digest(states_path):
        raise ValueError(f"{name}: state digest mismatch")
    data = add_pass_groups(dict(np.load(states_path)))
    region = Region(**parent["region"])
    bounds = {0: source["clock_bounds_s"][0]}
    full = []
    deletions = []
    for weighting in config["weightings"]:
        row = fit(
            data,
            region,
            parent["initial"],
            weighting,
            True,
            fit_clock=True,
            clock_bounds=bounds,
        )
        row["uncertainty"] = local_uncertainty(data, region, row, weighting)
        full.append(row)
        print(name, weighting, row["evaluation_rms_hz"], flush=True)
        pass_keys = np.column_stack([data["session"], data["norad"]])
        fold_values = {
            "satellite": _fold("satellite", data["norad"], config["deletion_folds"]),
            "pass": _fold("pass", pass_keys, config["deletion_folds"]),
        }
        for grouping in config["deletion_groups"]:
            for fold in range(config["deletion_folds"]):
                retained = fold_values[grouping] != fold
                deletion = fit(
                    data,
                    region,
                    parent["initial"],
                    weighting,
                    True,
                    subset=retained,
                    fit_clock=True,
                    clock_bounds=bounds,
                )
                deletions.append(
                    {
                        "weighting": weighting,
                        "deletion_group": grouping,
                        "deletion_fold": fold,
                        **deletion,
                    }
                )
    return {
        "name": name,
        "method": method,
        "source_inference": str(inference_path),
        "source_states": str(states_path),
        "source_digests": {
            str(inference_path): digest(inference_path),
            str(states_path): digest(states_path),
        },
        "observations": int(len(data["y"])),
        "episodes": int(len(np.unique(data["episode"]))),
        "passes": int(len(np.unique(data["pass_group"]))),
        "satellites": int(len(np.unique(data["norad"]))),
        "full_fits": full,
        "deletion_fits": deletions,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument(
        "--candidate",
        nargs=4,
        action="append",
        metavar=("NAME", "METHOD", "INFERENCE_JSON", "STATES_NPZ"),
        required=True,
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("fresh output required")
    parent_path = args.parent / "inference.json" if args.parent.is_dir() else args.parent
    parent = json.loads(parent_path.read_text())
    config = {
        "weightings": list(WEIGHTINGS),
        "pass_definition": "unique recording-index and NORAD pair",
        "deletion_groups": list(DELETION_GROUPS),
        "deletion_folds": DELETION_FOLDS,
        "deletion_assignment": "sha256(group name and integer key) modulo folds",
        "partition": "inherited randomized RF training/evaluation split",
        "robust_loss": f"soft_l1-equivalent residual transform, scale {ROBUST_SCALE_HZ:g} Hz",
        "clock_model": "shared clock inside source candidate's recorded bound",
        "truth_evaluation": "performed only after this output is sealed",
    }
    output = {
        "schema": SCHEMA,
        "evaluation_location_used": False,
        "configuration_frozen_before_truth_evaluation": True,
        "configuration": config,
        "parent_digest": digest(parent_path),
        "candidates": [],
    }
    for name, method, inference, states in args.candidate:
        output["candidates"].append(
            benchmark_candidate(name, method, Path(inference), Path(states), parent, config)
        )
    write_json(args.output, output)


if __name__ == "__main__":
    main()
