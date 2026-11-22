"""Project common external heights through the saved public fixed-owner likelihoods."""

import argparse
from contextlib import contextmanager
from functools import partial
from hashlib import sha256
import json
from pathlib import Path
from time import process_time
from unittest.mock import patch

import numpy as np

from leo.analysis.localization_v3 import recovery_inventory
from leo.analysis.localization_v3.reassociation_context import derivatives, objective
from leo.analysis.research import continuous_curve_fit, orbit_uncertainty
from leo.contracts.algo08_region import Algo08Region
from leo.operations.tle_archive import TleArchiveReader
from leo.presentation.localization_v3 import owner_digest
from leo.sky.frames import geodetic_to_ecef_km
from tools import algo08_position
from tools.pipeline_eval.variants.algo08_causal_reuse import prepare


MEASUREMENTS = Path(__file__).resolve().parent / "measurements"
PINS = {
    "north": ("north-baseline-first.json",
              "b67bbe4885fb5450f45e8eb1cf62f111b3ed3e7ce354afd67c3fd074c07364cb",
              "54ffd828f5cb9b09baa1d38e0f3fdff5b9e41954f74e60226e239fa5c6e4f1d8"),
    "south": ("south-shared.json",
              "ad17d7c1aabc82e527a48da3cdde4af62e3c0dfa020b6a2384be9bf5d3055041",
              "9ead12e735906a95066b77dfcaca54e9bdf68dc0a2c816a95fa3bca3419a3d49"),
}
HEIGHTS_M = (25., 100., 110.)
STEPS_KM = (.025, .050)


def verified(path, digest):
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != digest:
        raise ValueError(f"Saved input digest changed for {path.name}")
    return json.loads(raw)


@contextmanager
def observer_height(altitude_m):
    def observer(latitude, longitude, original_altitude):
        if original_altitude != 0.:
            raise ValueError("Expected zero-height components in the selected problem")
        return geodetic_to_ecef_km(latitude, longitude, altitude_m)

    # These routes supply the paired frequency, elevation, phase derivative and
    # orbital-mode projection for both the curved and predictive likelihoods.
    with (patch.object(continuous_curve_fit, "geodetic_to_ecef_km", observer),
          patch.object(orbit_uncertainty, "geodetic_to_ecef_km", observer)):
        yield


def projections(loss, endpoint):
    rows = {}
    for step in STEPS_KM:
        with observer_height(0.):
            zero_gradient, hessian = derivatives(loss, endpoint, h=step)
        eigenvalues = np.linalg.eigvalsh(hessian)
        if np.min(eigenvalues) <= 0:
            raise ValueError("Baseline horizontal objective has no positive local curvature")
        shifts = {}
        for height in HEIGHTS_M:
            with observer_height(height):
                gradient, _ = derivatives(loss, endpoint, h=step)
            shift = np.linalg.solve(hessian, zero_gradient - gradient)
            shifts[int(height)] = shift.tolist()
        rows[step] = dict(zero_gradient=zero_gradient.tolist(), eigenvalues=eigenvalues.tolist(),
                          shift_km=shifts)
    return rows


def measure(site, native_path, archive_path, assets):
    receipt_name, receipt_pin, native_pin = PINS[site]
    expected = verified(MEASUREMENTS / receipt_name, receipt_pin)["runs"]["baseline"]
    native = verified(native_path, native_pin)
    offer = Algo08Region.parse(expected["receipt"]["region"])
    results = {}

    def audit(context, owners, arms, observations, tracks, **options):
        for arm, (problem, endpoint) in context["problems"].items():
            digest = owner_digest(owners[arm])
            if digest != expected["owners"][arm]:
                raise ValueError("Selected owners differ from the released publication")
            if abs(objective(problem, context, endpoint) - arms[arm]["negative_twice_elbo"]) > 1e-5:
                raise ValueError("Selected objective did not replay at zero height")
            steps = projections(lambda point: objective(problem, context, point), endpoint)
            zero = problem.calculate(endpoint)
            projected = endpoint + steps[STEPS_KM[0]]["shift_km"][100]
            if np.max(np.abs(projected)) >= offer.width_km / 2:
                raise ValueError("Projected endpoint would hit the original search bounds")
            with observer_height(100.):
                raised = problem.calculate(projected)
            rms = [float(np.sqrt(np.mean(terms["conditional_residual_hz"][problem.keep] ** 2)))
                   for terms in (zero, raised)]
            results[arm] = dict(
                owner_sha256=digest, observations=len(owners[arm]), curved_points=int(problem.keep.sum()),
                predictive_tracks=len(context["entries"]), steps=steps, endpoint_km=endpoint.tolist(),
                projected_endpoint_km=projected.tolist(), curved_rms_hz=rms,
            )
        return results

    selected = algo08_position.selected_packet

    def uncached_packet(*args):
        # The normal selected-objective cache keys only on horizontal coordinates.
        with patch.object(recovery_inventory, "cached", lambda problem: problem):
            return selected(*args)

    prepared = partial(prepare, algo08_position.prepare_native_scan, statistics={})
    start = process_time()
    with (patch.object(algo08_position, "prepare_native_scan", prepared),
          patch.object(algo08_position, "selected_packet", uncached_packet),
          patch.object(algo08_position, "prepare_packet", audit)):
        prediction, packet, policy = algo08_position.solve(native, TleArchiveReader(archive_path), assets, offer)
    if prediction["status"] != "ok" or prediction["arms"] != expected["arms"] or packet is not results:
        raise ValueError("Saved zero-height regional prediction did not replay")
    return dict(site=site, native_sha256=native_pin, regional_receipt_sha256=receipt_pin,
                region=offer.document(), orbit_policy=policy, cpu_s=process_time() - start, arms=results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", choices=PINS)
    for name in ("native", "archive", "assets"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    print(json.dumps(measure(args.site, args.native, args.archive, args.assets), allow_nan=False, indent=2))
