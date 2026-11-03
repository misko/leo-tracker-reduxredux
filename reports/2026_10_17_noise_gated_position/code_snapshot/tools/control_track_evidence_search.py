"""Legacy-objective controls with the new search's inputs, starts and budgets."""

import argparse
import hashlib
import json
import time
from pathlib import Path

from associate_merged_track_catalogue import load_tracks, write
from evaluate_robust_curve_reassociation import population_association
from evaluate_shared_satellite_phase import Experiment, protocol
from localize_merged_track_catalogue import distance_km
from search_track_evidence_position import locate, prepare


class LegacyRanking:
    """Delegate parameter fitting to the unchanged old score and update rule."""

    def __init__(self, study):
        self.study, self.receipt = study, study.receipt

    def fit(self, latitude, longitude, budget, *, exact=False):
        result = Experiment.fit(self.study, latitude, longitude, budget, exact=exact)
        # Discovery does not spend time evaluating the diagnostic new score.
        result["compatible_curved_points"] = None
        return result


def run(case, fitted_c, output):
    study, seed, seed_path, binding, recording, background = prepare(case, fitted_c)
    protocol(study, output, "legacy_objective_matched_search_control", 8)
    write(
        output / "control_protocol.json",
        dict(
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            shared_search_source_sha256=hashlib.sha256(
                Path(__file__).with_name("search_track_evidence_position.py").read_bytes()
            ).hexdigest(),
            seed_fit_sha256=hashlib.sha256(seed_path.read_bytes()).hexdigest(),
            partition=binding,
            same_blind_c0_initial_position_and_hardware=True,
            same_points_candidates_priors_and_geographic_budgets=True,
            maximum_locations=41,
            grid_offsets_km=[-16, 0, 16],
            local_steps_km=[8, 2, 0.5, 0.125],
            discovery_generated_seed_budget=4,
            exact_generated_seed_budget=8,
            exact_finalists=3,
            legacy_objective_and_parameter_update_rule_unchanged=True,
            new_algorithm_extra_feasible_updates_absent=True,
            final_association_gate_order_matched_to_new_algorithm=True,
            c0_fitted_c_inputs_and_budgets_matched=True,
            evaluation_position_used_in_search=False,
        ),
    )
    started = time.monotonic()
    result = locate(LegacyRanking(study), seed, output)
    digest = hashlib.sha256((output / "fit.json").read_bytes()).hexdigest()
    association = population_association(
        study, result["endpoint"], load_tracks(recording), background
    )
    write(output / "association.json", association)
    reference = (37.849061591561885, -122.48574968092912)
    fit = result["endpoint"]
    error = distance_km((fit["latitude_deg"], fit["longitude_deg"]), reference)
    write(
        output / "evaluation.json",
        dict(
            position_error_km=error,
            within_0_5km=error < 0.5,
            reference_used_only_after_fit=True,
            fit_sha256=digest,
            resumed_not_cold=True,
        ),
    )
    summary = dict(
        case=case,
        fitted_c=fitted_c,
        algorithm="legacy objective control",
        position_error_km=error,
        associated_points=association["compatible_points"],
        merged_tracks=association["merged_tracks"],
        original_graph_points=association["original_points"],
        curved_points=sum(
            r["points"]
            for r in association["association"]["rows"]
            if r["compatible"] and r["active_curvature"]
        ),
        score=fit["score"],
        elapsed_seconds=time.monotonic() - started,
        locations=result["local_locations"],
    )
    write(output / "summary.json", summary)
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", choices=("DSX01-S01", "DS22-001"), required=True)
    p.add_argument("--fitted-c", action="store_true")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if Path("/mnt/qnap01") in (a.output.resolve(), *a.output.resolve().parents):
        p.error("QNAP is read-only")
    run(a.case, a.fitted_c, a.output)
