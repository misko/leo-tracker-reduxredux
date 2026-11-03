"""Causal TLE-revision width prototype for the frozen DS10-S01 bank ladder."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from selection import ROOT

BASE_SIGMA_HZ = 200.0
SHIFT_BOUND_S = 20.0
LIGHT_SPEED_KM_S = 299_792.458
DEFAULT_TLE_ROOT = Path("/var/lib/leo/tle")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def effective_orbit_sigmas(orbit_rms_hz, *, base_sigma_hz=BASE_SIGMA_HZ):
    """Return immutable quadrature widths for one frozen candidate bank."""

    widths = np.asarray(orbit_rms_hz, dtype=float)
    if widths.ndim != 1 or len(widths) == 0:
        raise ValueError("orbit_rms_hz must be a nonempty vector")
    if np.any(~np.isfinite(widths)) or np.any(widths < 0):
        raise ValueError("orbit_rms_hz must be finite and non-negative")
    if not np.isfinite(base_sigma_hz) or base_sigma_hz <= 0:
        raise ValueError("base_sigma_hz must be positive and finite")
    result = np.sqrt(float(base_sigma_hz) ** 2 + widths**2)
    result.setflags(write=False)
    return result


def diagnostic_orbit_widths(document):
    """Extract aligned robust RMS values without removing constant bias."""

    if document.get("schema") != "tle-time-alignment-diagnostic/v1":
        raise ValueError("unsupported orbit-width diagnostic schema")
    constraints = document.get("constraints", {})
    if constraints.get("reference_coordinates_read") is not False:
        raise ValueError("orbit-width diagnostic must not read reference coordinates")
    if constraints.get("future_tle_used") is not False:
        raise ValueError("orbit-width diagnostic must not use a future TLE")
    widths = {}
    for satellite in document.get("satellites", []):
        number = int(satellite["catalog_number"])
        if number in widths:
            raise ValueError(f"duplicate orbit width for catalog {number}")
        value = satellite["aligned_doppler_hz"]["raw_zero_frequency_adjustment"][
            "trimmed_95_rms"
        ]
        value = float(value)
        if not np.isfinite(value) or value < 0:
            raise ValueError(f"invalid orbit width for catalog {number}")
        widths[number] = value
    if not widths:
        raise ValueError("orbit-width diagnostic contains no satellite widths")
    return widths


class OrbitWidthLikelihood:
    """Adapter that freezes one normalized signal width per prediction column."""

    def __init__(self, prepared, masses, sigma_hz, *, base_sigma_hz=BASE_SIGMA_HZ):
        sigma_hz = np.asarray(sigma_hz, dtype=float)
        if sigma_hz.ndim != 1 or len(sigma_hz) == 0:
            raise ValueError("sigma_hz must be a nonempty vector")
        if np.any(~np.isfinite(sigma_hz)) or np.any(sigma_hz <= 0):
            raise ValueError("sigma_hz must be positive and finite")
        if not np.isfinite(base_sigma_hz) or base_sigma_hz <= 0:
            raise ValueError("base_sigma_hz must be positive and finite")
        self.prepared = prepared
        self.masses = masses
        self._sigma_hz = tuple(float(value) for value in sigma_hz)
        self.base_sigma_hz = float(base_sigma_hz)
        self.last_result = None

    @property
    def sigma_hz(self):
        values = np.asarray(self._sigma_hz, dtype=float)
        values.setflags(write=False)
        return values

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
        predicted = np.asarray(predicted)
        if predicted.ndim != 2 or predicted.shape[1] != len(self._sigma_hz):
            raise ValueError("prediction columns do not match frozen orbit widths")
        if not np.isfinite(sigma_hz) or float(sigma_hz) != self.base_sigma_hz:
            raise ValueError("optimizer sigma_hz differs from the frozen base width")
        self.last_result = self.prepared.evaluate(
            predicted,
            visible,
            sigma_hz=self.sigma_hz,
            **self.masses,
            track_contamination=0.2,
            return_gradient=return_gradient,
            return_precision=return_precision,
        )
        return self.last_result


def _coordinates_to_ecef(latitude_deg, longitude_deg):
    latitude, longitude = np.deg2rad([latitude_deg, longitude_deg])
    flattening = 1 / 298.257223563
    eccentricity = flattening * (2 - flattening)
    radius = 6378.137 / np.sqrt(1 - eccentricity * np.sin(latitude) ** 2)
    return np.asarray(
        [
            radius * np.cos(latitude) * np.cos(longitude),
            radius * np.cos(latitude) * np.sin(longitude),
            radius * (1 - eccentricity) * np.sin(latitude),
        ]
    )


def _group_geometry(data):
    group_values = np.unique(data.group)
    event_times = []
    event_rf = []
    spans = []
    for group in group_values:
        rows = np.flatnonzero(data.group == group)
        if not np.allclose(data.rf[rows], data.rf[rows[0]], rtol=0, atol=1e-6):
            raise ValueError(f"source group {group} has inconsistent RF")
        event_times.append(float(np.median(data.times[rows])))
        event_rf.append(float(data.rf[rows[0]]))
        spans.append(float(np.ptp(data.times[rows])))
    return np.asarray(event_times), np.asarray(event_rf), np.asarray(spans)


def _propagate_one(catalogue, index, origin_utc_ns, times_s, shift_s=0.0):
    from leo.sky.frames import (
        greenwich_mean_sidereal_time_rad,
        julian_day_from_utc_ns,
        teme_to_ecef,
    )
    from leo.sky.propagation import propagate_grid
    from leo.sky.sampling import SamplingGrid

    utc_ns = origin_utc_ns + np.rint(
        (np.asarray(times_s, dtype=float) + float(shift_s)) * 1e9
    ).astype(np.int64)
    state = propagate_grid(
        catalogue,
        SamplingGrid(tuple(int(value) for value in utc_ns), 0, 1.0),
        [index],
    )
    if np.any(state.error_code):
        raise RuntimeError("selected satellite failed causal TLE propagation")
    julian_day, fraction = julian_day_from_utc_ns(utc_ns)
    position_ecef, velocity_ecef = teme_to_ecef(
        state.position_teme_km,
        state.velocity_teme_km_s,
        greenwich_mean_sidereal_time_rad(julian_day, fraction)[None, :],
    )
    return (
        np.asarray(state.position_teme_km[0]),
        np.asarray(position_ecef[0]),
        np.asarray(velocity_ecef[0]),
    )


def _trimmed_95_rms(values):
    values = np.asarray(values, dtype=float)
    threshold = np.percentile(np.abs(values), 95)
    retained = values[np.abs(values) <= threshold]
    return float(np.sqrt(np.mean(retained**2)))


def _derive_causal_widths(
    data,
    catalog_numbers,
    *,
    origin_utc_ns,
    observer_lat_lon_deg,
    pinned_snapshot,
    previous_snapshot,
    tle_root,
):
    from scipy.optimize import minimize_scalar

    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_sets

    reader = TleArchiveReader(Path(tle_root))
    references = reader.list_snapshots(pinned_snapshot["provider"])

    def resolve(document):
        digest_value = document["digest"].removeprefix("sha256:")
        matches = [
            reference
            for reference in references
            if reference.collected_utc_ns == int(document["collected_utc_ns"])
            and reference.sha256 == digest_value
        ]
        if len(matches) != 1:
            raise ValueError("orbit diagnostic snapshot is not uniquely archived")
        return matches[0]

    pinned_reference = resolve(pinned_snapshot)
    previous_reference = resolve(previous_snapshot)
    if not previous_reference.collected_utc_ns < pinned_reference.collected_utc_ns < origin_utc_ns:
        raise ValueError("orbit-width snapshots must both be causal")
    pinned_catalogue = parse_element_sets(reader.read(pinned_reference))
    previous_catalogue = parse_element_sets(reader.read(previous_reference))
    pinned_lookup = {
        int(number): index for index, number in enumerate(pinned_catalogue.satellite_numbers)
    }
    previous_lookup = {
        int(number): index for index, number in enumerate(previous_catalogue.satellite_numbers)
    }
    event_times, event_rf, alternative_spans = _group_geometry(data)
    alignment_times = np.unique(event_times)
    observer = _coordinates_to_ecef(*observer_lat_lon_deg)
    latitude, longitude = np.deg2rad(observer_lat_lon_deg)
    up = np.asarray(
        [
            np.cos(latitude) * np.cos(longitude),
            np.cos(latitude) * np.sin(longitude),
            np.sin(latitude),
        ]
    )
    output = {}
    for catalog_number in catalog_numbers:
        catalog_number = int(catalog_number)
        if catalog_number not in pinned_lookup or catalog_number not in previous_lookup:
            raise ValueError(f"catalog {catalog_number} is absent from a causal snapshot")
        reference_teme, _, _ = _propagate_one(
            pinned_catalogue,
            pinned_lookup[catalog_number],
            origin_utc_ns,
            alignment_times,
        )

        def position_loss(shift_s):
            previous_teme, _, _ = _propagate_one(
                previous_catalogue,
                previous_lookup[catalog_number],
                origin_utc_ns,
                alignment_times,
                shift_s,
            )
            difference = previous_teme - reference_teme
            return float(np.mean(np.sum(difference**2, axis=1)))

        optimum = minimize_scalar(
            position_loss,
            bounds=(-SHIFT_BOUND_S, SHIFT_BOUND_S),
            method="bounded",
            options={"xatol": 1e-5, "maxiter": 80},
        )
        shift_s = float(optimum.x)
        if not optimum.success or abs(shift_s) >= SHIFT_BOUND_S - 1e-3:
            raise RuntimeError(f"catalog {catalog_number} causal time alignment did not resolve")
        _, pinned_position, pinned_velocity = _propagate_one(
            pinned_catalogue,
            pinned_lookup[catalog_number],
            origin_utc_ns,
            event_times,
        )
        _, previous_position, previous_velocity = _propagate_one(
            previous_catalogue,
            previous_lookup[catalog_number],
            origin_utc_ns,
            event_times,
            shift_s,
        )

        def doppler(position, velocity):
            delta = position - observer
            distance = np.linalg.norm(delta, axis=1)
            return (
                -event_rf * np.sum(delta * velocity, axis=1) / distance / LIGHT_SPEED_KM_S,
                delta,
                distance,
            )

        pinned_frequency, delta, distance = doppler(pinned_position, pinned_velocity)
        previous_frequency, _, _ = doppler(previous_position, previous_velocity)
        visible = np.sum(delta * up, axis=1) / distance >= 0
        if np.sum(visible) < 3:
            raise RuntimeError(f"catalog {catalog_number} has insufficient visible groups")
        residual = pinned_frequency[visible] - previous_frequency[visible]
        output[catalog_number] = {
            "orbit_rms_hz": _trimmed_95_rms(residual),
            "time_shift_s": shift_s,
            "position_rms_before_km": float(np.sqrt(position_loss(0.0))),
            "position_rms_after_km": float(np.sqrt(optimum.fun)),
            "visible_group_count": int(np.sum(visible)),
            "alternative_time_span_max_s": float(np.max(alternative_spans)),
        }
    return output


def _validate_expanded_source(source, source_path):
    if source.get("stage") != "expanded_bank":
        raise ValueError("source fit must be expanded-bank-v1")
    unit = source.get("unit", {})
    if unit.get("unit_id") != "DS10-S01" or unit.get("size") != 1:
        raise ValueError("orbit-width prototype is restricted to DS10-S01")
    if source.get("reference_read_before_seal") is not False:
        raise ValueError("expanded source must be sealed before reference evaluation")
    trials = source.get("fit", {}).get("trials", [])
    full_bank = np.asarray(source.get("fit", {}).get("full_bank"), dtype=int)
    if not trials or full_bank.ndim != 1 or not len(full_bank):
        raise ValueError("expanded source lacks a frozen bank ladder")
    for trial in trials:
        satellites = np.asarray(trial.get("satellite_indices"), dtype=int)
        if not np.array_equal(satellites, full_bank[: len(satellites)]):
            raise ValueError("expanded trials are not prefixes of one frozen bank")
        if "identity_masses" not in trial:
            raise ValueError("expanded trial lacks frozen identity masses")
    return unit, trials, full_bank


def fit_orbit_widths(data, source, diagnostic, *, budget_s=20.0, tle_root=DEFAULT_TLE_ROOT):
    """Refit every expanded prefix with frozen causal-revision widths."""

    from gauss_newton import refine_gauss_newton
    from staged_fit import frozen_row_weights, select_trials
    from track_likelihood import prepare_track_grouped_likelihood

    if not np.isfinite(budget_s) or not 0 < budget_s <= 20:
        raise ValueError("budget_s must lie in (0, 20]")
    unit, source_trials, full_bank = _validate_expanded_source(source, "expanded source")
    direct_widths = diagnostic_orbit_widths(diagnostic)
    full_numbers = np.asarray(data.numbers)[full_bank]
    missing = [int(number) for number in full_numbers if int(number) not in direct_widths]
    sentinel = 64136
    supplement_numbers = [sentinel, *missing]
    supplement_numbers = list(dict.fromkeys(supplement_numbers))
    bindings = diagnostic["bindings"]
    supplement = _derive_causal_widths(
        data,
        supplement_numbers,
        origin_utc_ns=int(unit["origin_utc_ns"]),
        observer_lat_lon_deg=bindings["observer_lat_lon_deg"],
        pinned_snapshot={"provider": "space-track", **bindings["pinned_snapshot"]},
        previous_snapshot={
            "provider": "space-track",
            **bindings["previous_causal_distinct_snapshot"],
        },
        tle_root=tle_root,
    )
    if sentinel not in direct_widths:
        raise ValueError("orbit diagnostic lacks the 64136 parity sentinel")
    if not np.isclose(
        supplement[sentinel]["orbit_rms_hz"],
        direct_widths[sentinel],
        rtol=0,
        atol=1e-8,
    ):
        raise ValueError("causal-width supplement does not reproduce the sealed sentinel")
    all_widths = dict(direct_widths)
    for number in missing:
        all_widths[number] = supplement[number]["orbit_rms_hz"]
    orbit_rms = np.asarray([all_widths[int(number)] for number in full_numbers])
    sigma_eff = effective_orbit_sigmas(orbit_rms)

    anchors = source["fit"]["anchors"]
    prepared = prepare_track_grouped_likelihood(
        data.measured,
        data.group,
        row_weights=frozen_row_weights(data),
        anchors=[np.asarray(anchor["groups"]) for anchor in anchors],
    )
    trials = []
    for source_trial in source_trials:
        satellites = np.asarray(source_trial["satellite_indices"], dtype=int)
        if not np.array_equal(satellites, full_bank[: len(satellites)]):
            raise ValueError("source trial bank changed after validation")
        column_sigma = sigma_eff[: len(satellites)]
        likelihood = OrbitWidthLikelihood(
            prepared,
            source_trial["identity_masses"],
            column_sigma,
        )
        initial = np.asarray(source_trial["parameters"], dtype=float)
        support = np.asarray(source_trial["satellite_support"], dtype=float)
        trial = refine_gauss_newton(
            data,
            initial,
            satellites,
            support,
            likelihood,
            sigma_hz=BASE_SIGMA_HZ,
            tau_sigma_s=1.0,
            tau_bound_s=3.0,
            budget_s=float(budget_s),
        )
        trial.pop("satellite_weights")
        trial["identity_masses"] = source_trial["identity_masses"]
        trial["orbit_revision_rms_hz"] = orbit_rms[: len(satellites)]
        trial["effective_sigma_hz"] = column_sigma
        trial["source_seed"] = {
            "objective": source_trial["objective"],
            "selection_score": source_trial["selection_score"],
            "status": source_trial["status"],
        }
        trial["likelihood_diagnostics"] = {
            key: value
            for key, value in likelihood.last_result.items()
            if "track" in key or key.endswith("group_count")
        }
        trials.append(trial)
    return {
        "rough": source["fit"]["rough"],
        "anchors": anchors,
        "full_bank": full_bank,
        "full_bank_catalog_numbers": full_numbers,
        "orbit_revision_rms_hz": orbit_rms,
        "effective_sigma_hz": sigma_eff,
        "width_sources": [
            {
                "catalog_number": int(number),
                "source": "sealed_alignment_diagnostic"
                if int(number) in direct_widths
                else "same_method_causal_supplement",
            }
            for number in full_numbers
        ],
        "supplement": {str(number): supplement[number] for number in missing},
        "sentinel_recomputed": supplement[sentinel],
        "trials": trials,
        **select_trials(trials),
        "bank_branches_independent": True,
        "bank_selection_reevaluated": True,
        "scope": (
            "DS10-S01-only causal TLE revision-sensitivity heuristic. Per-satellite widths are "
            "frozen before fitting as sqrt(200^2 + aligned robust-RMS^2), including constant "
            "revision bias because the fitted model has no satellite-frequency intercept. "
            "Widths are not calibrated uncertainties; independent Gaussian errors are an "
            "approximation that ignores correlated orbit errors. Expanded-bank prefixes, "
            "anchors, masses, and corresponding sealed seeds are unchanged."
        ),
    }


def run_case(expanded_fit_path, diagnostic_path, run_id, budget_s, tle_root):
    from rough_smoke import load_module, serializable

    expanded_fit_path = Path(expanded_fit_path)
    diagnostic_path = Path(diagnostic_path)
    source = json.loads(expanded_fit_path.read_text())
    diagnostic = json.loads(diagnostic_path.read_text())
    unit, _, _ = _validate_expanded_source(source, expanded_fit_path)
    if not run_id or Path(run_id).name != run_id or run_id in (".", ".."):
        raise ValueError("run_id must be one path component")
    output = ROOT / "runs" / run_id / unit["unit_id"]
    output.mkdir(parents=True, exist_ok=False)
    sources = {
        path.name: digest(path)
        for path in sorted(ROOT.glob("*.py"))
        if not path.name.startswith("test_")
    }
    bundle = load_module(
        "orbit_width_bundle", ROOT.parent / "2026_10_02_localization_benchmark/bundle.py"
    )
    data = bundle.Data(ROOT / "scans" / unit["session_ids"][0])
    bundle_path = ROOT / "scans" / unit["session_ids"][0] / "bundle.npz"
    expected_bundle = diagnostic.get("bindings", {}).get("bundle_npz_sha256")
    if expected_bundle != digest(bundle_path):
        raise ValueError("orbit diagnostic does not bind the DS10 source bundle")

    started = time.monotonic()
    fitted = fit_orbit_widths(
        data,
        source,
        diagnostic,
        budget_s=float(budget_s),
        tle_root=Path(tle_root),
    )
    receipt = {
        "schema": "multiscan-orbit-width-fit/v1",
        "stage": "orbit_width",
        "unit": unit,
        "run_id": run_id,
        "expanded_fit": str(expanded_fit_path),
        "expanded_fit_sha256": digest(expanded_fit_path),
        "orbit_diagnostic": str(diagnostic_path),
        "orbit_diagnostic_sha256": digest(diagnostic_path),
        "source_hashes": sources,
        "configuration": {
            "base_sigma_hz": BASE_SIGMA_HZ,
            "width_formula": "sqrt(base_sigma_hz^2 + aligned_trimmed_95_rms_hz^2)",
            "width_includes_constant_revision_bias": True,
            "tau_sigma_s": 1.0,
            "tau_bound_s": 3.0,
            "budget_s_per_bank": float(budget_s),
            "optimizer": "complete-data-fisher-gn/v2",
            "normalized_gaussian_density": True,
            "independent_orbit_error_approximation": True,
            "correlated_orbit_errors_modeled": False,
        },
        "width_position_conditioning": {
            "source": "sealed estimated observer from tle-time-alignment-diagnostic/v1",
            "east_north_km": diagnostic["bindings"]["observer_east_north_km"],
            "latitude_longitude_deg": diagnostic["bindings"]["observer_lat_lon_deg"],
            "reference_coordinates_used": False,
        },
        "reference_read_before_seal": False,
        "eligible_for_cohort": False,
        "elapsed_s": time.monotonic() - started,
        "fit": fitted,
        "sealed_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    fit_path = output / "fit.json"
    fit_path.write_text(json.dumps(serializable(receipt), indent=2) + "\n")
    fit_sha256 = digest(fit_path)

    reference_path = ROOT / "scans" / unit["session_ids"][0] / "evaluation.json"
    reference = json.loads(reference_path.read_text())["reference_site"]
    expected = bundle._COMMON.ecef(reference["latitude_deg"], reference["longitude_deg"])
    trial_errors = []
    for trial in fitted["trials"]:
        estimated = bundle._COMMON.ecef(*bundle._COMMON.coordinates(trial["parameters"][:2]))
        trial_errors.append(
            {
                "satellite_count": trial["satellite_count"],
                "objective": trial["objective"],
                "selection_score": trial["selection_score"],
                "success": trial["success"],
                "status": trial["status"],
                "convergence_reason": trial["convergence_reason"],
                "reference_error_km": float(np.linalg.norm(estimated - expected)),
            }
        )
    evaluation = {
        "schema": "multiscan-orbit-width-evaluation/v1",
        "unit_id": unit["unit_id"],
        "fit_sha256": fit_sha256,
        "trial_reference_errors": trial_errors,
        "objective_selected_satellite_count": fitted["score_leader"]["satellite_count"],
        "selection_resolved": fitted["selection_resolved"],
        "eligible_for_cohort": False,
        "scope": (
            "Post-seal reference evaluation only. Reference coordinates did not select widths, "
            "banks, anchors, masses, starts, hyperparameters, or the objective leader."
        ),
    }
    (output / "evaluation.json").write_text(json.dumps(evaluation, indent=2) + "\n")
    return receipt, evaluation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--expanded-fit", required=True, type=Path)
    parser.add_argument("--orbit-diagnostic", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--budget-s", type=float, default=20.0)
    parser.add_argument("--tle-root", type=Path, default=DEFAULT_TLE_ROOT)
    args = parser.parse_args()
    receipt, evaluation = run_case(
        args.expanded_fit,
        args.orbit_diagnostic,
        args.run_id,
        args.budget_s,
        args.tle_root,
    )
    print(
        json.dumps(
            {
                "unit_id": receipt["unit"]["unit_id"],
                "fit_sha256": evaluation["fit_sha256"],
                "selection_resolved": receipt["fit"]["selection_resolved"],
                "objective_selected_satellite_count": evaluation[
                    "objective_selected_satellite_count"
                ],
                "trial_reference_errors": evaluation["trial_reference_errors"],
            }
        )
    )


if __name__ == "__main__":
    main()
