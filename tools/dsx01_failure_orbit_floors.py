"""Conservative radial/normal TLE covariance floors, with no location input."""

import argparse
import copy
import hashlib
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from dsx01_joint_exact_mean import exact_conditional_frequency
from investigate_dsx01_localization_failures import OUTPUT, DiagnosticNormal, context, fit
from run_dsx01_joint_descent import ARMS, CASES

FLOORS_KM = ((.1, .05), (.5, .25), (1., .5))


def inflate_modes(bank, metadata, labels, radial_floor, normal_floor):
    if min(radial_floor, normal_floor) <= 0:
        raise ValueError("positive physical uncertainty floors required")
    result, details = dict(bank), copy.deepcopy(metadata)
    gain = np.ones((len(labels), 3))
    for k, j in enumerate(labels):
        if j not in details:
            continue
        m = details[j]
        gain[k, 0] = max(1., radial_floor / m["radial_sigma_km"])
        gain[k, 1:] = max(1., normal_floor / m["cross_sigma_km"])
        m["radial_sigma_km"] *= gain[k, 0]
        m["cross_sigma_km"] *= gain[k, 1]
        m["mean_motion_sigma_rev_day"] *= gain[k, 0]
        m["inclination_sigma_deg"] *= gain[k, 1]
        m["raan_sigma_deg"] *= gain[k, 2]
    for key in ("position_km", "velocity_km_s"):
        shape = bank[key].shape
        result[key] = (bank[key].reshape(len(labels), 3, *shape[1:])
                       * gain[:, :, None, None]).reshape(shape)
    return result, details


def run(case):
    scan, sigma, node, _, bindings, _ = context(case)
    rows = []
    for radial, normal in FLOORS_KM:
        for arm in ARMS:
            reference = np.zeros(len({r["candidate_index"] for r in node["seed"]["rows"]}))
            anchor, history = np.zeros(2), []
            for epoch in range(5):
                p = DiagnosticNormal(scan, node, sigma, arm == "fitted_c", reference=reference)
                p.mode_bank, p.mode_metadata = inflate_modes(
                    p.mode_bank, p.mode_metadata, p.labels, radial, normal)
                result = fit(p, anchor)
                anchor = np.array(result["parameters"])
                reference = np.clip(p.state(anchor)["phases"][p.labels], -15, 15)
                history.append(dict(epoch=epoch, fit=result))
            exact, _, parameters = exact_conditional_frequency(p, anchor)
            tangent, _ = p.conditional_frequency(anchor)
            rows.append(dict(control=f"orbit_floor_{radial}_{normal}", radial_floor_km=radial,
                             normal_floor_km=normal, arm=arm, fit=result, history=history,
                             reference=p.reference, physical_parameters=parameters,
                             exact_minus_tangent_rms_hz=float(np.sqrt(np.mean(
                                 ((exact - tangent) * p.q)**2)))))
        print(case, "orbit floors", radial, normal, flush=True)
    return dict(case=case, interventions=rows, source_bindings=bindings, GPS_used=False,
                no_physical_parameters_added=True, nominal_causal_TLE_unchanged=True,
                causal_cache_not_mutated=True,
                engineering_covariance_hypotheses_not_calibrated_confidence=True,
                code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES, required=True)
    args = parser.parse_args()
    path = OUTPUT / args.case / "orbit_floors.json"
    if not path.exists():
        write(path, dict(run(args.case), status="complete"))
