"""Matched blind sensitivity to uncalibrated orbital-phase prior floors."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from localize_merged_track_catalogue import distance_km
from search_fixed_satellite_families import locate
from transfer_fixed_satellite_families import FixedFamilies


def run(case, fitted_c, floor_s, output):
    if floor_s not in (0.0, 1.0, 3.0):
        raise ValueError("declared prior-floor sensitivity is 0, 1 or 3 seconds")
    study = FixedFamilies(case, fitted_c, False, phase_bound_floor_s=15)
    original_sigma = study.sigma.copy()
    study.sigma = np.maximum(study.sigma, floor_s)
    output.mkdir(parents=True, exist_ok=False)
    write(
        output / "protocol.json",
        dict(
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            fit_source_sha256=hashlib.sha256(
                Path(__file__).with_name("transfer_fixed_satellite_families.py").read_bytes()
            ).hexdigest(),
            source_blind_fit_sha256=study.source_digest,
            source_blind_association_sha256=study.association_digest,
            case=case,
            fitted_c=fitted_c,
            phase_sigma_floor_s=floor_s,
            original_phase_sigma_s=original_sigma,
            phase_sigma_s=study.sigma,
            phase_bounds_s=study.bounds,
            all_phase_boxes_fixed_to_15_seconds=True,
            drift_sigma_hz_s=0.5,
            drift_bound_hz_s=1,
            original_measured_rf_used_for_doppler=True,
            hardware_rf_c_feature_unchanged=True,
            no_known_position_parameters_read=True,
            actual_observations_labels_times_rf_and_initial_states_matched=True,
            c0_fitted_c_priors_and_73_location_search_budgets_matched=True,
            only_individually_measured_curved_fragments_calibrate=True,
            no_curved_points_rejected_from_fitting=True,
            sensitivity_priors_are_not_calibrated_covariances=True,
            evaluation_position_used_in_search=False,
        ),
    )
    started = time.monotonic()
    result = locate(study, output)
    fit = result["endpoint"]
    digest = hashlib.sha256((output / "fit.json").read_bytes()).hexdigest()
    error = distance_km(
        (fit["latitude_deg"], fit["longitude_deg"]), (37.849061591561885, -122.48574968092912)
    )
    write(
        output / "evaluation.json",
        dict(
            position_error_km=error,
            fit_sha256=digest,
            reference_used_only_after_fit=True,
            within_0_5km=error < 0.5,
            sensitivity_not_a_qualified_or_full_corpus_accuracy_result=True,
        ),
    )
    known = study.fit(37.849061591561885, -122.48574968092912)
    write(output / "known_position_diagnostic.json", known)
    summary = dict(
        case=case,
        fitted_c=fitted_c,
        phase_sigma_floor_s=floor_s,
        position_error_km=error,
        score=fit["score"],
        rms_hz=fit["detail"]["overall_rms_hz"],
        compatible_curved_points=fit["detail"]["member_compatible_points"],
        fixed_curved_points=len(study.observation_ids),
        known_position_rms_hz=known["detail"]["overall_rms_hz"],
        known_position_score=known["score"],
        known_position_compatible_points=known["detail"]["member_compatible_points"],
        locations=result["locations"],
        elapsed_seconds=time.monotonic() - started,
    )
    write(output / "summary.json", summary)
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", choices=("DSX01-S01", "DS22-001"), required=True)
    p.add_argument("--fitted-c", action="store_true")
    p.add_argument("--phase-sigma-floor-s", type=float, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if Path("/mnt/qnap01") in (a.output.resolve(), *a.output.resolve().parents):
        p.error("QNAP is read-only")
    run(a.case, a.fitted_c, a.phase_sigma_floor_s, a.output)
