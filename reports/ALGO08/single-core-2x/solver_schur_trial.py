"""Differential test of sparse joint blocks from a saved ALGO08v2 solver input."""

import argparse
from functools import partial
from hashlib import sha256
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scipy.linalg import cho_factor, cho_solve

from leo.analysis.localization_v3.marginal import JointMarginal
from leo.analysis.localization_v3.recovery_inventory import recovery_context
from leo.contracts.algo08_region import Algo08Region
from leo.operations.tle_archive import TleArchiveReader
from tools import algo08_position
from tools.pipeline_eval.variants import algo08_causal_reuse, algo08_family_schur


def dense_moments(design, raw, sigma, groups, weights, prior):
    a, y = design / sigma[:, None], raw / sigma
    gram = np.diag(prior) + a.T @ (weights[groups, None] * a)
    root = cho_factor(gram, lower=True)
    mu = cho_solve(root, a.T @ (weights[groups] * y))
    covariance = cho_solve(root, np.eye(len(prior)))
    energy = np.bincount(groups, weights=(y - a @ mu)**2, minlength=len(weights))
    variance = np.bincount(groups, weights=np.einsum("ij,ij->i", a @ covariance, a),
                           minlength=len(weights))
    logdet = float(2 * np.log(np.diag(root[0])).sum() - np.log(prior).sum())
    return mu, np.diag(covariance), logdet, energy, variance


def errors(actual, expected):
    return dict(zip(("coefficient", "marginal_variance", "logdet", "group_energy",
                     "group_variance"),
                    (float(np.max(np.abs(a - b))) for a, b in zip(actual, expected, strict=True)),
                    strict=True))


def differential(problem, point, powers):
    p = problem
    evaluate = getattr(p, "curved_calculate", p.calculate)
    calculation = evaluate(point)
    mean = calculation["coefficient"] - calculation["latent_coefficient"]
    design = calculation["features"]
    raw = p.values - p.q * calculation["intercept"] - design @ mean
    prior, weights = calculation["coefficient_prior_precision"], calculation["noise_precision"]
    groups = p.noise_groups[p.keep]
    family_groups = [p.labels.index(row["candidate_index"]) for row in p.rows]
    n = p.hardware.shape[1] + p.smooth.shape[1]
    modes = [[n + 2 + j] for j in range(len(p.labels))]
    for k, family in enumerate(p.supported_local):
        start = n + 2 + len(p.labels) + 3 * k
        modes[family].extend(range(start, start + 3))

    def prediction(x):
        model = JointMarginal.calculate(p, x, geometry_only=True)
        return p.q * model["intercept"] + model["features"] @ calculation["coefficient"]

    # Differential model only. This common representational change enters both
    # dense and sparse comparators, without changing the selected ALGO08 fit.
    step_km = 0.001
    directions = np.eye(2) * step_km
    position_columns = np.column_stack([(prediction(point + shift) - prediction(point - shift))
                                       / (2 * step_km) for shift in directions])
    raw, sigma = raw[p.keep], p.point_noise[p.keep]
    design = np.column_stack((position_columns, design))[p.keep]
    prior = np.r_[[12 / p.scan.search_region.width_km**2] * 2, prior]
    statistics = algo08_family_schur.TrackStatistics(
        design, raw, sigma, groups, family_groups, n + 2, modes
    )
    weights = powers * weights

    def calculate(reduced, current, omit=None):
        keep = np.ones(len(groups), dtype=bool)
        if omit is not None:
            keep = np.asarray(family_groups)[groups] != omit
        coefficient, diagonal, logdet, covariance = reduced.solve(omit=omit)
        energy, variance = algo08_family_schur.track_moments(statistics, coefficient, covariance)
        actual = (coefficient, diagonal, logdet, energy, variance)
        expected = dense_moments(design[keep], raw[keep], sigma[keep], groups[keep], current, prior)
        return errors(actual, expected), actual, expected

    reduced = statistics.reduce(weights, prior)
    nominal, actual, expected = calculate(reduced, weights)
    counts = np.bincount(groups, minlength=len(powers))
    alpha = 2 + powers * counts / 2
    updated = alpha / (2 + powers * (actual[-2] + actual[-1]) / 2)
    dense_updated = alpha / (2 + powers * (expected[-2] + expected[-1]) / 2)
    post_update, _, _ = calculate(statistics.reduce(powers * updated, prior), powers * updated)
    family_counts = np.bincount(np.asarray(family_groups)[groups], minlength=len(modes))
    omit = int(np.argmax(family_counts))
    omitted, _, _ = calculate(reduced, weights, omit)
    return dict(rows=len(raw), tracks=len(powers), families=len(modes), full_width=len(prior),
                shared_width=n + 2, largest_family_width=max(map(len, modes)),
                excluded_rows=int(family_counts[omit]), nominal=nominal, omitted=omitted,
                reweighted=post_update, next_gamma_precision_error=float(np.max(
                    np.abs(updated - dense_updated))))


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

    def evidence(_prepared, signed, fit):
        if fit is None:
            fit = dict(status="complete", accepted=False, baseline_node=signed["node"],
                       baseline_entries=signed["entries"], baseline_means=signed["means"],
                       original_mask=signed["keep"], powers=signed["powers"], model=signed["model"],
                       policy_arms=signed["arms"])
        ctx = recovery_context(signed["scan"], fit)
        output = {}
        for arm, (problem, endpoint) in ctx["problems"].items():
            half = problem.scan.search_region.half_width_km
            points = (endpoint, np.zeros(2), np.copysign(half, endpoint))
            output[arm] = {key: differential(problem, point, ctx["powers"])
                           for key, point in zip(("endpoint", "center", "corner"), points, strict=True)}
        return output

    with (
        patch.object(algo08_position, "selected_packet", evidence),
        patch.object(algo08_position, "prepare_native_scan", partial(
            algo08_causal_reuse.prepare, algo08_position.prepare_native_scan, statistics={}
        )),
    ):
        result, blocks, policy = algo08_position.solve(json.loads(raw), TleArchiveReader(args.archive),
                                                       args.assets, region)
    print(json.dumps(dict(decision=result, orbit_policy=policy, blocks=blocks,
                          native_sha256=args.native_sha256), allow_nan=False))


if __name__ == "__main__":
    main()
