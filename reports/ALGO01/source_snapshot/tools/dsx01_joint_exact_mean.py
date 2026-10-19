"""Check tangent orbital mean predictions against combined exact SGP4 changes."""

from analyze_dsx01_fixed_site import ecef_states
from fit_s01_69333_tle_parameter import perturb
from prototype_dsx01_continuous_position import latlon
from prototype_dsx01_mean_motion import reference_motion_satellite
from sgp4.api import Satrec

from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.sky.propagation import ElementSetCatalogue


def exact_conditional_frequency(problem, x):
    """Apply the fitted physical-mode parameters jointly to each causal TLE.

    This validates a conditional mean, not its Gaussian uncertainty law or
    satellite identity. The parameter priors and search are not modified.
    """
    p = problem
    result = p.calculate(x)
    a = result["coefficient"]
    begin = p.hardware.shape[1] + p.smooth.shape[1] + len(p.labels)
    supported = {j: k for k, j in enumerate(p.supported)}
    satellites, parameters = [], {}
    for j in p.labels:
        satellite = Satrec.twoline2rv(*p.scan.elements[str(int(p.scan.norads[j]))]["lines"])
        if j in supported:
            k = supported[j]
            metadata = p.mode_metadata[j]
            scales = result["scales"][2]
            shifts = dict(
                mean_motion_rev_day=a[begin + 3 * k]
                * metadata["mean_motion_sigma_rev_day"]
                * scales,
                inclination_deg=a[begin + 3 * k + 1] * metadata["inclination_sigma_deg"] * scales,
                raan_deg=a[begin + 3 * k + 2] * metadata["raan_sigma_deg"] * scales,
            )
            if getattr(p, "ecc_bank", None) is not None:
                start = begin + 3 * len(p.supported) + 2 * k
                shifts.update(
                    e_cos_omega=a[start] * p.ecc_metadata[j]["sigma"][0],
                    e_sin_omega=a[start + 1] * p.ecc_metadata[j]["sigma"][1],
                )
            elapsed_days = (
                (p.scan.receipt["origin_utc_ns"] / 1e9 + 150) / 86400
                + 2440587.5
                - satellite.jdsatepoch
                - satellite.jdsatepochF
            )
            satellite = reference_motion_satellite(
                satellite, shifts["mean_motion_rev_day"], elapsed_days
            )
            for name, delta in shifts.items():
                if name != "mean_motion_rev_day":
                    satellite = perturb(satellite, name, delta)
            parameters[j] = shifts
        satellites.append(satellite)
    numbers = tuple(int(p.scan.norads[j]) for j in p.labels)
    catalogue = ElementSetCatalogue(tuple(map(str, numbers)), numbers, tuple(satellites))
    position, velocity, good = ecef_states(
        catalogue, p.scan.receipt["origin_utc_ns"], p.sky["time_s"]
    )
    if not good.all():
        raise ValueError("jointly corrected orbital parameters failed exact SGP4 propagation")
    sky = dict(time_s=p.sky["time_s"], position_km=position, velocity_km_s=velocity)
    phase = p.state(x)["phases"][p.labels]
    frequency, elevation = paired_phase_frequency(
        sky, p.flat_times, p.flat_labels, phase, *latlon(x[:2])
    )
    return frequency, elevation, parameters
