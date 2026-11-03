"""Blind common-position pilot with independent scan-local calibration states."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from localize_merged_track_catalogue import distance_km
from search_fixed_satellite_families import locate
from transfer_fixed_satellite_families import FixedFamilies


class CommonPosition:
    """One geographic hypothesis; each scan retains all its own nuisance terms."""

    def __init__(self, studies):
        self.studies = studies
        self.receipt = dict(studies[0].receipt)
        # The seed uses only earlier blind estimates, never GPS or fixed-site fits.
        self.source_fit = {
            field: float(np.mean([study.source_fit[field] for study in studies]))
            for field in ("latitude_deg", "longitude_deg")
        }

    def fit(self, latitude, longitude):
        scans = [study.fit(latitude, longitude) for study in self.studies]
        points = [fit["detail"]["total_points"] for fit in scans]
        return dict(
            latitude_deg=latitude,
            longitude_deg=longitude,
            score=sum(fit["score"] for fit in scans),
            scans=scans,
            detail=dict(
                overall_rms_hz=float(
                    np.sqrt(
                        sum(
                            n * fit["detail"]["overall_rms_hz"] ** 2
                            for n, fit in zip(points, scans, strict=True)
                        )
                        / sum(points)
                    )
                ),
                member_compatible_points=sum(
                    fit["detail"]["member_compatible_points"] for fit in scans
                ),
                total_points=sum(points),
            ),
        )


def run(fitted_c, output):
    cases = ["DSX01-S01", "DS22-001"]
    studies = [FixedFamilies(case, fitted_c, False) for case in cases]
    study = CommonPosition(studies)
    output.mkdir(parents=True, exist_ok=False)
    write(
        output / "protocol.json",
        dict(
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            fixed_family_source_sha256=hashlib.sha256(
                Path(__file__).with_name("transfer_fixed_satellite_families.py").read_bytes()
            ).hexdigest(),
            search_source_sha256=hashlib.sha256(
                Path(__file__).with_name("search_fixed_satellite_families.py").read_bytes()
            ).hexdigest(),
            cases=cases,
            fitted_c=fitted_c,
            hypothesis="two recordings share one stationary position",
            scan_local_offsets_drifts_component_constants_and_satellite_phases=True,
            no_cross_scan_frequency_or_phase_calibration_tied=True,
            source_blind_fit_sha256=[s.source_digest for s in studies],
            source_blind_association_sha256=[s.association_digest for s in studies],
            observation_ids=[s.observation_ids for s in studies],
            candidate_norads=[s.norads for s in studies],
            labels=[s.labels for s in studies],
            phase_sigma_s=[s.sigma for s in studies],
            phase_bounds_s=[s.bounds for s in studies],
            only_individually_measured_curved_fragments_calibrate=True,
            every_fixed_point_contributes_and_no_label_or_point_is_rejected=True,
            c_pair_same_points_candidates_initializers_priors_and_search_budget=True,
            maximum_locations=73,
            maximum_local_sweeps=2,
            nonlinear_iterations_per_scan_per_initializer=6,
            phase_initializers_per_scan=2,
            drift_sigma_hz_s=0.5,
            drift_bound_hz_s=1,
            evaluation_position_used_in_search=False,
            same_site_hypothesis_requires_physical_validation=True,
        ),
    )
    result = locate(study, output)
    fit = result["endpoint"]
    digest = hashlib.sha256((output / "fit.json").read_bytes()).hexdigest()
    # Evaluation begins only after writing the independent estimate.
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
            not_whole_ds22_or_independent_identity_validation=True,
        ),
    )
    summary = dict(
        cases=cases,
        fitted_c=fitted_c,
        position_error_km=error,
        rms_hz=fit["detail"]["overall_rms_hz"],
        fixed_curved_points=fit["detail"]["total_points"],
        compatible_curved_points=fit["detail"]["member_compatible_points"],
        per_scan_rms_hz=[f["detail"]["overall_rms_hz"] for f in fit["scans"]],
        per_scan_compatible_points=[f["detail"]["member_compatible_points"] for f in fit["scans"]],
        locations=result["locations"],
        local_search_not_global_optimum=True,
        not_a_fully_qualified_localization_result=True,
    )
    write(output / "summary.json", summary)
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fitted-c", action="store_true")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if Path("/mnt/qnap01") in (args.output.resolve(), *args.output.resolve().parents):
        parser.error("QNAP is read-only")
    run(args.fitted_c, args.output)
