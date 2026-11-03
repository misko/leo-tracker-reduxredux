"""Post-search known-position diagnostics; never feed these states into search."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import load_tracks, write
from evaluate_robust_curve_reassociation import population_association
from search_track_evidence_position import PRIOR, ROOT, prepare


def run(case, fitted_c, output):
    arm = "fitted_c" if fitted_c else "c0"
    completed = ROOT / "reports/2026_10_17_noise_gated_position/search" / case / arm
    # Require a finished search, immutable endpoint binding and completed nulls.
    for name in ("summary.json", "conditional_nulls.json", "association.json"):
        if not (completed / name).is_file():
            raise ValueError("blind search is not finished")
    evaluation = json.loads((completed / "evaluation.json").read_text())
    fit_sha = hashlib.sha256((completed / "fit.json").read_bytes()).hexdigest()
    if fit_sha != evaluation["fit_sha256"]:
        raise ValueError("saved blind endpoint changed")
    study, _, _, _, recording, background = prepare(case, fitted_c)
    # Evaluation coordinates enter only this separate post-search diagnostic.
    lat, lon = 37.849061591561885, -122.48574968092912
    output.mkdir(parents=True, exist_ok=False)
    fit = study.fit(lat, lon, 8, exact=True)
    write(output / "same_blind_initializer_fit.json", fit)
    association = population_association(study, fit, load_tracks(recording), background)
    write(output / "same_blind_initializer_association.json", association)
    known_path = PRIOR / "fits" / case / f"repaired_{arm}" / "fixed_site.json"
    prior = json.loads(known_path.read_text())["fit"]
    refined = study.exact_refine(lat, lon, np.asarray(prior["beta"]), np.asarray(prior["phases_s"]))
    second = dict(
        fit,
        beta=refined["beta"].tolist(),
        phases_s=refined["phases_s"].tolist(),
        score=refined["evidence"]["score"],
        score_parts=refined["evidence"]["parts"],
        compatible_curved_points=refined["evidence"]["compatible_curved_points"],
        compatible_curved_components=refined["evidence"]["compatible_curved_components"],
        exact_history=refined["exact_history"],
        initializer="previous known-position diagnostic only",
    )
    write(output / "known_position_initializer_fit.json", second)
    second_association = population_association(study, second, load_tracks(recording), background)
    write(output / "known_position_initializer_association.json", second_association)
    endpoint = json.loads((completed / "fit.json").read_text())["endpoint"]
    write(
        output / "protocol.json",
        dict(
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            completed_blind_fit_sha256=fit_sha,
            previous_known_position_fit_sha256=hashlib.sha256(known_path.read_bytes()).hexdigest(),
            same_population_candidates_priors=True,
            same_blind_initializer_budget=8,
            alternative_known_initializer_is_not_a_blind_result=True,
            no_search_state_or_parameters_modified=True,
            not_fed_back_into_search=True,
            frequency_only_comparison_not_position_improvement=True,
        ),
    )
    summary = dict(
        case=case,
        fitted_c=fitted_c,
        blind_score=endpoint["score"],
        known_position_same_blind_initializer_score=fit["score"],
        known_position_same_blind_initializer_points=association["compatible_points"],
        known_position_historical_initializer_score=second["score"],
        known_position_historical_initializer_points=second_association["compatible_points"],
        blind_position_error_km=evaluation["position_error_km"],
        blind_fit_sha256=fit_sha,
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
