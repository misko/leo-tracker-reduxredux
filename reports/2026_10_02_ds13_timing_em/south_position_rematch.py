"""Symmetric bounded catalogue rematching at two sealed DS13 profile positions."""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime

import numpy as np
from all_visible_bank import load_expanded_scan
from compact_satellite_selection import (
    SESSIONS,
    FrozenBankEvaluator,
    _evaluate_neighborhood,
    _refit_shortlist,
    _screen_candidates,
    complexity_penalty,
    fit_compact_bank,
)
from finite_set_fit import assert_snapshot_unchanged, digest, snapshot_files
from finite_set_likelihood import prepare_finite_set_likelihood
from prepare_scans import ROOT
from rf_calibration_diagnostic import rf_features
from rough_smoke import serializable

LABELS = ("truth", "S-500m")
BUDGET_S = 115.0


def profile_start(profile, session, label, data):
    if label not in LABELS or profile.get("session") != session:
        raise ValueError("profile identity or requested position mismatch")
    points = [point for point in profile["positions"] if point["label"] == label]
    if len(points) != 1 or points[0].get("best") is None:
        raise ValueError("missing or ambiguous sealed profile point")
    point = points[0]
    best = point["best"]
    parameters = np.asarray(best["parameters"], dtype=float)
    satellites = np.asarray(profile["satellite_indices"], dtype=int)
    if parameters.shape != (6 + len(data.numbers),) or not np.all(np.isfinite(parameters)):
        raise ValueError("profile parameters do not match expanded bank")
    if not np.array_equal(parameters[:2], point["fixed_position_km"]):
        raise ValueError("profile parameters differ from fixed position")
    if not np.array_equal(np.asarray(data.numbers)[satellites], profile["catalog_numbers"]):
        raise ValueError("profile catalogues differ from expanded bank")
    probability = float(profile["detection_probability"])
    if best["detection_probability"] != probability:
        raise ValueError("profile point detection probability mismatch")
    return point, parameters.copy(), satellites.copy(), probability


def best_finite(candidates):
    finite = [row for row in candidates if np.isfinite(row["penalized_objective"])]
    if not finite:
        raise ValueError("no finite rematch state")
    return min(finite, key=lambda row: (
        row["penalized_objective"], len(row["satellite_indices"]), row["move"]
    ))


def rematch(data, point, parameters, satellites, probability, deadline, *,
            clock=time.monotonic, checkpoint=None):
    started = clock()
    remaining = max(0.0, deadline - started)
    prepared = prepare_finite_set_likelihood(data.measured, data.group)
    center, _ = rf_features(data.rf, data.receiver, False)
    coefficient = np.asarray(point["best"]["rf_coefficient_hz_per_ghz"], dtype=float)
    evaluator = FrozenBankEvaluator(
        data, prepared, probability, center, coefficient, len(prepared.group_values)
    )
    baseline_score = evaluator.evaluate_bank(parameters, satellites)
    if not np.isclose(baseline_score["objective"], point["best"]["objective"],
                      rtol=0.0, atol=1e-6):
        raise ValueError("sealed profile baseline does not reproduce")
    baseline = {
        "move": "sealed_profile_baseline", "satellite_indices": satellites,
        "fit": point["best"], **baseline_score,
    }
    result = {"baseline": baseline, "screening": [], "neighborhood": [], "refits": [],
              "selected": baseline, "screening_complete": False,
              "neighborhood_complete": False, "refits_complete": False, "errors": []}
    if checkpoint is not None:
        checkpoint(result)
    inactive = np.flatnonzero(~np.isin(np.arange(len(data.numbers)), satellites))
    inactive = inactive[np.argsort(np.asarray(data.numbers)[inactive], kind="stable")]
    result["inactive_candidate_count"] = len(inactive)
    candidates = [baseline]
    try:
        _, screening, stopped = _screen_candidates(
            data, evaluator, parameters, satellites, inactive,
            started + remaining * 0.40, clock=clock,
        )
        result.update(screening=screening, screening_complete=(
            not stopped and len(screening) == len(inactive)))
        if checkpoint is not None:
            checkpoint(result)
        neighborhood, stopped = _evaluate_neighborhood(
            data, evaluator, parameters, satellites, screening,
            started + remaining * 0.60, clock=clock,
        )
        result.update(neighborhood=neighborhood, neighborhood_complete=not stopped)
        for row in neighborhood:
            candidates.append({**row, "fit": {
                "parameters": row["parameters"],
                "rf_coefficient_hz_per_ghz": coefficient,
                "objective": row["objective"], "success": False,
                "status": "frozen_nuisance_unprofiled",
            }})
        result["selected"] = best_finite(candidates)
        if checkpoint is not None:
            checkpoint(result)

        def guarded_refit(fit_data, initial, bank, fixed_probability, rf, *, budget_s):
            fitted = fit_compact_bank(fit_data, initial, bank, fixed_probability, rf,
                                      budget_s=budget_s)
            if not np.array_equal(np.asarray(fitted["parameters"])[:2], parameters[:2]):
                raise ValueError("rematch refit changed fixed position")
            score = complexity_penalty(len(prepared.group_values), len(bank))
            candidates.append({"move": "refit:" + ",".join(map(str, bank)),
                               "satellite_indices": bank, "fit": fitted,
                               "penalized_objective": fitted["objective"] + score,
                               "complexity_penalty": score})
            result["selected"] = best_finite(candidates)
            result["completed_refit_states"] = candidates[len(neighborhood) + 1:]
            if checkpoint is not None:
                checkpoint(result)
            return fitted

        if any(row["move"] == "baseline" for row in neighborhood):
            refits, _ = _refit_shortlist(
                data, neighborhood, satellites, probability, coefficient, deadline,
                clock=clock, fitter=guarded_refit,
            )
            result["refits"] = refits
            result["refits_complete"] = all(row.get("attempted") for row in refits)
        result["selected"] = best_finite(candidates)
    except Exception as error:
        result["errors"].append(f"{type(error).__name__}: {error}")
        result["selected"] = best_finite(candidates)
    result["screened_candidate_count"] = len(result["screening"])
    result["unscreened_candidate_count"] = len(inactive) - len(result["screening"])
    result["ranking_resolved_within_shortlist"] = bool(
        result["screening_complete"] and result["neighborhood_complete"]
        and result["refits_complete"] and not result["errors"]
        and result["selected"]["fit"].get("success", False)
        and all(row.get("fit", {}).get("success", False) for row in result["refits"])
    )
    result["penalized_improvement_vs_profile"] = (
        baseline["penalized_objective"] - result["selected"]["penalized_objective"]
    )
    result["elapsed_s"] = clock() - started
    return result


