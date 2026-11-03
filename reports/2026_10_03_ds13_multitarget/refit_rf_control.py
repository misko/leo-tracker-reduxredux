"""Matched c=0 / fitted-c physical refits, separate from tracking heuristics.

Hold the same archived reference position, candidate set, observations, TLEs,
priors and solve budgets fixed. Refit timing and RX nuisances in BOTH arms.
This measures in-sample physical-fit sensitivity, not position accuracy.
"""
from pathlib import Path
import json
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
SOURCE = REPORTS / "2026_10_02_ds13_timing_em"
sys.path[:0] = [str(SOURCE), str(REPORTS / "2026_10_02_multiscan_localization"),
               str(REPORTS / "2026_10_02_localization_benchmark"),
               str(REPORTS / "2026_10_02_coherent_localization")]
from all_visible_bank import load_expanded_scan
from position_profile_grid import run_profile
from rf_calibration_diagnostic import CalibrationObjective, rf_features
from plot_tle_doppler_overlay import calibrated_points, orbital_curve
from prediction_plan import SharedPredictionPlan
from rough_smoke import serializable
from finite_set_fit import snapshot_files

SESSIONS = ["scan-fw-911c4e5db9243281", "scan-fw-ffa1cc19d8d7c09f"]


class ZeroRFObjective(CalibrationObjective):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bounds[self.size:] = [(0., 0.)] * (len(self.initial) - self.size)


def main():
    output = HERE / "rf-control"
    output.mkdir(exist_ok=True)
    result = {"scope": __doc__, "scans": [], "source_hashes": snapshot_files([__file__])}
    for label, session in zip(("A", "B"), SESSIONS):
        profile_path = SOURCE / "pruned-position-profile-grid" / f"{session}.json"
        profile = json.loads(profile_path.read_text())
        initial = next(p for p in profile["positions"] if p["label"] == "truth")["best"]
        data = load_expanded_scan(session)
        satellites = np.asarray(profile["satellite_indices"], int)
        scan = dict(scan=label, session=session, arms={})
        result["source_hashes"].update(snapshot_files([profile_path]))
        for arm, factory in (("fitted-c", CalibrationObjective), ("zero-c", ZeroRFObjective)):
            start = None
            attempts = []
            started = time.monotonic()
            for _ in range(5):
                fit = run_profile(data, initial["parameters"], satellites,
                                  initial["rf_coefficient_hz_per_ghz"] if arm == "fitted-c" else [0.],
                                  np.asarray(initial["parameters"][:2]),
                                  probability_override=profile["detection_probability"],
                                  start_vector=start, budget_s=8., objective_factory=factory)
                attempts.append({k: fit[k] for k in ("success", "status", "objective",
                                "projected_nuisance_gradient_inf_norm")})
                start = fit["vector"]
                if fit["success"]:
                    break
            params = np.asarray(fit["parameters"])
            prediction, visibility, _ = SharedPredictionPlan(data, satellites).predict(params)
            prediction = prediction.reshape(len(data.times), len(satellites))
            _, features = rf_features(data.rf, data.receiver, False)
            rf_term = features @ fit["rf_coefficient_hz_per_ghz"]
            rx = np.asarray(data.receiver, int)
            nuisance = params[2 + 2*rx] + params[3 + 2*rx]*(data.times - data.reference_time_s) + rf_term
            points = calibrated_points(data.measured, prediction + rf_term[:, None], data.rf,
                                       nuisance, 1/4.4e-6)
            np.savez_compressed(output / f"{label}-{arm}.npz", **points,
                                parameters=params, visible=visibility.reshape(prediction.shape))
            scan["arms"][arm] = {"fit": fit, "attempts": attempts,
                                   "elapsed_s": time.monotonic()-started}
            print(label, arm, fit["success"], fit["objective"], flush=True)
        result["scans"].append(scan)
        (output / "receipt.json").write_text(json.dumps(serializable(result), indent=2, allow_nan=False)+"\n")


if __name__ == "__main__":
    main()
