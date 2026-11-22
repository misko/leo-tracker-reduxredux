"""Score a predeclared local uncertainty ellipse on the public mirrored offers."""

import argparse
from functools import partial
import gzip
from hashlib import sha256
from importlib import import_module
import json
from math import cos, log, radians
from pathlib import Path
from time import process_time
from unittest.mock import patch

import numpy as np

from leo.analysis.localization_v3.reassociation_context import derivatives, objective
from leo.contracts.algo08_region import Algo08Region
from leo.operations.tle_archive import TleArchiveReader
from leo.presentation.localization_v3 import owner_digest
from tools import algo08_position
from tools.pipeline_eval.variants.algo08_causal_reuse import prepare


inputs = import_module("reports.ALGO08.single-core-2x.mirrored_height_trial")
MIRRORS_SHA256 = "ee8f80ec6267e7fe333d05ac794775fb54bc349cd143022a55599bf2f9af4728"
JOINT_95 = -2 * log(.05)
DISPLACEMENT_KM = .2


def overlap(centre, covariance, half):
    """Return containment of the ellipse and its closest square distance."""
    centre = np.asarray(centre)
    if np.all(np.abs(centre) + np.sqrt(JOINT_95 * np.diag(covariance)) <= half):
        return "inside", 0.
    if np.all(np.abs(centre) <= half):
        return "unresolved", 0.
    precision = np.linalg.inv(covariance)
    distances = []
    for normal, tangent in ((0, 1), (1, 0)):
        for face in (-half, half):
            difference = np.zeros(2)
            difference[normal] = face - centre[normal]
            shift = -precision[tangent, normal] * difference[normal] / precision[tangent, tangent]
            difference[tangent] = np.clip(centre[tangent] + shift, -half, half) - centre[tangent]
            distances.append(float(difference @ precision @ difference))
    closest = min(distances)
    return ("exterior" if closest > JOINT_95 else "unresolved"), closest


def local_frame(latlon, offer):
    lat, lon = latlon
    centre_lat, centre_lon = offer.center
    return np.array([(lon - centre_lon) * 111.32 * cos(radians(centre_lat)), (lat - centre_lat) * 111.])


def curvature(loss, endpoint):
    results = {step: {} for step in inputs.STEPS_KM}
    baseline = loss(endpoint)
    if not np.isfinite(baseline):
        return results
    for step in inputs.STEPS_KM:
        gradient, hessian = derivatives(loss, endpoint, h=step)
        if not np.isfinite(gradient).all() or not np.isfinite(hessian).all():
            continue
        eigenvalues = np.linalg.eigvalsh(hessian)
        row = dict(gradient=gradient.tolist(), eigenvalues=eigenvalues.tolist())
        results[step] = row
        if min(eigenvalues) <= 0:
            continue
        covariance = 2 * np.linalg.inv(hessian)
        profile = []
        for axis in range(2):
            delta = DISPLACEMENT_KM * covariance[:, axis] / covariance[axis, axis]
            losses = [loss(endpoint + sign * delta) - baseline for sign in (-1, 1)]
            profile.append(dict(axis=axis, displacement_km=delta.tolist(), deltas=losses,
                                average_delta=float(np.mean(losses))))
        row.update(covariance_km2=covariance.tolist(), profile=profile)
    return results


def score(arm, anchor, offer):
    covariance = arm["curvature"].get(inputs.STEPS_KM[0], {}).get("covariance_km2")
    if covariance is None or any("covariance_km2" not in row for row in arm["curvature"].values()):
        return dict(state="unresolved", reason="local_curvature_unavailable")
    east_scale = cos(radians(offer.center[0])) / cos(radians(anchor.center[0]))
    transform = np.diag([east_scale, 1.])
    local_covariance = transform @ np.asarray(covariance) @ transform
    centre = local_frame(arm["latlon"], offer)
    state, distance = overlap(centre, local_covariance, offer.width_km / 2)
    return dict(state=state, minimum_mahalanobis_squared=distance, estimate_km=centre.tolist(),
                ellipse_halfwidth_km=np.sqrt(JOINT_95 * np.diag(local_covariance)).tolist())


def measure(site, native_path, archive_path, assets):
    receipt_name, receipt_pin, native_pin = inputs.PINS[site]
    expected = inputs.verified(inputs.MEASUREMENTS / receipt_name, receipt_pin)["runs"]["baseline"]
    native = inputs.verified(native_path, native_pin)
    anchor = Algo08Region.parse(expected["receipt"]["region"])
    arms = {}

    def audit(context, owners, fitted, *_args, **_kwargs):
        for arm, (problem, endpoint) in context["problems"].items():
            digest = owner_digest(owners[arm])
            if digest != expected["owners"][arm]:
                raise ValueError("Selected owners differ from the released publication")
            loss = partial(objective, problem, context)
            if abs(loss(endpoint) - fitted[arm]["negative_twice_elbo"]) > 1e-5:
                raise ValueError("Selected objective did not replay")
            arms[arm] = dict(owner_sha256=digest, observations=len(owners[arm]),
                             curvature=curvature(loss, endpoint))
        return arms

    native_prepare = partial(prepare, algo08_position.prepare_native_scan, statistics={})
    began = process_time()
    with (patch.object(algo08_position, "prepare_native_scan", native_prepare),
          patch.object(algo08_position, "prepare_packet", audit)):
        prediction, packet, policy = algo08_position.solve(native, TleArchiveReader(archive_path), assets, anchor)
    if prediction["status"] != "ok" or prediction["arms"] != expected["arms"] or packet is not arms:
        raise ValueError("Saved regional prediction did not replay")
    for arm, position in prediction["arms"].items():
        arms[arm].update(position)

    # Keep the mirrored offers and their scorer labels downstream of inference.
    source = (inputs.MEASUREMENTS / "region-mirrors.json.gz").read_bytes()
    if sha256(source).hexdigest() != MIRRORS_SHA256:
        raise ValueError("Mirrored offers differ from the predeclared packet")
    mirrors = json.loads(gzip.decompress(source))["sites"][site]
    if any(row["native_sha256"] != native_pin for row in mirrors.values()):
        raise ValueError("Mirrored offers do not share the published detections")
    offers = {label: Algo08Region.parse(row["offer"]) for label, row in mirrors.items()}
    shift = local_frame(offers["inside"].center, offers["outside"])
    axis = int(np.argmax(np.abs(shift)))
    if not np.isclose(np.linalg.norm(shift), DISPLACEMENT_KM) or abs(shift[1-axis]) > 1e-8:
        raise ValueError("Expected the predeclared paired 200 m face shift")
    for arm in arms.values():
        arm["offers"] = {label: score(arm, anchor, offer)
                         for label, offer in dict(positive_control=anchor, **offers).items()}
    paired = {label: all(arm["offers"][label]["state"] == "inside" for arm in arms.values())
              for label in ("positive_control", "inside", "outside")}
    return dict(site=site, native_sha256=native_pin, receipt_sha256=receipt_pin, arms=arms,
                face_axis=axis, paired_publish=paired, orbit_policy=policy, cpu_s=process_time() - began)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", choices=inputs.PINS)
    for name in ("native", "archive", "assets"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    print(json.dumps(measure(args.site, args.native, args.archive, args.assets), allow_nan=False, indent=2))
