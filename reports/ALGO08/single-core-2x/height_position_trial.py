"""Score the receiver-height model on sparse, disjoint saved-orbit simulations."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from time import process_time

import numpy as np

from leo.analysis.localization_v3.orbits import ecef_states
from leo.analysis.localization_v3.region import SearchRegion
from leo.analysis.research.orbit_phase_geometry import phase_shifted_states
from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km, look_angles
from leo.sky.propagation import ElementSetCatalogue, parse_element_sets
from tools.pipeline_eval.scoring import distance_km

from .height_position_model import Geometry, PHASE_STEP_S, SIGMA_HZ, fit, synthesize


SEED = 261124
REGIONS = ((15., 75.), (-25., -65.), (65., 120.))
HEIGHT_KM = (0.1, 1.25, 2.25)
# Counts are orbits, held orbits, points per orbit, and nominal duration in seconds.
SUPPORTS = {"short": (8, 3, 6, 40), "long": (12, 4, 10, 120)}
COARSE_TIMES = np.arange(0., 301., 5.)


def subset(catalogue, chosen):
    return ElementSetCatalogue(*(tuple(getattr(catalogue, column)[i] for i in chosen)
                                 for column in ("names", "satellite_numbers", "satellites")))


def snapshot_bank(path):
    raw = path.read_bytes()
    stamp, expected = path.stem.split("-", 1)
    if sha256(raw).hexdigest() != expected:
        raise ValueError("Saved snapshot digest mismatch")
    origin = int(stamp)
    all_elements = parse_element_sets(raw.decode())
    age = origin - np.array(all_elements.element_epoch_utc_ns())
    use = [i for i in np.flatnonzero((age >= 0) & (age <= 48 * 3600 * 10**9))
           if "STARLINK" in all_elements.names[i].upper()]
    catalogue = subset(all_elements, use)
    position, velocity, usable = ecef_states(catalogue, origin, COARSE_TIMES)
    return origin, catalogue, position, velocity, usable


def groups(receiver, held_count, rng):
    held = np.concatenate([rng.choice(np.flatnonzero(receiver == lane), (held_count + 1 - lane) // 2,
                                      replace=False) for lane in (0, 1)])
    training = np.ones(len(receiver), dtype=bool)
    training[held] = False
    return training


def make_geometry(bank, region, rng, support):
    origin, catalogue, position, velocity, usable = bank
    tracks, held, observations, span = support
    width = span // 5 + 1
    observer = geodetic_to_ecef_km(*region.center, 0.)
    _, elevation, _, _ = look_angles(position, velocity, observer, ecef_to_enu_matrix(*region.center))
    arc = np.lib.stride_tricks.sliding_window_view(elevation, width, axis=1)
    starts = (arc.min(axis=2) >= 10.) & usable[:, None]
    visible = np.flatnonzero(starts.any(axis=1))
    chosen = rng.choice(visible, tracks, replace=False)
    times, positions, velocities = [], [], []
    for orbit in chosen:
        first = rng.choice(np.flatnonzero(starts[orbit]))
        interior = rng.choice(np.arange(1, width - 1), observations - 2, replace=False)
        t = COARSE_TIMES[first + np.sort(np.r_[0, interior, width - 1])] + rng.uniform(.05, .45)
        knots = np.arange(np.floor(t[0]) - 1, np.ceil(t[-1]) + 2)
        p, v, good = ecef_states(subset(catalogue, [orbit]), origin, knots)
        if not good.all():
            raise ValueError("A predeclared satellite arc failed propagation")
        orbit_bank = dict(time_s=knots, position_km=p, velocity_km_s=v)
        p, v = zip(*(phase_shifted_states(orbit_bank, t, h) for h in
                     (0., PHASE_STEP_S, -PHASE_STEP_S)), strict=True)
        times.append(t)
        positions.append(np.concatenate(p, axis=0))
        velocities.append(np.concatenate(v, axis=0))
    receiver = np.arange(tracks) % 2
    rf = np.linspace(10.7e9, 12.65e9, 8)[rng.permutation(np.arange(tracks) % 8)]
    training = groups(receiver, held, rng)
    geometry = Geometry(np.stack(positions, axis=1), np.stack(velocities, axis=1), np.stack(times), receiver, rf)
    identities = np.asarray(catalogue.satellite_numbers)[chosen]
    evidence = dict(elevation_eligible=len(visible), identities=identities.tolist(),
                    training=identities[training].tolist(), held=identities[~training].tolist(),
                    times_s=geometry.times.tolist(), receiver=receiver.tolist(), rf_hz=rf.tolist())
    return geometry, training, evidence


def measure(snapshot):
    started = process_time()
    bank = snapshot_bank(snapshot)
    preparation_cpu = process_time() - started
    cases = []
    for site_index, center in enumerate(REGIONS):
        region = SearchRegion(center, width_km=25.)
        truth_xy = np.random.default_rng([SEED, 1, site_index]).uniform(-8., 8., 2)
        truth_ll = region.latlon(truth_xy)
        for support_index, (name, support) in enumerate(SUPPORTS.items()):
            design_rng = np.random.default_rng([SEED, 2, site_index, support_index])
            geometry, training, design = make_geometry(bank, region, design_rng, support)
            levels = []
            for height in HEIGHT_KM:
                planted = np.r_[truth_xy, height]
                noise_rng = np.random.default_rng([SEED, 3, site_index, support_index])
                measured = synthesize(region, geometry, planted, noise_rng)
                arms = {}
                for fitted in (False, True):
                    for height_free in (False, True):
                        label = ("fitted_c" if fitted else "c0") + ("_free" if height_free else "_zero")
                        result = fit(region, geometry, measured, training, fit_height=height_free, fitted_c=fitted)
                        result.pop("prediction")
                        xyz = result["position_km"]
                        result.update(horizontal_error_km=distance_km(region.latlon(xyz), truth_ll),
                                      height_error_km=abs(xyz[2] - height))
                        arms[label] = result
                levels.append(dict(truth_height_km=height, arms=arms))
            cases.append(dict(region_center=center, trajectory_support=name, truth_xy_km=truth_xy.tolist(),
                              design=design, levels=levels))
    return dict(snapshot=snapshot.name, causal_orbits=len(bank[1]), seed=SEED, sigma_hz=SIGMA_HZ,
                preparation_cpu_s=preparation_cpu, total_cpu_s=process_time() - started, cases=cases)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    print(json.dumps(measure(parser.parse_args().snapshot), allow_nan=False))
