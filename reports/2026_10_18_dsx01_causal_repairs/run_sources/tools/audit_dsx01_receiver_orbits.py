"""Check frozen-bank identity and exact SGP4 corrections at joint endpoints."""

import argparse
import json

import numpy as np
from analyze_dsx01_fixed_site import ecef_states
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import Scan
from fit_s01_69333_tle_parameter import perturb
from prototype_dsx01_receiver_geometry import OUTPUT, SOURCE, geometry_problem
from prototype_s01_receiver_drift import ReceiverDriftProblem
from refine_dsx01_exact_receiver_orbits import ExactReferenceFamilies
from sgp4.api import Satrec

from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.sky.propagation import ElementSetCatalogue


def run(refined=False):
    source = OUTPUT / (
        "pooled_exact_refinement/endpoints.json"
        if refined
        else "pooled/orbit_em/mean_10_endpoints.json"
    )
    fit = json.loads(source.read_text())
    records = []
    for number in range(1, 6):
        case = f"DSX01-S0{number}"
        scan = Scan(case)
        seed = json.loads((SOURCE / case / "orbit_em_center.json").read_text())
        for arm, f in fit.items():
            p = geometry_problem(
                scan, seed, "orbit_em", arm == "fitted_c", (0, 0), mean_sigma=10, height_sigma=0
            )
            if refined:
                p = ReceiverDriftProblem(
                    ExactReferenceFamilies(
                        scan,
                        seed,
                        "orbit_em",
                        arm == "fitted_c",
                        (0, 0),
                        reference_extra=f["orbital_reference_states"][case],
                    ),
                    mean_sigma=10,
                )
            x = np.array(f["local_parameters"][case])
            state = p.decode(x)
            satellites = []
            for j in p.labels:
                sat = Satrec.twoline2rv(*scan.elements[str(int(scan.norads[j]))]["lines"])
                ex, ey = state["extra"].get(j, [0, 0])
                sat = perturb(perturb(sat, "e_cos_omega", ex), "e_sin_omega", ey)
                satellites.append(sat)
            nums = tuple(int(scan.norads[j]) for j in p.labels)
            cat = ElementSetCatalogue(tuple(map(str, nums)), nums, tuple(satellites))
            pos, vel, good = ecef_states(cat, scan.receipt["origin_utc_ns"], p.sky["time_s"])
            if not good.all():
                raise ValueError("exact corrected propagation failed")
            exact = dict(time_s=p.sky["time_s"], position_km=pos, velocity_km_s=vel)
            fexact, _ = paired_phase_frequency(
                exact,
                p.flat_times,
                p.flat_labels,
                state["phases"][p.labels],
                f["latitude_deg"],
                f["longitude_deg"],
            )
            ftangent, _ = p.predicted(x)
            q = np.concatenate(
                [
                    np.full(len(scan.tracks[i]["times"]), scan.tracks[i]["rf_hz"] / 11.5e9)
                    for i in p.members
                ]
            )
            delta = q * (fexact - ftangent)
            tangent = p.orbit_sky(state)
            record = dict(
                case=case,
                arm=arm,
                mean_sigma_hz_s=10,
                exact_minus_tangent_native_rms_hz=float(np.sqrt(np.mean(delta**2))),
                exact_minus_tangent_native_max_hz=float(abs(delta).max()),
                maximum_state_difference_m=float(
                    1000 * np.linalg.norm(pos - tangent["position_km"], axis=2).max()
                ),
                original_data_position_phases_hardware_frozen=True,
            )
            records.append(record)
            print(record, flush=True)
    write(
        OUTPUT
        / ("exact_joint_orbit_refined_audit.json" if refined else "exact_joint_orbit_audit.json"),
        records,
    )
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refined", action="store_true")
    run(parser.parse_args().refined)
