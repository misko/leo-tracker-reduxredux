"""Bounded raw-only finite-set versus categorical localization pilot adapter."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from finite_set_likelihood import circular_residual, prepare_finite_set_likelihood
from gauss_newton import refine_gauss_newton
from prediction_plan import SharedPredictionPlan
from profile_seed import _validate_source_provenance
from rough_smoke import load_module, serializable
from selection import ROOT
from staged_fit import frozen_row_weights, select_trials
from track_likelihood import prepare_track_grouped_likelihood

DEFAULT_RUN_ID = "finite-set-v1"
DEFAULT_GEOMETRY_PREFLIGHT = ROOT / "finite-set-geometry-preflight.json"
DEFAULT_MEDIAN_EFFECT = ROOT / "finite-set-median-time-effect.json"
NUMERICAL_DEPENDENCIES = (
    "finite_set_fit.py",
    "finite_set_likelihood.py",
    "gauss_newton.py",
    "prediction_plan.py",
    "prediction_jacobian.py",
    "joint_inputs.py",
    "grouped_likelihood.py",
    "track_likelihood.py",
    "staged_fit.py",
    "track_seed.py",
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def array_digest(values):
    values = np.ascontiguousarray(values)
    payload = values.dtype.str.encode() + np.asarray(values.shape, dtype="<i8").tobytes()
    return hashlib.sha256(payload + values.tobytes()).hexdigest()


def snapshot_files(paths):
    snapshot = {}
    for path in paths:
        path = Path(path)
        key = str(path.resolve())
        if key in snapshot:
            raise ValueError(f"duplicate provenance path {key}")
        snapshot[key] = digest(path)
    return snapshot


def assert_snapshot_unchanged(snapshot):
    changed = [path for path, expected in snapshot.items() if digest(path) != expected]
    if changed:
        raise RuntimeError(f"fitting provenance changed before seal: {', '.join(changed)}")


class GroupMedianGeometryData:
    """Copy prediction keys and replace row times by group receive-time medians."""

    def __init__(self, source):
        self.source = source
        self.measured = np.asarray(source.measured).copy()
        self.group = np.asarray(source.group).copy()
        self.times = np.asarray(source.times, dtype=float).copy()
        self.rf = np.asarray(source.rf, dtype=float).copy()
        self.receiver = np.asarray(source.receiver, dtype=int).copy()
        self.channel = np.asarray(source.channel, dtype=int).copy()
        if any(values.ndim != 1 for values in (self.times, self.rf, self.receiver, self.group)):
            raise ValueError("prediction keys must be one-dimensional")
        if not (
            len(self.times)
            == len(self.rf)
            == len(self.receiver)
            == len(self.channel)
            == len(self.group)
            == len(self.measured)
        ):
            raise ValueError("prediction keys and measurements must align")
        source_times = self.times.copy()
        unequal_time_groups = 0
        maximum_span = 0.0
        for group_value in np.unique(self.group):
            rows = np.flatnonzero(self.group == group_value)
            frequencies = np.unique(self.rf[rows])
            receivers = np.unique(self.receiver[rows])
            channels = np.unique(self.channel[rows])
            if len(frequencies) != 1 or len(receivers) != 1 or len(channels) != 1:
                raise ValueError(
                    f"source group {group_value!r} has unequal RF, receiver, or channel keys"
                )
            row_times = self.times[rows]
            if np.any(~np.isfinite(row_times)):
                raise ValueError("source group times must be finite")
            span = float(np.ptp(row_times))
            unequal_time_groups += int(span > 0)
            maximum_span = max(maximum_span, span)
            self.times[rows] = np.median(row_times)
        self.geometry_receipt = {
            "policy": (
                "Candidate-independent median receive time per source group; exact source-group "
                "RF and receiver are required. The copied geometry is used by both finite-set and "
                "categorical-control arms so each group/satellite has one prediction."
            ),
            "source_times_sha256": array_digest(source_times),
            "adapted_times_sha256": array_digest(self.times),
            "rf_sha256": array_digest(self.rf),
            "receiver_sha256": array_digest(self.receiver),
            "channel_sha256": array_digest(self.channel),
            "group_sha256": array_digest(self.group),
            "group_count": int(len(np.unique(self.group))),
            "unequal_source_time_group_count": int(unequal_time_groups),
            "maximum_source_group_time_span_s": maximum_span,
            "changed_row_count": int(np.sum(self.times != source_times)),
            "measurements_changed": False,
            "applied_to_both_arms": True,
        }
        self._validate_groupwise_geometry()

    def _validate_groupwise_geometry(self):
        for group_value in np.unique(self.group):
            rows = self.group == group_value
            if (
                len(np.unique(self.times[rows])) != 1
                or len(np.unique(self.rf[rows])) != 1
                or len(np.unique(self.receiver[rows])) != 1
                or len(np.unique(self.channel[rows])) != 1
            ):
                raise ValueError("adapted prediction geometry is not groupwise constant")

    def __getattr__(self, name):
        return getattr(self.source, name)


def prediction_geometry_preflight(data, parameters, satellites):
    satellites = np.asarray(satellites, dtype=int)
    plan = SharedPredictionPlan(data, satellites)
    predicted, visible, _ = plan.predict(parameters)
    predicted = np.asarray(predicted).reshape(len(data.times), len(satellites))
    visible = np.asarray(visible).reshape(predicted.shape)
    maximum_circular_spread = 0.0
    conflicting_visibility_groups = 0
    for group_value in np.unique(data.group):
        rows = np.flatnonzero(data.group == group_value)
        spread = np.max(np.abs(circular_residual(predicted[rows], predicted[rows[0]])))
        maximum_circular_spread = max(maximum_circular_spread, float(spread))
        conflicting_visibility_groups += int(np.any(visible[rows] != visible[rows[0]]))
    if maximum_circular_spread > 1e-10 or conflicting_visibility_groups:
        raise ValueError("adapted data did not produce one prediction and visibility per group")
    return {
        "satellite_count": len(satellites),
        "maximum_group_prediction_circular_spread_hz": maximum_circular_spread,
        "conflicting_group_visibility_count": conflicting_visibility_groups,
        "groupwise_prediction_contract_satisfied": True,
    }


def frozen_raw_masses(selected_count, full_bank_count):
    if not isinstance(selected_count, (int, np.integer)) or selected_count <= 0:
        raise ValueError("selected_count must be a positive integer")
    if not isinstance(full_bank_count, (int, np.integer)) or full_bank_count < selected_count:
        raise ValueError("full_bank_count must be an integer at least as large as selected_count")
    per_satellite = 0.8 / full_bank_count
    return {
        "raw_satellite_mass": np.full(selected_count, per_satellite),
        "raw_background_mass": float(1 - selected_count * per_satellite),
        "anchor_satellite_mass": np.empty((0, selected_count)),
        "anchor_unknown_mass": np.empty(0),
    }


class FiniteSetLikelihoodAdapter:
    def __init__(self, prepared, detection_probability, clutter_rate=2.0):
        self.prepared = prepared
        self.detection_probability = float(detection_probability)
        self.clutter_rate = float(clutter_rate)
        self.last_result = None

    def evaluate(
        self,
        predicted,
        visible,
        *,
        sigma_hz,
        satellite_weights,
        background_mass,
        return_gradient=False,
        return_precision=False,
    ):
        satellite_count = np.asarray(predicted).shape[1]
        if np.asarray(satellite_weights).shape != (satellite_count,):
            raise ValueError("optimizer satellite weights do not match predictions")
        result = self.prepared.evaluate(
            predicted,
            visible,
            sigma_hz=sigma_hz,
            detection_probability=np.full(satellite_count, self.detection_probability),
            clutter_rate=self.clutter_rate,
            implementation="batched",
            return_gradient=return_gradient,
            return_precision=return_precision,
        )
        self.last_result = {
            **result,
            "null_support": float(np.sum(result["expected_clutter_count"])),
            "adapter_null_support_semantics": "expected finite-set clutter peak count",
            "optimizer_background_mass_argument_ignored": float(background_mass),
        }
        return self.last_result


class RawCategoricalLikelihoodAdapter:
    def __init__(self, prepared, masses):
        if prepared.anchor_count != 0:
            raise ValueError("categorical control must not contain anchors")
        self.prepared = prepared
        self.masses = masses
        self.last_result = None

    def evaluate(
        self,
        predicted,
        visible,
        *,
        sigma_hz,
        satellite_weights,
        background_mass,
        return_gradient=False,
        return_precision=False,
    ):
        self.last_result = self.prepared.evaluate(
            predicted,
            visible,
            sigma_hz=sigma_hz,
            **self.masses,
            track_contamination=0.2,
            return_gradient=return_gradient,
            return_precision=return_precision,
        )
        return self.last_result


def build_likelihood_arms(data, selected_count, full_bank_count):
    masses = frozen_raw_masses(selected_count, full_bank_count)
    finite_prepared = prepare_finite_set_likelihood(data.measured, data.group)
    control_prepared = prepare_track_grouped_likelihood(
        data.measured,
        data.group,
        row_weights=frozen_row_weights(data),
        anchors=[],
    )
    detection_probability = 0.8 / full_bank_count
    return {
        "finite_set": FiniteSetLikelihoodAdapter(
            finite_prepared,
            detection_probability=detection_probability,
            clutter_rate=2.0,
        ),
        "categorical_control": RawCategoricalLikelihoodAdapter(
            control_prepared,
            masses,
        ),
        "masses": masses,
        "detection_probability": detection_probability,
        "control_anchor_count": control_prepared.anchor_count,
    }


def _trial_diagnostics(arm, likelihood):
    result = likelihood.last_result
    if arm == "finite_set":
        return {
            "satellite_detection_probability": result["satellite_detection_probability"],
            "expected_clutter_count": result["expected_clutter_count"],
            "raw_peak_count": result["raw_peak_count"],
            "unique_peak_count": result["unique_peak_count"],
            "conditioned_nonempty": result["conditioned_nonempty"],
            "density_convention": result["density_convention"],
        }
    return {
        key: value for key, value in result.items() if "track" in key or key.endswith("group_count")
    }


def fit_raw_only_controls(
    data,
    expanded,
    *,
    budget_s_per_arm=15.0,
    refiner=refine_gauss_newton,
    prediction_preflight=prediction_geometry_preflight,
):
    if not np.isfinite(budget_s_per_arm) or not 0 < budget_s_per_arm <= 15:
        raise ValueError("budget_s_per_arm must lie in (0, 15]")
    expanded_fit = expanded["fit"]
    full_bank = np.asarray(expanded_fit["full_bank"], dtype=int)
    if len(full_bank) == 0 or len(np.unique(full_bank)) != len(full_bank):
        raise ValueError("expanded full bank must be nonempty and unique")
    geometry = data if isinstance(data, GroupMedianGeometryData) else GroupMedianGeometryData(data)
    full_trials = [
        trial
        for trial in expanded_fit["trials"]
        if np.array_equal(np.asarray(trial["satellite_indices"], dtype=int), full_bank)
    ]
    if len(full_trials) != 1:
        raise ValueError("expanded source must contain exactly one full-bank trial")
    prediction_receipt = prediction_preflight(
        geometry,
        np.asarray(full_trials[0]["parameters"], dtype=float),
        full_bank,
    )
    trials = {"finite_set": [], "categorical_control": []}
    for source_trial in expanded_fit["trials"]:
        satellites = np.asarray(source_trial["satellite_indices"], dtype=int)
        source_parameters = np.asarray(source_trial["parameters"], dtype=float)
        arms = build_likelihood_arms(geometry, len(satellites), len(full_bank))
        expected_masses = arms["masses"]
        source_masses = source_trial["identity_masses"]
        if not np.allclose(
            source_masses["raw_satellite_mass"],
            expected_masses["raw_satellite_mass"],
            rtol=0,
            atol=1e-12,
        ) or not np.isclose(
            source_masses["raw_background_mass"],
            expected_masses["raw_background_mass"],
            rtol=0,
            atol=1e-12,
        ):
            raise ValueError("expanded trial raw masses differ from the frozen full-bank scale")
        for arm in ("finite_set", "categorical_control"):
            likelihood = arms[arm]
            trial = refiner(
                geometry,
                source_parameters.copy(),
                satellites,
                np.ones(len(satellites)),
                likelihood,
                sigma_hz=200.0,
                tau_sigma_s=1.0,
                tau_bound_s=3.0,
                slope_bound=50.0,
                budget_s=float(budget_s_per_arm),
            )
            trial.pop("satellite_weights", None)
            trial["arm"] = arm
            trial["source_parameters"] = source_parameters
            trial["source_parameters_sha256"] = array_digest(source_parameters)
            trial["full_bank_count"] = len(full_bank)
            trial["per_satellite_probability"] = arms["detection_probability"]
            trial["raw_masses"] = expected_masses
            trial["anchors_used"] = 0
            trial["likelihood_diagnostics"] = _trial_diagnostics(arm, likelihood)
            trials[arm].append(trial)
    selections = {arm: select_trials(arm_trials) for arm, arm_trials in trials.items()}
    return {
        "full_bank": full_bank,
        "source_trial_count": len(expanded_fit["trials"]),
        "fitted_bank_sizes": [
            int(len(trial["satellite_indices"])) for trial in expanded_fit["trials"]
        ],
        "finite_set_trials": trials["finite_set"],
        "categorical_control_trials": trials["categorical_control"],
        "finite_set_selection": selections["finite_set"],
        "categorical_control_selection": selections["categorical_control"],
        "geometry": geometry.geometry_receipt,
        "prediction_geometry_preflight": prediction_receipt,
        "expanded_anchor_count_ignored": len(expanded_fit["anchors"]),
        "anchors_used_by_either_arm": 0,
        "same_source_seed_per_bank_and_arm": True,
        "all_expanded_ladder_banks_fitted_in_both_arms": True,
        "full_bank_trial_used_only_for_prediction_geometry_preflight": True,
        "same_optimizer_budget_per_arm_s": float(budget_s_per_arm),
        "finite_set_clutter_rate": 2.0,
        "finite_set_clutter_rate_semantics": (
            "Frozen heuristic lambda=2, not estimated from these groups and not a calibrated "
            "physical peak-count prior."
        ),
        "cross_arm_objective_ranking_performed": False,
        "scope": (
            "Matched raw-only control. Both arms use the same candidate-independent group-median "
            "prediction geometry, expanded-bank trial seeds, full-bank probability scale, sigma, "
            "tau prior, bounds, optimizer and budget. Neither arm uses dense anchors. Finite-set "
            "groups model multiple peaks jointly; categorical control retains one latent stored "
            "alternative per source group. The arms live on different sample spaces, so absolute "
            "NLL is never used to rank them; bank selection occurs only within each arm. The "
            "finite-set model is a conditional approximation, not a physically calibrated "
            "posterior. Its visibility-dependent missing-detection terms are piecewise and can "
            "favor geometries that hide candidate satellites."
        ),
    }


def _validate_external_geometry_preflight(session_id, bundle_sha256):
    receipt = json.loads(DEFAULT_GEOMETRY_PREFLIGHT.read_text())
    if receipt.get("schema") != "finite-set-geometry-preflight/v1":
        raise ValueError("unsupported finite-set geometry preflight schema")
    if (
        receipt.get("reference_coordinates_read") is not False
        or receipt.get("fits_run") is not False
    ):
        raise ValueError("geometry preflight must be truth-free and fit-free")
    matches = [row for row in receipt["rows"] if row["session"] == session_id]
    if len(matches) != 1 or matches[0]["bundle_sha256"] != bundle_sha256:
        raise ValueError("geometry preflight does not bind the frozen bundle")
    conflicts = matches[0]["conflicting_groups"]
    if any(conflicts[key] != 0 for key in ("rf", "receiver", "channel")):
        raise ValueError("geometry preflight found conflicting group metadata")
    return {
        "path": str(DEFAULT_GEOMETRY_PREFLIGHT),
        "sha256": digest(DEFAULT_GEOMETRY_PREFLIGHT),
        "row": matches[0],
    }


def _validate_median_effect(unit_id, expanded_sha256):
    receipt = json.loads(DEFAULT_MEDIAN_EFFECT.read_text())
    if receipt.get("schema") != "finite-set-median-time-effect/v1":
        raise ValueError("unsupported finite-set median-time effect schema")
    if (
        receipt.get("reference_coordinates_read") is not False
        or receipt.get("fits_run") is not False
    ):
        raise ValueError("median-time effect receipt must be truth-free and fit-free")
    matches = [row for row in receipt["units"] if row["unit_id"] == unit_id]
    if len(matches) != 1 or matches[0]["seed_fit_sha256"] != expanded_sha256:
        raise ValueError("median-time effect receipt does not bind the expanded source")
    if (
        matches[0]["visibility_changes"] != 0
        or matches[0]["maximum_within_group_prediction_span_hz"] != 0
    ):
        raise ValueError("median-time effect receipt violates groupwise geometry")
    return {
        "path": str(DEFAULT_MEDIAN_EFFECT),
        "sha256": digest(DEFAULT_MEDIAN_EFFECT),
        "row": matches[0],
    }


def _load_sources(unit_id):
    expanded_path = ROOT / "runs" / "expanded-bank-v1" / unit_id / "fit.json"
    dense_path = ROOT / "runs" / "dense-anchor-v1" / unit_id / "fit.json"
    expanded = json.loads(expanded_path.read_text())
    dense = json.loads(dense_path.read_text())
    if expanded.get("stage") != "expanded_bank" or expanded["unit"]["unit_id"] != unit_id:
        raise ValueError("expanded source has the wrong stage or unit")
    if expanded.get("reference_read_before_seal") is not False:
        raise ValueError("expanded source lacks truth-free sealing")
    if dense.get("stage") != "dense_anchor" or dense.get("reference_read_before_seal") is not False:
        raise ValueError("dense source lacks standard truth-free sealing")
    if expanded["source_fit_sha256"] != digest(dense_path):
        raise ValueError("expanded source is not bound to the dense source")
    return {
        "expanded": expanded,
        "expanded_path": expanded_path,
        "expanded_sha256": digest(expanded_path),
        "dense_path": dense_path,
        "dense_sha256": digest(dense_path),
        "source_validation": _validate_source_provenance(dense),
    }


def run_case(unit_id, run_id, *, budget_s_per_arm=15.0):
    sources = _load_sources(unit_id)
    expanded = sources["expanded"]
    bundle = load_module(
        f"finite_set_bundle_{unit_id}",
        ROOT.parent / "2026_10_02_localization_benchmark" / "bundle.py",
    )
    session_id = expanded["unit"]["session_ids"][0]
    source_data = bundle.Data(ROOT / "scans" / session_id)
    data = GroupMedianGeometryData(source_data)
    bundle_directory = ROOT / "scans" / session_id
    bundle_sha256 = digest(bundle_directory / "bundle.npz")
    geometry_preflight = _validate_external_geometry_preflight(session_id, bundle_sha256)
    median_effect = _validate_median_effect(unit_id, sources["expanded_sha256"])
    output = ROOT / "runs" / run_id / unit_id
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    source_paths = [ROOT / name for name in NUMERICAL_DEPENDENCIES]
    source_paths.append(ROOT.parent / "2026_10_02_localization_benchmark" / "bundle.py")
    source_snapshot = snapshot_files(source_paths)
    artifact_snapshot = snapshot_files(
        [
            sources["expanded_path"],
            sources["dense_path"],
            DEFAULT_GEOMETRY_PREFLIGHT,
            DEFAULT_MEDIAN_EFFECT,
            bundle_directory / "bundle.json",
            bundle_directory / "bundle.npz",
        ]
    )
    started = time.monotonic()
    fitted = fit_raw_only_controls(
        data,
        expanded,
        budget_s_per_arm=budget_s_per_arm,
    )
    assert_snapshot_unchanged(source_snapshot)
    assert_snapshot_unchanged(artifact_snapshot)
    receipt = {
        "schema": "finite-set-raw-control-fit/v1",
        "stage": "finite_set_raw_control",
        "unit": expanded["unit"],
        "dataset": "DS10" if unit_id.startswith("DS10-") else "DS11",
        "run_id": run_id,
        "expanded_fit": str(sources["expanded_path"]),
        "expanded_fit_sha256": sources["expanded_sha256"],
        "dense_fit": str(sources["dense_path"]),
        "dense_fit_sha256": sources["dense_sha256"],
        "source_validation": sources["source_validation"],
        "geometry_preflight": geometry_preflight,
        "median_time_effect": median_effect,
        "source_hashes_prefit": source_snapshot,
        "bound_artifact_hashes_prefit": artifact_snapshot,
        "prefit_hashes_reverified_unchanged_before_seal": True,
        "configuration": {
            "sigma_hz": 200.0,
            "tau_sigma_s": 1.0,
            "tau_bound_s": 3.0,
            "slope_bound_hz_s": 50.0,
            "finite_set_clutter_rate": 2.0,
            "finite_set_clutter_rate_role": "frozen heuristic, not estimated or calibrated",
            "finite_set_implementation": "batched",
            "full_bank_signal_or_detection_mass": 0.8,
            "budget_s_per_bank_per_arm": float(budget_s_per_arm),
            "optimizer": "complete-data-fisher-gn/v2",
        },
        "reference_read_before_seal": False,
        "evaluation_written": False,
        "eligible_for_cohort": False,
        "cross_arm_absolute_nll_ranking": False,
        "finite_set_conditional_approximation": True,
        "elapsed_s": time.monotonic() - started,
        "fit": fitted,
        "sealed_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    output.mkdir(parents=True, exist_ok=False)
    fit_path = output / "fit.json"
    fit_path.write_text(json.dumps(serializable(receipt), indent=2) + "\n")
    return fit_path, receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("unit_id", choices=("DS10-S01", "DS11-S02"))
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--budget-s-per-arm", type=float, default=15.0)
    args = parser.parse_args()
    if not args.run_id or Path(args.run_id).name != args.run_id or args.run_id in (".", ".."):
        parser.error("run-id must be one path component")
    if not 0 < args.budget_s_per_arm <= 15:
        parser.error("budget-s-per-arm must lie in (0, 15]")
    fit_path, receipt = run_case(
        args.unit_id,
        args.run_id,
        budget_s_per_arm=args.budget_s_per_arm,
    )
    print(
        json.dumps(
            {
                "unit_id": args.unit_id,
                "fit": str(fit_path),
                "fit_sha256": digest(fit_path),
                "elapsed_s": receipt["elapsed_s"],
                "finite_set_leader_k": receipt["fit"]["finite_set_selection"]["score_leader"][
                    "satellite_count"
                ],
                "control_leader_k": receipt["fit"]["categorical_control_selection"]["score_leader"][
                    "satellite_count"
                ],
            }
        )
    )


if __name__ == "__main__":
    main()


__all__ = [
    "FiniteSetLikelihoodAdapter",
    "GroupMedianGeometryData",
    "RawCategoricalLikelihoodAdapter",
    "build_likelihood_arms",
    "fit_raw_only_controls",
    "frozen_raw_masses",
    "run_case",
]
