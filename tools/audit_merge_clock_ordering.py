"""Exposed fixed-point sensitivity to original shared receiver-drift estimates."""

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
from continuous_merge_consistency_study import LOCAL, PREVIOUS, REPORT
from continuous_merge_positions import load_prepared
from continuous_merge_study import sha, write

from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_bootstrap import bootstrap_position
from leo.contracts.regional_position import PositionOrbitBank, RegionalPrior


def main():
    session = "fast-014c72ff95ab599c51ba3b3ec9b92cb8"
    old = PREVIOUS / "local/DS20" / session
    current = LOCAL / "DS20" / session
    authority = old / "positions/posthoc-coarse-bank-comparison.json"
    fixed = json.loads(authority.read_bytes())
    checkpoint = PREVIOUS.parent.parent / fixed["variants"]["baseline"]["checkpoint"]
    original = json.loads(checkpoint.read_bytes())["value"]["result"]
    prepared = load_prepared(old / "baseline.json")
    merged = load_prepared(old / "replace-guard.json")
    pool = tuple(dict.fromkeys((*prepared.bootstrap_tracks, *merged.bootstrap_tracks)))
    diagnosis = json.loads((current / "positions/point-diagnosis.json").read_bytes())
    consistent = next(
        r for r in diagnosis if r["point"] == [-80.0, -80.0] and r["policy"]["mode"] == "consistent"
    )
    conflict = next(
        d for d in consistent["decisions"] if d["reason"] == "different-orbital-candidate"
    )
    parent = prepared.bootstrap_tracks[conflict["parent_indices"][0]]
    joined = tuple(conflict["joined_rows"])
    with np.load(old / "positions/bank.npz") as z:
        bank = PositionOrbitBank(**{k: z[k] for k in z.files})
    drift_vectors = {
        "uncorrected": (0.0, 0.0),
        "original_bootstrap_drift": tuple(original["bootstrap"]["vector"][i] for i in (3, 5)),
        "original_fixed_point_fit_drift": tuple(
            original["fits"]["V16"]["fit"]["vector"][i] for i in (3, 5)
        ),
    }
    results = {}
    for label, drift in drift_vectors.items():
        obs = prepared.observations
        correction = np.array(drift)[obs.receiver] * (obs.times_s - obs.time_center_s)
        adjusted = replace(obs, measured_hz=obs.measured_hz - correction)
        fit = bootstrap_position(
            adjusted,
            bank,
            RegionalPrior(),
            [-80, -80],
            pool,
            maximum_seconds=5,
            orbit_predictor=predict_orbits,
        )
        by_rows = {m.rows: m for m in fit.matches}
        results[label] = {"receiver_drift_hz_s": drift}
        for name, rows in (("parent", parent), ("joined", joined)):
            match = by_rows.get(rows)
            results[label][name] = (
                None
                if match is None
                else {
                    "catalogue_candidate": int(bank.numbers[match.satellite_index]),
                    "shape_rms_hz": match.shape_rms_hz,
                    "timing_s": match.timing_s,
                }
            )
    write(
        REPORT / "clock-ordering-sensitivity.json",
        {
            "scope": (
                "Exposed local sensitivity at east -80 km, north -80 km; "
                "not an accuracy experiment. "
                "Two correction vectors come from the original baseline at this fixed point; "
                "neither is used by the new protected-merge full positioning replays. "
                "CFO windows, proposal pool, orbit bank, timing grid, and budgets are matched."
            ),
            "point": [-80, -80],
            "authority_sha256": sha(authority),
            "original_checkpoint_sha256": sha(checkpoint),
            "script_sha256": sha(Path(__file__)),
            "results": results,
        },
    )
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
