"""Replay frozen wide-search assignments with independent Astropy frame conversion.

Requires the optional astropy research dependency and an explicit IERS table.
No antenna reference or new observations are accepted.
"""

import argparse
import json
from pathlib import Path

import astropy
import astropy.units as u
import numpy as np
from astropy.coordinates import (
    ITRS,
    TEME,
    CartesianDifferential,
    CartesianRepresentation,
    EarthLocation,
)
from astropy.time import Time
from astropy.utils import iers
from compare_positioning_cohorts import fit
from replay_regional_doppler import digest, load_observations, write_json

from leo.analysis.research.regional_doppler import Region
from leo.sky.frames import geodetic_to_ecef_km
from leo.sky.propagation import parse_element_sets


def itrs_states(satellite, utc_ns):
    seconds, ns = np.divmod(utc_ns, 1_000_000_000)
    time = Time(seconds, ns / 1e9, format="unix", scale="utc")
    errors, p, v = satellite.sgp4_array(time.utc.jd1, time.utc.jd2)
    if np.any(errors):
        raise ValueError("SGP4 error in frozen assignment")
    representation = CartesianRepresentation(p.T * u.km).with_differentials(
        CartesianDifferential(v.T * u.km / u.s)
    )
    earth = TEME(representation, obstime=time).transform_to(ITRS(obstime=time))
    return earth.cartesian.xyz.to_value(u.km).T, earth.velocity.d_xyz.to_value(u.km / u.s).T


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["run", "evidence", "iers", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("fresh output required")
    iers.conf.auto_download = False
    iers.earth_orientation_table.set(iers.IERS_A.open(str(args.iers)))
    parent = json.loads((args.run / "inference.json").read_text())
    if (
        not parent["complete"]
        or parent["position_truth_used"]
        or parent["prior_matched_norads_used"]
    ):
        raise ValueError("independent completed parent required")
    data = dict(np.load(args.run / "states.npz"))
    baseline = {k: v.copy() for k, v in data.items()}
    documents, catalogues, sources = {}, {}, {}
    for episode, assignment in enumerate(parent["assignments"]):
        sid = assignment["session_id"]
        if sid not in documents:
            path = args.evidence / "evidence" / (sid + ".json")
            sources[str(path)] = digest(path)
            documents[sid] = json.loads(path.read_text())
        document = documents[sid]
        meta = document["inventory"]
        path = args.evidence / "evidence" / meta["tle_file"]
        if str(path) not in catalogues:
            sources[str(path)] = digest(path)
            if sources[str(path)] != meta["tle_digest"]:
                raise ValueError("TLE digest mismatch")
            cat = parse_element_sets(path.read_text())
            catalogues[str(path)] = dict(zip(cat.satellite_numbers, cat.satellites, strict=True))
        arc = dict(load_observations(document, 0))[assignment["episode_id"]]
        mask = data["episode"] == episode
        if not np.array_equal(data["y"][mask], arc.frequency_hz) or not np.array_equal(
            data["training"][mask], arc.training
        ):
            raise ValueError("frozen observation/partition mismatch")
        for shift in [0.0, -0.5, 0.5]:
            utc_ns = meta["reference_utc_ns"] + np.rint((arc.time_s + shift) * 1e9).astype(np.int64)
            p, v = itrs_states(catalogues[str(path)][assignment["norad"]], utc_ns)
            suffix = "" if shift == 0 else str(shift)
            data["p" + suffix][mask], data["v" + suffix][mask] = p, v
    coordinate_errors = []
    for lat, lon, alt in [(0, 0, 0), (40, -100, 0), (-60, 150, 1234), (80, -170, -50)]:
        independent = EarthLocation.from_geodetic(lon * u.deg, lat * u.deg, alt * u.m)
        coordinate_errors.append(
            float(
                np.linalg.norm(
                    np.array([x.to_value(u.km) for x in independent.geocentric])
                    - geodetic_to_ecef_km(lat, lon, alt)
                )
                * 1000
            )
        )
    output = dict(
        evaluation_location_used=False,
        astropy_version=astropy.__version__,
        parent_digest=digest(args.run / "inference.json"),
        iers_digest=digest(args.iers),
        source_digests=sources,
        geodetic_check_max_difference_m=max(coordinate_errors),
        position_difference_m=dict(
            median=float(np.median(np.linalg.norm(data["p"] - baseline["p"], axis=1)) * 1000),
            maximum=float(np.max(np.linalg.norm(data["p"] - baseline["p"], axis=1)) * 1000),
        ),
        velocity_difference_m_s=dict(
            median=float(np.median(np.linalg.norm(data["v"] - baseline["v"], axis=1)) * 1000),
            maximum=float(np.max(np.linalg.norm(data["v"] - baseline["v"], axis=1)) * 1000),
        ),
        models=[],
    )
    ids = [i for i, a in enumerate(parent["assignments"]) if a in parent["selected_assignments"]]
    for selection, mask in [("all", None), ("selected", np.isin(data["episode"], ids))]:
        for clock in [False, True]:
            result = fit(
                data,
                Region(**parent["region"]),
                parent["initial"],
                "observation",
                True,
                subset=mask,
                fit_clock=clock,
            )
            output["models"].append(dict(selection=selection, **result))
            print(selection, clock, result["latitude_deg"], result["longitude_deg"], flush=True)
    write_json(args.output, output)


if __name__ == "__main__":
    main()
