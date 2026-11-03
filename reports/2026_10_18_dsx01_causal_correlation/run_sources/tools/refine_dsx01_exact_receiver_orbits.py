"""Relinearize orbital corrections around exact SGP4 joint-fit endpoints.

This is a blind continuation: its starts and orbital reference states come
only from the completed Mill Valley fits, never the evaluation GPS.
"""

import hashlib
import json
import time
from pathlib import Path

import numpy as np
from analyze_dsx01_fixed_site import ecef_states
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import Scan
from fit_s01_69333_tle_parameter import perturb
from iterate_dsx01_position_nominations import AnchoredFamilies
from prototype_dsx01_continuous_position import latlon
from prototype_dsx01_pooled_position import Pool
from prototype_dsx01_receiver_geometry import OUTPUT, SOURCE
from prototype_s01_receiver_drift import ReceiverDriftProblem
from sgp4.api import Satrec

from leo.analysis.research.factor_position_fit import factor_gauss_newton
from leo.sky.propagation import ElementSetCatalogue


def corrected_satellite(scan, j, extra):
    sat = Satrec.twoline2rv(*scan.elements[str(int(scan.norads[j]))]["lines"])
    ex, ey = extra.get(j, [0, 0])
    return perturb(perturb(sat, "e_cos_omega", ex), "e_sin_omega", ey)


def exact_corrected_bank(scan, labels, extra):
    numbers = tuple(int(scan.norads[j]) for j in labels)
    cat = ElementSetCatalogue(
        tuple(map(str, numbers)),
        numbers,
        tuple(corrected_satellite(scan, j, extra) for j in labels),
    )
    p, v, good = ecef_states(cat, scan.receipt["origin_utc_ns"], scan.sky["time_s"])
    if not good.all():
        raise ValueError("exact corrected satellite propagation failed")
    return dict(time_s=scan.sky["time_s"], position_km=p, velocity_km_s=v)


def exact_reference(scan, labels, extra):
    satellites = []
    for j in labels:
        current = corrected_satellite(scan, j, extra)
        satellites.append(current)
        if j in extra:
            for parameter in ("e_cos_omega", "e_sin_omega"):
                satellites.extend(perturb(current, parameter, d) for d in (2e-5, -2e-5))
    numbers = tuple(s.satnum for s in satellites)
    cat = ElementSetCatalogue(tuple(map(str, numbers)), numbers, tuple(satellites))
    pos, vel, good = ecef_states(cat, scan.receipt["origin_utc_ns"], scan.sky["time_s"])
    if not good.all():
        raise ValueError("exact orbital reference propagation failed")
    pp, vv, basis = [], [], {}
    offset = 0
    for j in labels:
        pp.append(pos[offset])
        vv.append(vel[offset])
        offset += 1
        if j in extra:
            basis[j] = (
                np.array(
                    [
                        (pos[offset] - pos[offset + 1]) / 4e-5,
                        (pos[offset + 2] - pos[offset + 3]) / 4e-5,
                    ]
                ),
                np.array(
                    [
                        (vel[offset] - vel[offset + 1]) / 4e-5,
                        (vel[offset + 2] - vel[offset + 3]) / 4e-5,
                    ]
                ),
            )
            offset += 4
    return dict(
        time_s=scan.sky["time_s"], position_km=np.array(pp), velocity_km_s=np.array(vv)
    ), basis


class ExactReferenceFamilies(AnchoredFamilies):
    def __init__(
        self, scan, seed, method, fitted_c, anchor, *, reference_extra, reference_geometry=None
    ):
        self.reference_bank = None
        super().__init__(scan, seed, method, fitted_c, anchor)
        if method != "orbit_em":
            raise ValueError("orbital relinearization requires orbit_em")
        self.reference_extra = {int(j): np.array(v) for j, v in reference_extra.items()}
        self.reference_bank, self.reference_basis = (
            reference_geometry
            if reference_geometry is not None
            else exact_reference(scan, self.labels, self.reference_extra)
        )

    def orbit_sky(self, state):
        if self.reference_bank is None:
            return super().orbit_sky(state)
        sky = {k: v.copy() for k, v in self.reference_bank.items()}
        for j, coefficient in state["extra"].items():
            delta = coefficient - self.reference_extra[j]
            dp, dv = self.reference_basis[j]
            k = self.local_j[j]
            sky["position_km"][k] += np.einsum("k,ktd->td", delta, dp)
            sky["velocity_km_s"][k] += np.einsum("k,ktd->td", delta, dv)
        return sky


def run():
    source = OUTPUT / "pooled/orbit_em/mean_10_endpoints.json"
    inherited = json.loads(source.read_text())
    directory = OUTPUT / "pooled_exact_refinement"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "endpoints.json"
    if path.exists():
        return json.loads(path.read_text())
    scans = [Scan(f"DSX01-S0{k}") for k in range(1, 6)]
    seeds = [
        {"c0/orbit_em": json.loads((SOURCE / s.case / "orbit_em_center.json").read_text())}
        for s in scans
    ]
    starts = [f["parameters"][:2] for f in inherited["c0"]["fits"]]
    write(
        directory / "protocol.json",
        dict(
            no_reference_GPS_or_oracle_initialization=True,
            inherited_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            exact_SGP4_relinearization_at_inherited_orbital_coefficients=True,
            original_zero_mean_orbit_priors_unchanged=True,
            common_c0_geographic_starts_for_both_arms=starts,
            iterations_per_start=24,
            same_curved_points_nominations_aliases_candidate_sets_and_priors_for_c_arms=True,
            stationary_receiver_site_assumption=True,
            mean_RX_drift_sigma_hz_s=10,
            band_contrast_sigma_hz_s=0.5,
            derivative_step_eccentricity=2e-5,
            code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        ),
    )
    results = {}
    for arm, old in inherited.items():
        reference = {
            case: {int(j): np.array(v) for j, v in state["extra"].items()}
            for case, state in old["states"].items()
        }

        def factory(scan, seed, method, variant, fitted_c, refs=reference):
            return ReceiverDriftProblem(
                ExactReferenceFamilies(
                    scan, seed, method, fitted_c, (0, 0), reference_extra=refs[scan.case]
                ),
                mean_sigma=10,
            )

        pool = Pool(scans, seeds, "orbit_em", arm, "independent_phase", problem_factory=factory)
        assert [list(n) for n in pool.names] == old["names"]
        initial = np.array(min(old["fits"], key=lambda f: f["score"])["parameters"])
        mark, fits = time.monotonic(), []
        for point in starts:
            x = initial.copy()
            x[:2] = point
            fits.append(
                factor_gauss_newton(
                    pool.functions, pool.mappings, x, pool.lower, pool.upper, iterations=24
                )
            )
        best = min(fits, key=lambda f: f["score"])
        x = best["parameters"]
        results[arm] = dict(
            latitude_deg=latlon(x[:2])[0],
            longitude_deg=latlon(x[:2])[1],
            east_north_km=x[:2],
            score=best["score"],
            fits=fits,
            starts=starts,
            states={
                s.case: p.decode(x[m])
                for s, p, m in zip(scans, pool.problems, pool.mappings, strict=True)
            },
            local_parameters={s.case: x[m] for s, m in zip(scans, pool.mappings, strict=True)},
            orbital_reference_states=reference,
            aliases={s.case: p.alias for s, p in zip(scans, pool.problems, strict=True)},
            seconds=time.monotonic() - mark,
        )
        print(arm, list(x[:2]), best["score"], flush=True)
    write(path, results)
    return results


if __name__ == "__main__":
    run()
