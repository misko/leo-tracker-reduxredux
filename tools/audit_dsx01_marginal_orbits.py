"""Exact-SGP4 checks for the new independent sub-kilometre prototype endpoints."""

import json

import numpy as np
from analyze_dsx01_fixed_site import ecef_states
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import Scan
from fit_s01_69333_tle_parameter import perturb
from probe_dsx01_scan_influence import OUTPUT
from prototype_dsx01_mean_motion import reference_motion_satellite
from prototype_dsx01_orbit_marginal import marginal_problem, variant_options
from report_dsx01_model_iterations import nominated_metrics
from sgp4.api import Satrec

from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.sky.propagation import ElementSetCatalogue


def run():
    records = []
    for case, method, variant in [
        ("DSX01-S01", "receiver_smooth", "student_physical"),
        ("DSX01-S04", "orbit_em", "hierarchy_physical"),
    ]:
        scan = Scan(case)
        fits = json.loads((OUTPUT / "marginal" / case / method / "endpoints.json").read_text())
        options = variant_options(variant)
        for arm in ("c0", "fitted_c"):
            fit = fits[f"{variant}/{arm}"]
            args = (
                scan,
                dict(rows=fit["rows"], state=fit["state"]),
                method,
                arm == "fitted_c",
                fit["east_north_km"],
            )
            p = marginal_problem(*args, **options)
            p.problem.alias = fit["aliases"]
            x = np.array(min(fit["fits"], key=lambda f: f["score"])["parameters"])
            state = p.association_state(x)
            _, _, coefficients, *_ = p.problem.calculate(p.native_parameters(x))
            satellites = []
            for j in p.labels:
                sat = Satrec.twoline2rv(*scan.elements[str(int(scan.norads[j]))]["lines"])
                if method == "orbit_em":
                    ex, ey = state["extra"].get(j, [0, 0])
                    sat = perturb(perturb(sat, "e_cos_omega", ex), "e_sin_omega", ey)
                if j in p.supported:
                    meta = p.mode_metadata[j]
                    a = coefficients[j]
                    elapsed = (
                        (scan.receipt["origin_utc_ns"] / 1e9 + 150) / 86400
                        + 2440587.5
                        - sat.jdsatepoch
                        - sat.jdsatepochF
                    )
                    sat = reference_motion_satellite(
                        sat, a[0] * meta["mean_motion_sigma_rev_day"], elapsed
                    )
                    sat = perturb(sat, "inclination_deg", a[1] * meta["inclination_sigma_deg"])
                    sat = perturb(sat, "raan_deg", a[2] * meta["raan_sigma_deg"])
                satellites.append(sat)
            numbers = tuple(int(scan.norads[j]) for j in p.labels)
            cat = ElementSetCatalogue(tuple(map(str, numbers)), numbers, tuple(satellites))
            pos, vel, good = ecef_states(cat, scan.receipt["origin_utc_ns"], p.sky["time_s"])
            assert good.all()
            bank = dict(time_s=p.sky["time_s"], position_km=pos, velocity_km_s=vel)
            f, e = paired_phase_frequency(
                bank,
                p.flat_times,
                p.flat_labels,
                state["phases"][p.labels],
                fit["latitude_deg"],
                fit["longitude_deg"],
            )
            for j, bias in state.get("marginal_satellite_bias_hz", {}).items():
                f[p.flat_labels == p.local_j[j]] += bias
            lifted, _ = p.predicted(x)
            q = np.concatenate(
                [
                    np.full(len(scan.tracks[i]["times"]), scan.tracks[i]["rf_hz"] / 11.5e9)
                    for i in p.members
                ]
            )
            delta = q * (f - lifted)
            item = dict(experiment="marginal", method=method, variant=variant, arm=arm, fit=fit)

            def factory(*args, config=options):
                return marginal_problem(*args, **config)

            original = nominated_metrics(scan, item, problem_factory=factory)

            def exact_factory(*args, config=options, ff=f, ee=e):
                result = marginal_problem(*args, **config)
                result.predicted = lambda x: (ff, ee)
                return result

            exact = nominated_metrics(scan, item, problem_factory=exact_factory)
            record = dict(
                case=case,
                method=method,
                variant=variant,
                arm=arm,
                exact_minus_lifted_native_rms_hz=float(np.sqrt(np.mean(delta**2))),
                exact_minus_lifted_native_max_hz=float(abs(delta).max()),
                accepted_nominated_points_lifted=original["accepted_nominated_curved_points"],
                accepted_nominated_points_exact=exact["accepted_nominated_curved_points"],
                location_hardware_phase_and_mode_coefficients_frozen=True,
            )
            records.append(record)
            print(record, flush=True)
    write(OUTPUT / "independent_exact_orbit_audit.json", records)
    return records


if __name__ == "__main__":
    run()
