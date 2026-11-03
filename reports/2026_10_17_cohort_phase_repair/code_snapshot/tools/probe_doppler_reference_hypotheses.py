"""Explicit Doppler-coefficient sensitivities preserving actual RF and hardware c."""

import argparse
import hashlib
import json
import time
from pathlib import Path

from associate_merged_track_catalogue import write
from localize_merged_track_catalogue import distance_km
from search_fixed_satellite_families import locate
from transfer_fixed_satellite_families import FixedFamilies

FACTORS = {"sampled_edge": 1, "edge_midpoint": 0, "double_edge_offset": 2}


class ReferenceHypothesis(FixedFamilies):
    def __init__(self, case, fitted_c, hypothesis):
        self.hypothesis, self.edge_factor = hypothesis, FACTORS[hypothesis]
        super().__init__(case, fitted_c, False)

    def doppler_rf_hz(self, track):
        midpoint = 10825000000.0 + 250000000.0 * (track["channel"] - 1)
        return midpoint + self.edge_factor * (track["rf_hz"] - midpoint)


def run(case, fitted_c, hypothesis, output, *, diagnostic_only=False):
    study = ReferenceHypothesis(case, fitted_c, hypothesis)
    output.mkdir(parents=True, exist_ok=False)
    references = {
        t["key"]: dict(actual_rf_hz=t["rf_hz"], doppler_reference_hz=study.doppler_rf_hz(t))
        for _, members in study.groups
        for t in members
    }
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
            hypothesis=hypothesis,
            edge_factor=study.edge_factor,
            reference_definition="midpoint + factor*(actual RF - midpoint)",
            midpoint_hz="10825000000 + 250000000*(channel-1)",
            actual_rf_and_hardware_c_feature_unchanged=True,
            times_cfo_values_ids_and_candidate_labels_unchanged=True,
            c0_fitted_c_same_observations_labels_initializers_priors_and_budgets=True,
            only_measured_curved_fragments_calibrate=True,
            no_rf_parameter_estimated=True,
            hypotheses_are_not_calibration_authority=True,
            rf_references=references,
            diagnostic_only=diagnostic_only,
            same_73_location_binary_scale_search_for_all_hypotheses=True,
            independent_local_not_globally_converged=True,
            evaluation_position_used_in_search=False,
        ),
    )
    started = time.monotonic()
    result, error = None, None
    if not diagnostic_only:
        result = locate(study, output)
        digest = hashlib.sha256((output / "fit.json").read_bytes()).hexdigest()
        # Ground truth enters only after the independent endpoint is saved.
        f = result["endpoint"]
        error = distance_km(
            (f["latitude_deg"], f["longitude_deg"]), (37.849061591561885, -122.48574968092912)
        )
        write(
            output / "evaluation.json",
            dict(
                position_error_km=error,
                fit_sha256=digest,
                reference_used_only_after_fit=True,
                within_0_5km=error < 0.5,
                experimental_reference_hypothesis=True,
                not_a_qualified_localization_result=True,
            ),
        )
    known = study.fit(37.849061591561885, -122.48574968092912)
    write(output / "known_position_diagnostic.json", known)
    summary = dict(
        case=case,
        fitted_c=fitted_c,
        hypothesis=hypothesis,
        diagnostic_only=diagnostic_only,
        position_error_km=error,
        known_position_rms_hz=known["detail"]["overall_rms_hz"],
        known_position_compatible_points=known["detail"]["member_compatible_points"],
        fixed_points=len(study.observation_ids),
        elapsed_seconds=time.monotonic() - started,
    )
    if result is not None:
        summary.update(
            locations=result["locations"],
            score=result["endpoint"]["score"],
            rms_hz=result["endpoint"]["detail"]["overall_rms_hz"],
            compatible_curved_points=result["endpoint"]["detail"]["member_compatible_points"],
        )
    write(output / "summary.json", summary)
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", choices=("DSX01-S01", "DS22-001"), required=True)
    p.add_argument("--fitted-c", action="store_true")
    p.add_argument("--hypothesis", choices=tuple(FACTORS), required=True)
    p.add_argument("--diagnostic-only", action="store_true")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if Path("/mnt/qnap01") in (a.output.resolve(), *a.output.resolve().parents):
        p.error("QNAP is read-only")
    run(a.case, a.fitted_c, a.hypothesis, a.output, diagnostic_only=a.diagnostic_only)
