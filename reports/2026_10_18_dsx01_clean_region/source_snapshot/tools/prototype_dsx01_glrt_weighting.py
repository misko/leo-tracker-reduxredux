"""Score-dependent CFO variance learned only from radio polynomial residuals."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from build_dsx01_causal_forecast import OUTPUT
from compare_dsx01_retention_localization import METHODS, Scan
from iterate_dsx01_position_nominations import fit_once
from prototype_dsx01_receiver_geometry import SOURCE, geometry_problem

SCORES = OUTPUT / "glrt_scores.json"


def fit_variance(margins, squares):
    """Gaussian variance floor + strength/margin, bounded in physical Hz²."""
    m, y = np.asarray(margins), np.asarray(squares)
    if m.ndim != 1 or y.shape != m.shape or not len(m) or np.any(m <= 0) or np.any(y < 0):
        raise ValueError("positive margins and nonnegative squared residuals required")
    if not np.isfinite(m).all() or not np.isfinite(y).all():
        raise ValueError("finite noise observations required")

    def profile(ratio):
        shape = 1 + ratio / m
        maximum = min(360000, 360000 / ratio) if ratio else 360000
        floor = np.clip(np.mean(y / shape), 1600, maximum)
        variance = floor * shape
        return float(np.mean(np.log(variance) + y / variance)), np.array([floor, floor * ratio])

    # Profile the overall scale analytically, then bracket the shape with a
    # fixed logarithmic grid. Pure NumPy keeps the research dependency lean.
    grid = np.r_[0, np.geomspace(1e-6, 225, 257)]
    values = np.array([profile(r)[0] for r in grid])
    best = int(np.argmin(values))
    left, right = grid[max(0, best - 1)], grid[min(len(grid) - 1, best + 1)]
    phi = (np.sqrt(5) - 1) / 2
    for _ in range(64):
        a, b = right - phi * (right - left), left + phi * (right - left)
        if profile(a)[0] < profile(b)[0]:
            right = b
        else:
            left = a
    candidates = [profile(grid[best]), profile((left + right) / 2)]
    return min(candidates, key=lambda pair: pair[0])[1]


def variance_samples(scan, scores):
    margins, squares = [], []
    for i in scan.curved:
        t = scan.tracks[i]
        lookup = {oid: k for k, oid in enumerate(t["observation_ids"])}
        for piece in t["pieces"]:
            indexes = [lookup[oid] for oid in piece["observation_ids"] if oid in lookup]
            degree = piece["degree"]
            if len(indexes) < 2 * (degree + 1) + 3:
                continue
            times, y = t["times"][indexes], t["values"][indexes]
            z = (times - times.mean()) / max(1, np.ptp(times))
            design = np.vander(z, degree + 1, increasing=True)
            q, _ = np.linalg.qr(design)
            leverage = np.sum(q**2, axis=1)
            residual = y - q @ (q.T @ y)
            squares.extend(residual**2 / (1 - leverage))
            margins.extend(scores[t["observation_ids"][k]]["fractional_margin"] for k in indexes)
    return np.array(margins), np.array(squares)


def weighted_scan(case):
    scan = Scan(case)
    source = json.loads(SCORES.read_text())[case]
    scores = source["scores"]
    for t in scan.tracks:
        for oid, y in zip(t["observation_ids"], t["values"], strict=True):
            raw = scores[oid]["measured_cfo_hz"]
            # Graph tracks may have an integer alias lift.
            period = 1 / 4.4e-6
            if abs((y - raw) - round((y - raw) / period) * period) > 1e-6:
                raise ValueError("score and graph CFO disagree")
    m, y = variance_samples(scan, scores)
    floor, strength = fit_variance(m, y)
    white, correlated, scales = [], [], []
    for t in scan.tracks:
        margin = np.array([scores[oid]["fractional_margin"] for oid in t["observation_ids"]])
        sigma = np.clip(np.sqrt(floor + strength / margin), 40, 600)
        scales.extend(sigma)
        white.append((np.diag(1 / sigma), float(2 * np.log(sigma / 150).sum())))
        covariance = np.diag(sigma**2) + 150**2 * np.exp(
            -abs(t["times"][:, None] - t["times"]) / 10
        )
        lower = np.linalg.cholesky(covariance)
        correlated.append(
            (
                np.linalg.solve(lower, np.eye(len(sigma))),
                float(2 * np.log(np.diag(lower) / 150).sum()),
            )
        )
    scan.white, scan.ou = white, correlated
    metadata = dict(
        only_original_curved_radio_polynomial_residuals_estimate_noise=True,
        no_GPS_TLE_or_satellite_residuals_used_in_noise_fit=True,
        covariance_frozen_before_position_fit=True,
        source_sha256=source["source_sha256"],
        noise_samples=len(m),
        floor_hz=float(np.sqrt(floor)),
        strength_hz2=float(strength),
        sigma_quantiles_hz=np.quantile(scales, [0, 0.1, 0.5, 0.9, 1]),
        original_glrt_margin_quantiles=np.quantile(m, [0, 0.1, 0.5, 0.9, 1]),
    )
    return scan, metadata


def run(case, method):
    directory = OUTPUT / "score_weighting" / case / method
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "endpoints.json"
    if path.exists():
        return json.loads(path.read_text())
    scan, metadata = weighted_scan(case)
    seed_path = SOURCE / case / f"{method}_center.json"
    seed = json.loads(seed_path.read_text())
    nominal = Scan(case)
    locked = geometry_problem(
        nominal, seed, method, False, (0, 0), mean_sigma=10, height_sigma=0
    ).alias

    def factory(*args):
        p = geometry_problem(*args, mean_sigma=10, height_sigma=0)
        p.problem.alias = list(locked)
        return p

    fits = fit_once(scan, seed, method, (0, 0), problem_class=factory)
    write(path, fits)
    write(directory / "noise_model.json", metadata)
    write(
        directory / "protocol.json",
        dict(
            common_raw_curved_points_nominations_aliases_priors_and_grid_budget=True,
            c0_and_fitted_c_use_same_frozen_variances=True,
            source_sha256=hashlib.sha256(seed_path.read_bytes()).hexdigest(),
            scores_sha256=hashlib.sha256(SCORES.read_bytes()).hexdigest(),
            code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        ),
    )
    print(case, method, {a: f["east_north_km"] for a, f in fits.items()}, flush=True)
    return fits


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", default="DSX01-S05")
    p.add_argument("--method", choices=METHODS, required=True)
    a = p.parse_args()
    run(a.case, a.method)
