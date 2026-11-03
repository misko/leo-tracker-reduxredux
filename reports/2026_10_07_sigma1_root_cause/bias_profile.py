"""Fixed-position continuation from each own-arm optimized bias to the reference.

Eight small position steps reduce the large-jump initialization problem seen in
the first oracle diagnostic. This is a conditional score profile, not inference.
"""
import json
from dataclasses import replace
from pathlib import Path

import numpy as np

from oracle import HERE, CONTROLS, load, fixed_audit, reference_point


def main():
    from leo.analysis.regional_position_score import PositionObjective
    from leo.analysis.regional_position_fit import fit_position
    from leo.contracts.regional_position import PositionScore
    destination = HERE / "bias_profile_results.json"
    if destination.exists():
        raise FileExistsError(destination)
    stage = json.loads((HERE / "shared_bias/results.json").read_text())
    doc, receipt, obs, prior, bank, checkpoint, prefix = load("1939")
    truth = reference_point(prior, doc["reference_latitude_deg"], doc["reference_longitude_deg"])
    result = dict(protocol_sha256=CONTROLS.digest_bytes(Path(__file__).read_bytes()), sigma_s=1.,
                  seconds_per_step=8., steps=8, rows=[], status="running")
    for arm in CONTROLS.ARMS:
        selected = stage["selected"][arm]
        assert selected["converged"]
        basin = selected["basin"]
        association = checkpoint.get(prefix + ":" + basin + ":association")["result"]
        calibration = checkpoint.get(prefix + ":" + basin + ":calibration")["result"]
        obj = PositionObjective(obs, bank.select(association["selected_indices"]), prior,
                                replace(PositionScore(**doc["configuration"]["scores"]["V16"]), relative_sigma_s=1.),
                                receiver_baseline_hz=np.asarray(calibration["receiver_baseline_hz"]))
        vector = np.asarray(selected["vector"]).copy()
        start_point = vector[:2].copy()
        initial = fixed_audit(obj, vector, arm)
        initial.update(arm=arm, fraction=0., error_m=selected["error_m"], basin=basin)
        result["rows"].append(initial)
        for fraction in np.linspace(0., 1., 9)[1:]:
            target = (1 - fraction) * start_point + fraction * truth
            vector[:2] = target
            fit = fit_position(obj, vector, rf_arm=arm, fixed_position=True,
                               maximum_seconds=8., maximum_iterations=300)
            row = fixed_audit(obj, fit.vector, arm)
            np.testing.assert_array_equal(fit.vector[:2], target)
            assert abs(row["stationarity"] - fit.stationarity) < 1e-5
            vector = fit.vector.copy()
            row.update(arm=arm, fraction=float(fraction), basin=basin, elapsed_s=fit.elapsed_s,
                       stop_reason=fit.stop_reason)
            result["rows"].append(row)
            destination.write_text(json.dumps(result, indent=2, default=CONTROLS.encode) + "\n")
            print(arm, fraction, round(row["objective"], 3), row["converged"], round(row["stationarity"], 6), flush=True)
    result["status"] = "complete"
    destination.write_text(json.dumps(result, indent=2, default=CONTROLS.encode) + "\n")


if __name__ == "__main__":
    main()
