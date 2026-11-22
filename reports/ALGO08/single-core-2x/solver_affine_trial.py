"""Time fixed-weight conditional geometry scores on the same saved solve inputs."""

import argparse
from functools import partial
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
from time import process_time
from unittest.mock import patch

import numpy as np
from scipy.linalg import cho_factor, cho_solve

from leo.analysis.localization_v3.marginal import JointMarginal
from leo.analysis.localization_v3.recovery_inventory import recovery_context
from leo.contracts.algo08_region import Algo08Region
from leo.operations.tle_archive import TleArchiveReader
from tools import algo08_position
from tools.pipeline_eval.variants import algo08_causal_reuse
from tools.pipeline_eval.variants.algo08_affine_statistics import AffineScore


def compare(p, endpoint, powers):
    evaluate = getattr(p, "curved_calculate", p.calculate)
    calculated = evaluate(endpoint)
    prior = calculated["coefficient_prior_precision"]
    prior_center = calculated["coefficient"] - calculated["latent_coefficient"]
    weight = (powers * calculated["noise_precision"])[p.noise_groups[p.keep]]
    sigma = p.point_noise[p.keep]
    half = p.scan.search_region.half_width_km
    grid = np.array(list(product(np.linspace(-half, half, 9), repeat=2)))
    weighted = np.sqrt(weight) / sigma
    priors, prior_log = np.diag(prior), np.log(prior).sum()

    def rows(point):
        geometry = JointMarginal.calculate(p, point, geometry_only=True)
        design = geometry["features"][p.keep]
        response = (p.values - p.q * geometry["intercept"])[p.keep] - design @ prior_center
        return np.column_stack((design, response))

    def direct(point):
        full = rows(point) * weighted[:, None]
        a, y = full[:, :-1], full[:, -1]
        root = cho_factor(priors + a.T @ a, lower=True)
        coefficients = cho_solve(root, a.T @ y)
        error = y - a @ coefficients
        volume = 2 * np.log(np.diag(root[0])).sum() - prior_log
        return float(error @ error + (prior * coefficients) @ coefficients + volume)

    start = process_time()
    exact = np.array([direct(point) for point in grid])
    exact_cpu = process_time() - start

    def evaluate_patches(quadrants):
        centers = tuple(product((-half / 2, half / 2), repeat=2)) if quadrants else ((0, 0),)
        directions = np.eye(2) * 0.001
        start = process_time()
        patches = {}
        for center in centers:
            derivatives = [(rows(center + step) - rows(center - step)) / 0.002
                           for step in directions]
            patches[center] = AffineScore(np.stack((rows(center), *derivatives)), sigma,
                                         weight, prior)
        scores = []
        for point in grid:
            center = tuple(np.copysign(half / 2, point)) if quadrants else (0, 0)
            scores.append(patches[center].score(*(point - center)))
        cpu = process_time() - start
        scores = np.asarray(scores)
        error = np.abs(scores - exact)
        best = grid[int(np.argmin(scores))]
        expected = grid[int(np.argmin(exact))]
        return dict(cpu_s=cpu, exact_geometry_evaluations=5*len(centers),
                    max_score_error=float(error.max()), median_score_error=float(np.median(error)),
                    grid_minimum_movement_km=float(np.linalg.norm(best - expected)),
                    grid_score_span=float(np.ptp(exact)))

    return dict(physical_cpu_s=exact_cpu, points=len(grid), rows=int(p.keep.sum()),
                one=evaluate_patches(False), four=evaluate_patches(True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("native", "archive", "assets", "region"):
        parser.add_argument(name, type=Path)
    parser.add_argument("native_sha256")
    args = parser.parse_args()
    raw = args.native.read_bytes()
    if sha256(raw).hexdigest() != args.native_sha256.removeprefix("sha256:"):
        raise ValueError("Native detections differ from their declared digest")
    region = Algo08Region.parse(json.loads(args.region.read_bytes()))

    def scores(_prepared, signed, fit):
        if fit is None:
            fit = dict(status="complete", accepted=False, baseline_node=signed["node"],
                       baseline_entries=signed["entries"], baseline_means=signed["means"],
                       original_mask=signed["keep"], powers=signed["powers"], model=signed["model"],
                       policy_arms=signed["arms"])
        context = recovery_context(signed["scan"], fit)
        return {arm: compare(problem, point, context["powers"])
                for arm, (problem, point) in context["problems"].items()}

    with (
        patch.object(algo08_position, "selected_packet", scores),
        patch.object(algo08_position, "prepare_native_scan", partial(
            algo08_causal_reuse.prepare, algo08_position.prepare_native_scan, statistics={}
        )),
    ):
        decision, comparisons, policy = algo08_position.solve(json.loads(raw),
            TleArchiveReader(args.archive), args.assets, region)
    print(json.dumps(dict(decision=decision, comparisons=comparisons, orbit_policy=policy,
                          native_sha256=args.native_sha256), allow_nan=False))


if __name__ == "__main__":
    main()
