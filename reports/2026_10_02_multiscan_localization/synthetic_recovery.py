"""Truth-free conditional synthetic recovery audit for the frozen DS10-S01 bank."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from coherent_fit import FixedBankLikelihood
from gauss_newton import refine_gauss_newton
from grouped_likelihood import DEFAULT_ALIAS_HZ
from staged_fit import frozen_row_weights
from track_likelihood import prepare_track_grouped_likelihood

ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = ROOT / "runs" / "coherent-v1" / "DS10-S01" / "fit.json"
DEFAULT_ZOOM = ROOT / "runs" / "profile-zoom-v1" / "DS10-S01" / "fit.json"
DEFAULT_OUTPUT = ROOT / "synthetic-recovery-ds10-s01.json"
DEFAULT_OFFSETS_KM = ((0.75, 0.0), (-0.5, 0.5), (0.0, -0.75))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def jsonable(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


class SyntheticData:
    """Read-only layout adapter that substitutes only synthetic measurements."""

    def __init__(self, source, measured, provenance):
        measured = np.asarray(measured, dtype=float)
        if measured.shape != np.asarray(source.measured).shape:
            raise ValueError("synthetic measurements must match the source layout")
        if np.any(~np.isfinite(measured)):
            raise ValueError("synthetic measurements must be finite")
        self.source = source
        self.measured = measured.copy()
        self.provenance = dict(provenance)

    def __getattr__(self, name):
        return getattr(self.source, name)


@dataclass(frozen=True)
class SyntheticRealization:
    data: SyntheticData
    group_values: np.ndarray
    selected_rows: np.ndarray
    selected_satellites: np.ndarray
    anchor_indices: np.ndarray
    anchor_identities: np.ndarray
    metadata: dict


def _normalized_group_weights(group, row_weights):
    group = np.asarray(group)
    row_weights = np.asarray(row_weights, dtype=float)
    if group.ndim != 1 or row_weights.shape != group.shape or len(group) == 0:
        raise ValueError("group and row_weights must be equal nonempty vectors")
    if np.any(~np.isfinite(row_weights)) or np.any(row_weights < 0):
        raise ValueError("row_weights must be finite and non-negative")
    values, inverse = np.unique(group, return_inverse=True)
    totals = np.bincount(inverse, weights=row_weights, minlength=len(values))
    if np.any(totals <= 0):
        raise ValueError("each source group must have positive row mass")
    return values, inverse, row_weights / totals[inverse]


def _validate_masses(masses, anchor_count, satellite_count):
    raw = np.asarray(masses["raw_satellite_mass"], dtype=float)
    anchor = np.asarray(masses["anchor_satellite_mass"], dtype=float)
    unknown = np.asarray(masses["anchor_unknown_mass"], dtype=float)
    background = float(masses["raw_background_mass"])
    if raw.shape != (satellite_count,) or anchor.shape != (
        anchor_count,
        satellite_count,
    ):
        raise ValueError("frozen satellite masses do not match the bank and anchors")
    if unknown.shape != (anchor_count,):
        raise ValueError("frozen unknown masses do not match the anchors")
    if (
        np.any(~np.isfinite(raw))
        or np.any(~np.isfinite(anchor))
        or np.any(~np.isfinite(unknown))
        or not np.isfinite(background)
        or np.any(raw < 0)
        or np.any(anchor < 0)
        or np.any(unknown < 0)
        or background <= 0
    ):
        raise ValueError("frozen masses must be finite and non-negative")
    if not np.isclose(background + raw.sum(), 1.0, rtol=0, atol=1e-12):
        raise ValueError("raw masses must sum to one")
    if anchor_count and not np.allclose(unknown + anchor.sum(axis=1), 1.0, rtol=0, atol=1e-12):
        raise ValueError("anchor masses must sum to one")
    return raw, anchor


def _paired_predictions(data, parameters, satellites):
    satellites = np.asarray(satellites, dtype=int)
    rows = np.repeat(np.arange(len(data.times)), len(satellites))
    paired = np.tile(satellites, len(data.times))
    predicted, visible = data.predict(parameters, rows=rows, satellites=paired)
    shape = (len(data.times), len(satellites))
    return np.asarray(predicted).reshape(shape), np.asarray(visible).reshape(shape)


def conditional_noiseless_realization(
    data,
    generating_parameters,
    satellites,
    masses,
    anchors,
    *,
    row_weights,
    seed=2026100216,
):
    """Condition each usable group on one noiseless categorical signal row.

    This is deliberately not an unconditional draw from the likelihood mixture.
    It conditions raw groups on their signal branch and anchors on a known identity
    with maximum all-group visibility. Every unselected alternative is an
    independent fixed-RNG uniform-null draw.
    """

    generating_parameters = np.asarray(generating_parameters, dtype=float)
    satellites = np.asarray(satellites, dtype=int)
    anchors = [np.asarray(anchor, dtype=np.asarray(data.group).dtype) for anchor in anchors]
    if generating_parameters.shape != (6 + len(data.numbers),):
        raise ValueError("generating parameters do not match the candidate count")
    if np.any(~np.isfinite(generating_parameters)):
        raise ValueError("generating parameters must be finite")
    if satellites.ndim != 1 or len(satellites) == 0:
        raise ValueError("satellites must be a nonempty vector")
    if len(np.unique(satellites)) != len(satellites):
        raise ValueError("satellites must be unique")
    raw_mass, anchor_mass = _validate_masses(masses, len(anchors), len(satellites))
    group_values, group_inverse, normalized_weights = _normalized_group_weights(
        data.group, row_weights
    )
    group_lookup = {
        value.item() if isinstance(value, np.generic) else value: index
        for index, value in enumerate(group_values)
    }
    group_anchor = np.full(len(group_values), -1, dtype=int)
    for anchor_index, anchor in enumerate(anchors):
        if anchor.ndim != 1 or len(anchor) == 0:
            raise ValueError("anchors must contain nonempty group vectors")
        for value in anchor:
            key = value.item() if isinstance(value, np.generic) else value
            if key not in group_lookup:
                raise ValueError(f"anchor contains unknown source group {key!r}")
            group_index = group_lookup[key]
            if group_anchor[group_index] >= 0:
                raise ValueError("source groups cannot belong to multiple anchors")
            group_anchor[group_index] = anchor_index

    predicted, visible = _paired_predictions(data, generating_parameters, satellites)
    rng = np.random.default_rng(seed)
    measured = rng.uniform(-DEFAULT_ALIAS_HZ / 2, DEFAULT_ALIAS_HZ / 2, len(data.times))
    selected_rows = np.full(len(group_values), -1, dtype=int)
    selected_satellites = np.full(len(group_values), -1, dtype=int)
    anchor_identities = np.full(len(anchors), -1, dtype=int)

    for anchor_index in range(len(anchors)):
        indices = np.flatnonzero(group_anchor == anchor_index)
        visibility_count = np.zeros(len(satellites), dtype=int)
        for group_index in indices:
            rows = np.flatnonzero(group_inverse == group_index)
            visibility_count += np.any(visible[rows], axis=0)
        positive = anchor_mass[anchor_index] > 0
        if not np.any(positive):
            continue
        maximum = np.max(visibility_count[positive])
        eligible = positive & (visibility_count == maximum)
        probabilities = np.where(eligible, anchor_mass[anchor_index], 0.0)
        probabilities /= probabilities.sum()
        anchor_identities[anchor_index] = int(rng.choice(len(satellites), p=probabilities))

    for group_index in range(len(group_values)):
        rows = np.flatnonzero(group_inverse == group_index)
        anchor_index = group_anchor[group_index]
        if anchor_index >= 0:
            candidate = anchor_identities[anchor_index]
            if candidate < 0:
                continue
            usable_rows = rows[visible[rows, candidate]]
            if len(usable_rows) == 0:
                continue
            probabilities = normalized_weights[usable_rows]
            probabilities /= probabilities.sum()
            selected_row = int(rng.choice(usable_rows, p=probabilities))
        else:
            pair_weights = normalized_weights[rows, None] * raw_mass[None, :]
            pair_weights = np.where(visible[rows], pair_weights, 0.0)
            if pair_weights.sum() <= 0:
                continue
            flat_index = int(
                rng.choice(pair_weights.size, p=(pair_weights / pair_weights.sum()).ravel())
            )
            row_offset, candidate = np.unravel_index(flat_index, pair_weights.shape)
            selected_row = int(rows[row_offset])
        measured[selected_row] = (
            predicted[selected_row, candidate] + DEFAULT_ALIAS_HZ / 2
        ) % DEFAULT_ALIAS_HZ - DEFAULT_ALIAS_HZ / 2
        selected_rows[group_index] = selected_row
        selected_satellites[group_index] = candidate

    signal = selected_rows >= 0
    anchored_signal = signal & (group_anchor >= 0)
    null_only = ~signal
    full_visibility = []
    for anchor_index in range(len(anchors)):
        identity = anchor_identities[anchor_index]
        indices = np.flatnonzero(group_anchor == anchor_index)
        full_visibility.append(bool(identity >= 0 and np.all(signal[indices])))
    metadata = {
        "schema": "conditional-noiseless-grouped-synthetic/v1",
        "seed": int(seed),
        "scope": (
            "Conditional implementation audit, not an unconditional sample from the full "
            "mixture and not evidence about real-data localization accuracy. Each usable source "
            "group has exactly one categorical noiseless signal alternative; every other stored "
            "alternative is an independent uniform-null draw. Raw groups are conditioned on the "
            "signal branch. Each anchor uses one identity across all groups, chosen from its "
            "frozen positive-mass identities by maximum visible-group coverage; groups with no "
            "visible row for that identity remain all-null."
        ),
        "row_alternatives_are_categorical": True,
        "rows_are_not_treated_as_independent_observations": True,
        "unconditional_generative_claim": False,
        "gaussian_signal_noise_hz": 0.0,
        "null_distribution": f"uniform circular interval width {DEFAULT_ALIAS_HZ} Hz",
        "group_count": int(len(group_values)),
        "signal_group_count": int(signal.sum()),
        "null_only_group_count": int(null_only.sum()),
        "anchor_count": int(len(anchors)),
        "anchored_signal_group_count": int(anchored_signal.sum()),
        "raw_signal_group_count": int(np.sum(signal & (group_anchor < 0))),
        "anchors_fully_visible": int(np.sum(full_visibility)),
        "selected_rows_sha256": hashlib.sha256(selected_rows.tobytes()).hexdigest(),
        "selected_satellites_sha256": hashlib.sha256(selected_satellites.tobytes()).hexdigest(),
    }
    synthetic = SyntheticData(data, measured, metadata)
    return SyntheticRealization(
        data=synthetic,
        group_values=group_values,
        selected_rows=selected_rows,
        selected_satellites=selected_satellites,
        anchor_indices=group_anchor,
        anchor_identities=anchor_identities,
        metadata=metadata,
    )


def objective_components(data, parameters, satellites, likelihood, tau_sigma_s=1.0):
    predicted, visible = _paired_predictions(data, parameters, satellites)
    result = likelihood.evaluate(
        predicted,
        visible,
        sigma_hz=200.0,
        satellite_weights=np.ones(len(satellites)) / len(satellites),
        background_mass=0.2,
    )
    tau = np.asarray(parameters)[6 + np.asarray(satellites, dtype=int)]
    prior = 0.5 * float(np.sum((tau / tau_sigma_s) ** 2))
    likelihood_nll = -float(result["total_log_likelihood"])
    return {
        "likelihood_nll": likelihood_nll,
        "timing_prior": prior,
        "objective": likelihood_nll + prior,
        "tau_l2_s": float(np.linalg.norm(tau)),
    }


def timing_prior_profile(data, parameters, satellites, likelihood, scales=None):
    scales = (1.0, 0.999, 0.99, 0.95, 0.0) if scales is None else tuple(scales)
    parameters = np.asarray(parameters, dtype=float)
    satellite_indices = 6 + np.asarray(satellites, dtype=int)
    profile = []
    for scale in scales:
        candidate = parameters.copy()
        candidate[satellite_indices] *= float(scale)
        profile.append(
            {
                "tau_scale": float(scale),
                **objective_components(data, candidate, satellites, likelihood),
            }
        )
    generating = profile[0]
    prior_shift = any(
        row["likelihood_nll"] > generating["likelihood_nll"] + 1e-10
        and row["objective"] < generating["objective"] - 1e-10
        for row in profile[1:]
    )
    return {
        "profile": profile,
        "timing_prior_shifts_generating_map_along_shrink_path": prior_shift,
        "interpretation": (
            "True only when shrinking tau worsens synthetic likelihood yet improves the penalized "
            "objective, directly identifying the configured timing prior as the shift source."
        ),
    }


def run_recovery_audit(
    realization,
    generating_parameters,
    satellites,
    masses,
    anchors,
    row_weights,
    *,
    offsets_km=DEFAULT_OFFSETS_KM,
    per_start_budget_s=12.0,
    total_fit_budget_s=40.0,
    recovery_tolerance_km=0.1,
    refiner=refine_gauss_newton,
):
    offsets = np.asarray(offsets_km, dtype=float)
    if offsets.ndim != 2 or offsets.shape[1] != 2 or len(offsets) < 2:
        raise ValueError("several two-coordinate position offsets are required")
    if np.any(~np.isfinite(offsets)):
        raise ValueError("position offsets must be finite")
    if per_start_budget_s <= 0 or total_fit_budget_s <= 0 or total_fit_budget_s > 60:
        raise ValueError("fit budgets must be positive with total at most 60 seconds")
    if len(offsets) * per_start_budget_s > total_fit_budget_s:
        raise ValueError("per-start fit budgets exceed the total fit budget")
    if recovery_tolerance_km <= 0 or not np.isfinite(recovery_tolerance_km):
        raise ValueError("recovery tolerance must be positive and finite")

    data = realization.data
    prepared = prepare_track_grouped_likelihood(
        data.measured,
        data.group,
        row_weights=row_weights,
        anchors=anchors,
    )
    baseline_likelihood = FixedBankLikelihood(prepared, masses)
    prior_profile = timing_prior_profile(
        data, generating_parameters, satellites, baseline_likelihood
    )
    started = time.monotonic()
    trials = []
    for offset in offsets:
        elapsed = time.monotonic() - started
        remaining = total_fit_budget_s - elapsed
        if remaining <= 0.25:
            trials.append(
                {
                    "position_offset_km": offset,
                    "status": "not_run_total_budget_exhausted",
                    "position_recovered": False,
                }
            )
            continue
        initial = np.asarray(generating_parameters, dtype=float).copy()
        initial[:2] += offset
        likelihood = FixedBankLikelihood(prepared, masses)
        fitted = refiner(
            data,
            initial,
            np.asarray(satellites, dtype=int),
            np.ones(len(satellites)),
            likelihood,
            sigma_hz=200.0,
            tau_sigma_s=1.0,
            tau_bound_s=3.0,
            slope_bound=50.0,
            budget_s=min(per_start_budget_s, max(0.1, remaining - 0.1)),
        )
        fitted_position = np.asarray(fitted["parameters"], dtype=float)[:2]
        error = float(np.linalg.norm(fitted_position - np.asarray(generating_parameters)[:2]))
        trials.append(
            {
                "position_offset_km": offset,
                "initial_position_error_km": float(np.linalg.norm(offset)),
                "fitted_position_km": fitted_position,
                "position_error_from_generating_km": error,
                "position_recovered": bool(error <= recovery_tolerance_km),
                "fit": fitted,
            }
        )
    completed = [trial for trial in trials if "fit" in trial]
    recovered = [trial["position_recovered"] for trial in completed]
    return {
        "settings": {
            "sigma_hz": 200.0,
            "tau_sigma_s": 1.0,
            "tau_bound_s": 3.0,
            "slope_bound_hz_s": 50.0,
            "per_start_budget_s": float(per_start_budget_s),
            "total_fit_budget_s": float(total_fit_budget_s),
            "position_recovery_tolerance_km": float(recovery_tolerance_km),
        },
        "timing_prior_diagnostic": prior_profile,
        "trials": trials,
        "completed_trial_count": len(completed),
        "recovered_trial_count": int(np.sum(recovered)),
        "all_completed_positions_recovered": bool(completed and all(recovered)),
        "recovery_was_measured_not_assumed": True,
        "fit_elapsed_s": time.monotonic() - started,
    }


def _load_bundle_module():
    path = ROOT.parent / "2026_10_02_localization_benchmark" / "bundle.py"
    spec = importlib.util.spec_from_file_location("synthetic_recovery_bundle", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load bundle adapter from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_sealed_inputs(source_path=DEFAULT_SOURCE, zoom_path=DEFAULT_ZOOM):
    source_path = Path(source_path)
    zoom_path = Path(zoom_path)
    source = json.loads(source_path.read_text())
    zoom = json.loads(zoom_path.read_text())
    source_sha256 = digest(source_path)
    if zoom.get("source_fit_sha256") != source_sha256:
        raise ValueError("sealed profile zoom is not bound to the supplied coherent fit")
    if source["unit"] != zoom["unit"] or source["unit"]["unit_id"] != "DS10-S01":
        raise ValueError("sealed inputs must describe the same DS10-S01 unit")
    source_attestation = source.get("reference_read_before_seal")
    if source_attestation not in (None, False):
        raise ValueError("source fit has an incompatible truth-use attestation")
    if zoom.get("reference_read_before_seal") is not False:
        raise ValueError("profile zoom does not attest truth-free sealing")
    leader = source["fit"]["score_leader"]
    generating = zoom["fit"]["selected"]["fit"]
    satellites = np.asarray(leader["satellite_indices"], dtype=int)
    if len(satellites) != 12 or not np.array_equal(
        satellites, np.asarray(generating["satellite_indices"], dtype=int)
    ):
        raise ValueError("sealed profile zoom and source must share the frozen K12 bank")
    bundle = _load_bundle_module()
    session_id = source["unit"]["session_ids"][0]
    data = bundle.Data(ROOT / "scans" / session_id)
    if data.session_id != session_id:
        raise ValueError("bundle session does not match the frozen unit")
    anchors = [np.asarray(anchor["groups"]) for anchor in source["fit"]["anchors"]]
    return {
        "data": data,
        "generating_parameters": np.asarray(generating["parameters"], dtype=float),
        "satellites": satellites,
        "masses": leader["identity_masses"],
        "anchors": anchors,
        "source": source,
        "zoom": zoom,
        "source_sha256": source_sha256,
        "zoom_sha256": digest(zoom_path),
        "source_path": source_path,
        "zoom_path": zoom_path,
        "source_reference_attestation": source_attestation,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-fit", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--zoom-fit", type=Path, default=DEFAULT_ZOOM)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed", type=int, default=2026100216)
    parser.add_argument("--per-start-budget-s", type=float, default=12.0)
    parser.add_argument("--total-fit-budget-s", type=float, default=40.0)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")
    sealed = load_sealed_inputs(args.source_fit, args.zoom_fit)
    data = sealed["data"]
    weights = frozen_row_weights(data)
    realization = conditional_noiseless_realization(
        data,
        sealed["generating_parameters"],
        sealed["satellites"],
        sealed["masses"],
        sealed["anchors"],
        row_weights=weights,
        seed=args.seed,
    )
    audit = run_recovery_audit(
        realization,
        sealed["generating_parameters"],
        sealed["satellites"],
        sealed["masses"],
        sealed["anchors"],
        weights,
        per_start_budget_s=args.per_start_budget_s,
        total_fit_budget_s=args.total_fit_budget_s,
    )
    report = {
        "schema": "truth-free-synthetic-recovery-audit/v1",
        "unit": sealed["source"]["unit"],
        "dataset": "DS10",
        "source_fit": str(sealed["source_path"]),
        "source_fit_sha256": sealed["source_sha256"],
        "sealed_profile_zoom": str(sealed["zoom_path"]),
        "sealed_profile_zoom_sha256": sealed["zoom_sha256"],
        "reference_coordinates_read": False,
        "source_fit_reference_attestation": (
            "field absent in cohort fit schema; the sealed profile zoom explicitly records "
            "reference_read_before_seal=false and binds this source by SHA-256"
            if sealed["source_reference_attestation"] is None
            else "reference_read_before_seal=false"
        ),
        "candidate_bank": {
            "size": 12,
            "satellite_indices": sealed["satellites"],
            "catalog_numbers": np.asarray(data.numbers)[sealed["satellites"]],
            "masses_and_anchors_source": "frozen coherent-v1 DS10-S01 score leader",
        },
        "generating_parameters_source": "sealed profile-zoom-v1 DS10-S01 selected fit",
        "generating_position_km": sealed["generating_parameters"][:2],
        "synthetic_scope": realization.metadata,
        "audit": audit,
        "claim_limit": (
            "This audit checks implemented prediction, grouped likelihood, and GN recovery on a "
            "conditional synthetic realization. It does not validate the real-data model, claim "
            "an exact unconditional generator, or establish sub-kilometer real-data accuracy."
        ),
    }
    args.output.write_text(json.dumps(jsonable(report), indent=2) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "fit_elapsed_s": audit["fit_elapsed_s"],
                "completed": audit["completed_trial_count"],
                "recovered": audit["recovered_trial_count"],
                "timing_prior_shift": audit["timing_prior_diagnostic"][
                    "timing_prior_shifts_generating_map_along_shrink_path"
                ],
            }
        )
    )


if __name__ == "__main__":
    main()


__all__ = [
    "SyntheticData",
    "SyntheticRealization",
    "conditional_noiseless_realization",
    "load_sealed_inputs",
    "objective_components",
    "run_recovery_audit",
    "timing_prior_profile",
]
