"""Check empirical-support geometry derivatives on actual capture incumbents."""
import json
from dataclasses import replace

import numpy as np

from experiment import HERE, loader, controls, full_scan_pool
from cone_objective import ConeObjective, cone_bundle


def main():
    from leo.contracts.regional_position import PositionScore
    rows = []
    theta, frames, support = cone_bundle()
    for case in ("1939", "2139"):
        doc, old, obs, prior, bank, checkpoint, prefix = loader.load(case)
        selected = min((r for r in full_scan_pool(case, old) if r["arm"] == "fitted-c"), key=lambda r:r["selection_score"])
        basin = selected["basin"]
        assoc = checkpoint.get(prefix + ":" + basin + ":association")["result"]
        cal = checkpoint.get(prefix + ":" + basin + ":calibration")["result"]
        obj = ConeObjective(obs, bank.select(assoc["selected_indices"]), prior,
                            replace(PositionScore(**doc["configuration"]["scores"]["V16"]), relative_sigma_s=1.),
                            receiver_baseline_hz=np.asarray(cal["receiver_baseline_hz"]),
                            strength=1., theta=theta, frames=frames, support=support)
        vector = np.asarray(selected["vector"])
        _, grad, _ = obj.evaluate(vector)
        for index, h in ((0, .001), (1, .001), (2, .001), (6, .001), (7, 1e-5), (8, 1e-5), (12, 1e-5)):
            plus, minus = vector.copy(), vector.copy()
            plus[index] += h
            minus[index] -= h
            numeric = (obj.evaluate(plus)[0] - obj.evaluate(minus)[0]) / (2*h)
            error = abs(numeric - grad[index])
            row = dict(case=case, basin=basin, index=index, analytic=float(grad[index]), numerical=float(numeric), absolute_error=float(error))
            rows.append(row)
            assert error < .01 + .0001 * abs(numeric), row
        print(case, "real-gradient audit passed", flush=True)
    (HERE / "gradient_audit.json").write_text(json.dumps(dict(rows=rows, passed=True), indent=2) + "\n")


if __name__ == "__main__":
    main()
