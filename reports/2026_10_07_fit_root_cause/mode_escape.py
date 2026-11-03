"""Causal timing-mode intervention, matched arms, no cross-arm warm starts.

Each arm continues only its own original associated fit. In catalogue order,
try moving one satellite's orbit shift to the mean of the other shifts; retain
the move only if the unchanged complete V16 objective decreases. All observation
rows and satellites remain. One bounded continuous refinement follows the sweep.
This is an exploratory continuation, not a matched original-total-budget rerun.
"""

import json
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SID = "scan-fw-6bf407cfe8158445"
BASIN = "point:-87.5:-87.5"


def common_mode_trial(vector, basis, satellite_index):
    result = np.asarray(vector, float).copy()
    shifts = result[7] + basis @ result[8:]
    shifts[satellite_index] = (
        shifts.sum() - shifts[satellite_index]
    ) / (len(shifts) - 1)
    result[7] = shifts.mean()
    result[8:] = basis.T @ shifts
    return result


def main():
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    from leo.application.regional_position_inputs import prepare_position_windows
    from leo.operations.tle_archive import TleArchiveReader
    from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
    from leo.sky.propagation import parse_element_sets
    from leo.analysis.regional_position_bank import build_regional_bank
    from leo.analysis.regional_position_score import PositionObjective, coordinates
    from leo.analysis.regional_position_fit import fit_position
    from leo.contracts.regional_position import RegionalPrior, PositionScore
    from leo.contracts.digests import canonical_digest
    from leo.storage.regional_position_checkpoints import RegionalCheckpointStore

    begun = time.monotonic()
    snapshot = json.loads((HERE.parent / "2026_10_07_recent_filter_review/snapshot.json").read_text())
    doc = next(c["regional_document"] for c in snapshot["captures"] if c["session_id"] == SID)
    saved = doc["diagnostics"]
    store = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    try:
        source = store.load(SID)
    finally:
        store.close()
    assert source.input_manifest_sha256 == doc["input_manifest_sha256"]
    assert source.analysis_manifest_sha256 == doc["analysis_manifest_sha256"]
    prepared = prepare_position_windows(source)
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    tle = next(s for s in archive.list_snapshots()
               if s.digest == saved["snapshot_sha256"]
               and s.collected_utc_ns == saved["snapshot_collected_utc_ns"])
    payload, _ = exclude_labelled_starlink_debris(archive.read(tle))
    catalogue = parse_element_sets(payload)
    indices = np.asarray([i for i, name in enumerate(catalogue.names)
                          if name.upper().startswith("STARLINK")])
    prior = RegionalPrior(**doc["configuration"]["prior"])
    bank, receipt = build_regional_bank(catalogue, indices, prepared.start_utc_ns,
                                       prepared.observations, prior, maximum_seconds=60)
    assert list(receipt.retained_numbers) == saved["bank"]["retained_numbers"]
    checkpoint = RegionalCheckpointStore(Path("/srv/bulk/leo"), SID, saved["checkpoint_binding"])
    prefix = canonical_digest(doc["configuration"]["run"])
    calibration = checkpoint.get(prefix + ":" + BASIN + ":calibration")["result"]
    association = checkpoint.get(prefix + ":" + BASIN + ":association")["result"]
    objective = PositionObjective(
        prepared.observations, bank.select(association["selected_indices"]), prior,
        PositionScore(**doc["configuration"]["scores"]["V16"]),
        receiver_baseline_hz=np.asarray(calibration["receiver_baseline_hz"]),
    )
    original = [r for r in saved["final_starts"]
                if r["method"] == "V16" and r["basin"] == BASIN and r["start"] == "associated"]
    point = np.asarray(association["initial_vector"][:2])
    spacings = [p["spacing_km"] for m in doc["methods"] for p in m["points"]
                if p["east_km"] == -87.5 and p["north_km"] == -87.5]
    radius = max(12.5, max(spacings) / np.sqrt(2))
    results = []
    for arm in ("fitted-c", "zero-c"):
        saved_row = next(r for r in original if r["arm"] == arm)
        vector = np.asarray(saved_row["fit"]["vector"])
        initial_value, _, _ = objective.evaluate(vector)
        assert abs(initial_value - saved_row["fit"]["objective"]) < 1e-6
        current_value = initial_value
        interventions = []
        for j, number in enumerate(objective.bank.numbers):
            trial = common_mode_trial(vector, objective.basis, j)
            assert np.array_equal(trial[:7], vector[:7])
            assert abs(trial[7]) <= 10
            assert np.max(np.abs(trial[7] + objective.basis @ trial[8:])) <= 20
            trial_value, _, terms = objective.evaluate(trial)
            improvement = current_value - trial_value
            accepted = improvement > 1e-8
            interventions.append({
                "number": int(number), "accepted": accepted,
                "objective_before": float(current_value), "objective_trial": float(trial_value),
                "objective_improvement": float(improvement),
                "satellite_signal_mass_trial": float(terms.responsibilities[:, j].sum()),
                "shift_before_s": float(vector[7] + objective.basis[j] @ vector[8:]),
                "shift_trial_s": float(trial[7] + objective.basis[j] @ trial[8:]),
            })
            if accepted:
                vector, current_value = trial, trial_value
        fit = fit_position(objective, vector, rf_arm=arm, maximum_seconds=20,
                           maximum_iterations=300, local_center=point, local_radius_km=radius)
        value, _, terms = objective.evaluate(fit.vector)
        relative_penalty = .5 * np.sum((fit.vector[8:] / objective.score.relative_sigma_s) ** 2)
        common_penalty = .5 * (fit.vector[7] / objective.score.common_sigma_s) ** 2
        results.append({
            "arm": arm, "initial_objective": float(initial_value),
            "after_discrete_sweep_objective": float(current_value),
            "interventions": interventions, "objective": float(value),
            "selection_score": float(value + saved_row["calibration_penalty"]),
            "data_nll": terms.nll, "relative_timing_penalty": float(relative_penalty),
            "common_timing_penalty": float(common_penalty),
            "posterior_rms_hz": fit.posterior_rms_hz, "signal_mass": fit.signal_windows,
            "vector": fit.vector.tolist(), "converged": fit.converged,
            "stationarity": fit.stationarity, "stop_reason": fit.stop_reason,
            "fit_elapsed_s": fit.elapsed_s, "evaluations": fit.evaluations,
        })
        print(arm, "initial", initial_value, "sweep", current_value,
              "refined", value, "converged", fit.converged, flush=True)
    # Reference coordinates enter only after every objective-based decision.
    for row in results:
        lat, lon = np.radians(coordinates(prior, row["vector"][:2]))
        ref_lat, ref_lon = np.radians([doc["reference_latitude_deg"], doc["reference_longitude_deg"]])
        h = np.sin((lat - ref_lat) / 2) ** 2 + np.cos(lat) * np.cos(ref_lat) * np.sin((lon - ref_lon) / 2) ** 2
        row["horizontal_error_m"] = float(2 * 6371008.8 * np.arcsin(np.sqrt(np.clip(h, 0, 1))))
    output = {
        "session_id": SID, "basin": BASIN, "input_sha256": source.input_manifest_sha256,
        "analysis_sha256": source.analysis_manifest_sha256, "tle_sha256": tle.digest,
        "windows": len(prepared.observations.window_ids), "satellite_numbers": objective.bank.numbers.tolist(),
        "local_radius_km": radius, "additional_budget_per_arm": {"timing_trials": len(objective.bank.numbers),
                                                                   "fit_seconds": 20, "fit_iterations": 300},
        "limitations": ["One selected failure case and one basin, not independent validation.",
                        "Additional continuation budget beyond the original matched fits.",
                        "Own-arm saved incumbents used; no cross-arm outputs or truth used to choose trials.",
                        "Only one catalogue-order timing sweep; no global optimality claim."],
        "results": results, "total_elapsed_s": time.monotonic() - begun,
    }
    (HERE / "mode_escape.json").write_text(json.dumps(output, indent=2) + "\n")


if __name__ == "__main__":
    main()
