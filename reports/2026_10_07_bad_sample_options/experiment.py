"""Matched bounded continuation of four frozen V16 failure captures.

Every original final basin and every original arm incumbent remains a candidate.
Each option refines the same best ORIGINAL incumbent of its own arm per basin.
No arm, option, or capture consumes another one's newly optimized output.
Reference coordinates are read only after objective-based selection is complete.
"""

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from scipy.optimize import nnls

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "2026_10_07_recent_filter_review/snapshot.json"
CASES = {
    "1838": "scan-fw-6bf407cfe8158445",
    "1939": "scan-fw-6a376b600fc2f542",
    "2139": "scan-fw-e3bebc228093a125",
    "2209": "scan-fw-0695481606e1a3e8",
}
OPTIONS = (
    ("sigma015", .15, False), ("sigma030", .30, False),
    ("sigma050", .50, False), ("sigma100", 1., False),
    ("modes015", .15, True), ("modes050", .50, True),
)
ARMS = ("fitted-c", "zero-c")


def encode(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(type(value).__name__)


def digest_bytes(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def vector_digest(vector):
    return digest_bytes(np.asarray(vector, dtype="<f8").tobytes())


def select(rows):
    return min(rows, key=lambda r: (r["selection_score"], r["basin"], r["origin"]))


def timing_trial(vector, basis, index):
    answer = np.asarray(vector, float).copy()
    shifts = answer[7] + basis @ answer[8:]
    shifts[index] = (shifts.sum() - shifts[index]) / (len(shifts) - 1)
    answer[7], answer[8:] = shifts.mean(), basis.T @ shifts
    return answer


def audit(vector, gradient, basis, arm, prior_radius, center, radius, timing_min, timing_max):
    """Independent scaled KKT audit, matching deployed tolerances and bounds."""
    vector, gradient = np.asarray(vector), np.asarray(gradient)
    scales = np.r_[1., 1., 200., 2., 200., 2., 200., np.ones(len(vector) - 7)]
    free = np.array([i for i in range(len(vector)) if arm != "zero-c" or i != 6])
    matrix = np.zeros((len(basis), len(vector)))
    matrix[:, 7], matrix[:, 8:] = 1, basis
    shifts = matrix @ vector
    normals = []
    minimum_slack = min(float((shifts - timing_min).min()), float((timing_max - shifts).min()))
    for j, shift in enumerate(shifts):
        if shift - timing_min <= 1e-6:
            normals.append((matrix[j] * scales)[free])
        if timing_max - shift <= 1e-6:
            normals.append((-matrix[j] * scales)[free])
    boundary = False
    for origin, r in ((np.zeros(2), prior_radius), (np.asarray(center), radius)):
        distance = np.linalg.norm(vector[:2] - origin)
        slack = r * r - distance * distance
        minimum_slack = min(minimum_slack, float(slack))
        boundary |= bool(distance >= r - 1e-4)
        if slack <= 1e-6:
            normal = np.zeros(len(vector))
            normal[:2] = -2 * (vector[:2] - origin)
            normals.append((normal * scales)[free])
    low, high = np.full(len(vector), -np.inf), np.full(len(vector), np.inf)
    low[:2], high[:2] = -prior_radius, prior_radius
    low[6], high[6], low[7], high[7] = -5000, 5000, -10, 10
    z = vector / scales
    for k, i in enumerate(free):
        normal = np.eye(len(free))[k]
        if z[i] <= low[i] / scales[i] + 1e-7:
            normals.append(normal)
        if z[i] >= high[i] / scales[i] - 1e-7:
            normals.append(-normal)
    scaled = (gradient * scales)[free]
    if normals:
        active = np.asarray(normals).T
        multipliers, _ = nnls(active, scaled, maxiter=100 * max(1, active.shape[1]))
        scaled = scaled - active @ multipliers
    stationarity = float(np.max(np.abs(scaled), initial=0))
    bounds_ok = bool(np.all(vector[free] >= low[free] - 1e-7)
                     and np.all(vector[free] <= high[free] + 1e-7))
    feasible = minimum_slack >= -1e-6 and bounds_ok and (arm != "zero-c" or vector[6] == 0)
    return dict(stationarity=stationarity, converged=bool(feasible and stationarity <= .001),
                boundary=boundary, feasible=bool(feasible), minimum_constraint_slack=minimum_slack)


def run(case, seconds=12.):
    import leo
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    from leo.application.regional_position_inputs import prepare_position_windows
    from leo.operations.tle_archive import TleArchiveReader
    from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
    from leo.sky.propagation import parse_element_sets
    from leo.analysis.regional_position_bank import build_regional_bank
    from leo.analysis.regional_position_score import PositionObjective, coordinates
    from leo.analysis.regional_position_fit import fit_position
    from leo.analysis.regional_position_search import SpatialSearch, SpatialEvaluation, distinct_basins
    from leo.contracts.regional_position import RegionalPrior, PositionScore
    from leo.contracts.digests import canonical_digest
    from leo.storage.regional_position_checkpoints import RegionalCheckpointStore

    target = HERE / case
    target.mkdir(exist_ok=True)
    if (target / "results.json").exists():
        raise FileExistsError("Use the existing receipt; do not overwrite completed runs")
    begun = time.monotonic()
    raw = SOURCE.read_bytes()
    snapshot = json.loads(raw)
    capture = next(c for c in snapshot["captures"] if c["session_id"] == CASES[case])
    doc, sid = capture["regional_document"], capture["session_id"]
    code_root = Path(leo.__file__).parent
    for relative, expected in doc["configuration"]["source_digests"].items():
        assert digest_bytes((code_root / relative).read_bytes()) == expected, relative
    store = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    try:
        source = store.load(sid)
    finally:
        store.close()
    assert source.input_manifest_sha256 == doc["input_manifest_sha256"]
    assert source.analysis_manifest_sha256 == doc["analysis_manifest_sha256"]
    prepared = prepare_position_windows(source)
    obs = prepared.observations
    saved = doc["diagnostics"]
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    tle = next(s for s in archive.list_snapshots() if s.digest == saved["snapshot_sha256"]
               and s.collected_utc_ns == saved["snapshot_collected_utc_ns"])
    payload, _ = exclude_labelled_starlink_debris(archive.read(tle))
    catalogue = parse_element_sets(payload)
    indices = np.asarray([i for i, name in enumerate(catalogue.names) if name.upper().startswith("STARLINK")])
    evidence = canonical_digest({"windows": prepared.evidence_sha256, "tle": tle.digest,
                                 "candidates": [int(catalogue.satellite_numbers[i]) for i in indices]})
    assert evidence == doc["evidence_sha256"]
    prior = RegionalPrior(**doc["configuration"]["prior"])
    bank, bank_receipt = build_regional_bank(catalogue, indices, prepared.start_utc_ns,
                                           obs, prior, maximum_seconds=60)
    assert list(bank_receipt.retained_numbers) == saved["bank"]["retained_numbers"]
    checkpoint = RegionalCheckpointStore(Path("/srv/bulk/leo"), sid, saved["checkpoint_binding"])
    prefix = canonical_digest(doc["configuration"]["run"])
    basins = {}
    for method in doc["methods"]:
        search = SpatialSearch(tuple(SpatialEvaluation(p["east_km"], p["north_km"], p["spacing_km"], p["objective"])
                                     for p in method["points"] if p["objective"] is not None),
                               method["deferred_cells"], method["search_stop_reason"])
        for p in distinct_basins(search, count=doc["configuration"]["run"]["basins_per_method"]):
            key = f"point:{p.east_km:g}:{p.north_km:g}"
            basins[key] = max(basins.get(key, 0), p.spacing_km)
    finals = [r for r in saved["final_starts"] if r["method"] == "V16" and r["fit"]]
    assert {r["basin"] for r in finals} <= set(basins)
    options = [dict(name=name, relative_sigma_s=sigma, timing_sweep=sweep) for name, sigma, sweep in OPTIONS]
    output = dict(case=case, session_id=sid, capture_start_utc=capture["capture_start_utc"],
                  protocol_sha256=digest_bytes(Path(__file__).read_bytes()), snapshot_sha256=digest_bytes(raw),
                  input_sha256=source.input_manifest_sha256, analysis_sha256=source.analysis_manifest_sha256,
                  evidence_sha256=evidence, window_evidence_sha256=prepared.evidence_sha256, tle_sha256=tle.digest,
                  source_digests_verified=doc["configuration"]["source_digests"],
                  windows=len(obs.window_ids), options=options,
                  budget_seconds_per_basin_arm_option=seconds, maximum_iterations=300,
                  original_results=[dict(method=m["name"], arm=a["name"], selected=a["selected"])
                                    for m in doc["methods"] for a in m["arms"]],
                  basins={}, runs=[], candidates=[], selections=[], status="running")

    def save():
        (target / "progress.json").write_text(json.dumps(output, default=encode, indent=2) + "\n")

    for basin, spacing in sorted(basins.items()):
        rows = [r for r in finals if r["basin"] == basin]
        if not rows:
            continue
        cal = checkpoint.get(prefix + ":" + basin + ":calibration")["result"]
        assoc = checkpoint.get(prefix + ":" + basin + ":association")["result"]
        subset = bank.select(assoc["selected_indices"])
        center = np.asarray(assoc["initial_vector"][:2])
        radius = max(12.5, spacing / np.sqrt(2))
        penalty = rows[0]["calibration_penalty"]
        assert all(abs(r["calibration_penalty"] - penalty) < 1e-10 for r in rows)
        initial_by_arm = {arm: min((r for r in rows if r["arm"] == arm),
                                  key=lambda r: (r["fit"]["objective"], r["start"])) for arm in ARMS}
        timing_min = max(-20., subset.nodes_s[0] - obs.times_s.min())
        timing_max = min(20., subset.nodes_s[-1] - obs.times_s.max())
        base_score = PositionScore(**doc["configuration"]["scores"]["V16"])
        output["basins"][basin] = dict(numbers=subset.numbers.tolist(), center=center.tolist(), radius_km=radius,
                                       baseline_sha256=vector_digest(cal["receiver_baseline_hz"]),
                                       seeds={arm:dict(original_start=r["start"], vector=r["fit"]["vector"],
                                                       vector_sha256=vector_digest(r["fit"]["vector"]))
                                              for arm, r in initial_by_arm.items()}, repricing=[])
        for option, sigma, sweep in OPTIONS:
            objective = PositionObjective(obs, subset, prior, replace(base_score, relative_sigma_s=sigma),
                                          receiver_baseline_hz=np.asarray(cal["receiver_baseline_hz"]))

            def candidate(vector, arm, origin, **extra):
                value, gradient, terms = objective.evaluate(vector)
                mass = float(terms.responsibilities.sum())
                common_penalty = .5 * (vector[7] / base_score.common_sigma_s) ** 2
                relative_penalty = .5 * np.sum((vector[8:] / sigma) ** 2)
                return dict(option=option, relative_sigma_s=sigma, timing_sweep=sweep, arm=arm,
                            basin=basin, origin=origin, vector=np.asarray(vector).tolist(),
                            objective=float(value), selection_score=float(value + penalty),
                            calibration_penalty=penalty, data_nll=float(terms.nll),
                            common_timing_penalty=float(common_penalty), relative_timing_penalty=float(relative_penalty),
                            posterior_rms_hz=float(np.sqrt(np.sum(terms.responsibilities * terms.residual_hz**2) / mass)) if mass else None,
                            signal_fraction=mass / len(obs.window_ids), signal_mass=mass,
                            **audit(vector, gradient, objective.basis, arm, prior.radius_km, center, radius, timing_min, timing_max),
                            **extra)

            for r in rows:
                row = candidate(np.asarray(r["fit"]["vector"]), r["arm"], "saved-" + r["start"])
                if sigma == .15:
                    delta = abs(row["objective"] - r["fit"]["objective"])
                    assert delta < 1e-6
                    if option == "sigma015":
                        output["basins"][basin]["repricing"].append(dict(arm=r["arm"], start=r["start"], discrepancy=delta))
                if row["feasible"]:
                    output["candidates"].append(row)
            for arm in ARMS:
                seed = np.asarray(initial_by_arm[arm]["fit"]["vector"], float).copy()
                # Admit only tiny rounding repairs to originally feasible spatial bounds.
                repairs = []
                for origin, r in ((np.zeros(2), prior.radius_km), (center, radius)):
                    distance = np.linalg.norm(seed[:2] - origin)
                    if distance > r:
                        assert distance - r < 1e-5, (basin, distance, r)
                        seed[:2] = origin + (seed[:2] - origin) * (r - 1e-8) / distance
                        repairs.append(float(distance - r + 1e-8))
                start_time = time.monotonic()
                deadline = start_time + seconds
                current, _, _ = objective.evaluate(seed)
                interventions = []
                if sweep:
                    for j, number in enumerate(subset.numbers):
                        if time.monotonic() >= deadline - .1:
                            break
                        trial = timing_trial(seed, objective.basis, j)
                        shifts = trial[7] + objective.basis @ trial[8:]
                        feasible = abs(trial[7]) <= 10 and np.all(shifts >= timing_min) and np.all(shifts <= timing_max)
                        trial_value = objective.evaluate(trial)[0] if feasible else None
                        accepted = feasible and trial_value < current - 1e-8
                        interventions.append(dict(number=int(number), objective_before=float(current),
                                                  objective_trial=trial_value, feasible=bool(feasible), accepted=bool(accepted)))
                        if accepted:
                            seed, current = trial, trial_value
                    sweep_row = candidate(seed, arm, "timing-sweep")
                    if sweep_row["feasible"]:
                        output["candidates"].append(sweep_row)
                remaining = deadline - time.monotonic()
                fit = None
                error = None
                if remaining > .02:
                    try:
                        fit = fit_position(objective, seed, rf_arm=arm, maximum_seconds=remaining,
                                           maximum_iterations=300, local_center=center, local_radius_km=radius)
                    except (ValueError, TimeoutError) as caught:
                        error = f"{type(caught).__name__}: {caught}"
                elapsed = time.monotonic() - start_time
                if fit is not None:
                    result = candidate(fit.vector, arm, "continued-fit", stop_reason=fit.stop_reason,
                                       native_converged=fit.converged, evaluations=fit.evaluations)
                    assert abs(result["objective"] - fit.objective) < 1e-6
                    assert abs(result["stationarity"] - fit.stationarity) < 1e-5
                    if result["feasible"]:
                        output["candidates"].append(result)
                else:
                    result = None
                output["runs"].append(dict(option=option, basin=basin, arm=arm,
                                           seed_sha256=vector_digest(initial_by_arm[arm]["fit"]["vector"]),
                                           spatial_rounding_repairs_km=repairs, interventions=interventions,
                                           fit_budget_seconds=max(0., remaining), elapsed_s=elapsed, error=error,
                                           result=result))
                print(case, basin, option, arm, "score", round(result["selection_score"], 2) if result else None,
                      "converged", result["converged"] if result else False,
                      "elapsed", round(elapsed, 2), flush=True)
                save()
    for option, _, _ in OPTIONS:
        for arm in ARMS:
            output["selections"].append(dict(select([r for r in output["candidates"]
                                                      if r["option"] == option and r["arm"] == arm])))
    # Truth only evaluates completed score-based selections, never proposals.
    for r in output["candidates"] + output["selections"]:
        lat, lon = np.radians(coordinates(prior, r["vector"][:2]))
        ref_lat, ref_lon = np.radians([doc["reference_latitude_deg"], doc["reference_longitude_deg"]])
        h = np.sin((lat - ref_lat) / 2) ** 2 + np.cos(lat) * np.cos(ref_lat) * np.sin((lon - ref_lon) / 2) ** 2
        r["horizontal_error_m"] = float(2 * 6371008.8 * np.arcsin(np.sqrt(np.clip(h, 0, 1))))
    output["nested_search_gaps"] = {name:max(0., next(r["selection_score"] for r in output["selections"] if r["option"] == name and r["arm"] == "fitted-c")
                                               - next(r["selection_score"] for r in output["selections"] if r["option"] == name and r["arm"] == "zero-c"))
                                      for name, _, _ in OPTIONS}
    output.update(status="complete", elapsed_s=time.monotonic() - begun)
    save()
    (target / "results.json").write_text(json.dumps(output, default=encode, indent=2) + "\n")
    for r in output["selections"]:
        print("SELECTED", case, r["option"], r["arm"], round(r["horizontal_error_m"], 2),
              r["converged"], r["boundary"], r["basin"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=CASES)
    parser.add_argument("--seconds", type=float, default=12.)
    args = parser.parse_args()
    if not 0 < args.seconds <= 20:
        raise ValueError("per-fit budget must be in (0,20] seconds")
    run(args.case, args.seconds)