def run_case(cell):
    session, label = cell
    started = time.monotonic()
    destination = ROOT / "south-position-rematch" / f"{session}-{label}.json"
    if destination.exists():
        raise FileExistsError(destination)
    path = ROOT / "pruned-position-profile-grid" / f"{session}.json"
    profile = json.loads(path.read_text())
    assert_snapshot_unchanged(profile["source_hashes"])
    hashes = {**profile["source_hashes"], **snapshot_files([
        __file__, path, ROOT / "compact_satellite_selection.py",
        ROOT / "all-visible-bank" / session / "receipt.json",
        ROOT / "all-visible-bank" / session / "expanded.npz",
    ])}
    data = load_expanded_scan(session)
    point, parameters, satellites, probability = profile_start(profile, session, label, data)
    destination.parent.mkdir(exist_ok=True)
    common = {
        "schema": "ds13-south-position-rematch/v1", "session": session, "label": label,
        "fixed_position_km": parameters[:2], "detection_probability": probability,
        "source_hashes": hashes, "profile_sha256": digest(path),
        "source_satellite_indices": satellites,
        "source_catalog_numbers": np.asarray(data.numbers)[satellites],
        "all_visible_candidate_count": len(data.numbers),
        "row_count": len(data.measured), "group_count": len(np.unique(data.group)),
        "reference_position_conditioned": True,
        "ranking_uses_location_error": False,
        "scope": "EXPLORATORY symmetric rematching at sealed reference and south positions. "
                 "Identical fixed p, sigma200, timing priors and 0.5log(G) per satellite. "
                 "All observations retained. Seven candidate timing offsets relative to each "
                 "profile's common timing, top8 add/drop/swap neighborhood, four Fisher refits. "
                 "One local pass; no iterative pruning or global optimum claim. The candidate "
                 "pool retains the original archived spatial/time eligibility envelope.",
        "budget_s": BUDGET_S,
    }
    sequence = 0

    def checkpoint(partial):
        nonlocal sequence
        assert_snapshot_unchanged(hashes)
        checkpoint_path = destination.with_name(
            destination.stem + f"-partial-{sequence:02d}.json"
        )
        with checkpoint_path.open("x") as stream:
            json.dump(serializable({**common, **partial, "complete_receipt": False}),
                      stream, allow_nan=False)
        sequence += 1

    result = rematch(data, point, parameters, satellites, probability,
                     started + BUDGET_S, checkpoint=checkpoint)
    selected = result["selected"]
    selected["catalog_numbers"] = np.asarray(data.numbers)[
        np.asarray(selected["satellite_indices"], dtype=int)]
    assert_snapshot_unchanged(hashes)
    with destination.open("x") as stream:
        json.dump(serializable({**common, **result, "complete_receipt": True,
                                "total_elapsed_s": time.monotonic() - started,
                                "sealed_utc": datetime.now(UTC).isoformat()}),
                  stream, indent=2, allow_nan=False)
    return {"session": session, "label": label,
            "screened": result["screened_candidate_count"],
            "improvement": result["penalized_improvement_vs_profile"],
            "selected_move": selected["move"],
            "resolved": result["ranking_resolved_within_shortlist"],
            "elapsed_s": time.monotonic() - started}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    cells = [(session, label) for session in SESSIONS for label in LABELS]
    with ProcessPoolExecutor(max_workers=2) as executor:
        for result in executor.map(run_case, cells):
            print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
