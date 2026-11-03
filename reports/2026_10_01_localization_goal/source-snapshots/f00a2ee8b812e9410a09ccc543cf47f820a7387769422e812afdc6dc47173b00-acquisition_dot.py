"""Frozen acquisition model with shared receiver geometry and dot products."""
# ruff: noqa: E402, I001
import time
from dataclasses import asdict
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'2026_10_01_localization_approaches'))
from adapter import prepare
from acquire import (
    AcquisitionResult, FixedHeightTrackLikelihood, Seed, coarse_to_fine, fibonacci_disk,
    LIGHT_KM_S, WGS84_A_KM, WGS84_F, enu_state_ecef_km,
)
from leo.analysis.localization_geometry import stationary_range_rate_grid
from leo.analysis.localization_search import MemoizedPointScorer


class DotTrackLikelihood(FixedHeightTrackLikelihood):
    def __init__(self, *args, geometry_cache=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.geometry_cache = {} if geometry_cache is None else geometry_cache

    def __call__(self, points_en_km, nuisance_hypotheses):
        points = np.asarray(points_en_km, dtype=float)
        if np.asarray(nuisance_hypotheses).shape != (1, 0):
            raise ValueError('proposal fixes all nuisance coordinates')
        key = (points.shape, points.tobytes())
        if key not in self.geometry_cache:
            receivers = np.stack([
                enu_state_ecef_km(east, north, self.height_surface(float(east), float(north)),
                                 self.config.prior_center_lat_deg,
                                 self.config.prior_center_lon_deg)
                for east, north in points
            ])
            semiminor = WGS84_A_KM*(1-WGS84_F)
            up = receivers/np.array([WGS84_A_KM**2, WGS84_A_KM**2, semiminor**2])
            up /= np.linalg.norm(up, axis=1, keepdims=True)
            self.geometry_cache[key] = receivers, up
        receivers, up = self.geometry_cache[key]
        positions, velocities = self._orbit_states(np.zeros(1))
        rate, sine_elevation = stationary_range_rate_grid(
            positions[0], velocities[0], receivers, up,
        )
        doppler = self.config.doppler_sign*self.config.reference_frequency_hz/LIGHT_KM_S*rate
        means = np.einsum('pst,mt->psm', doppler, self.contrasts)
        residual = self.observation[None, None, :]-means
        quadratic = np.einsum('...i,ij,...j->...', residual, self.precision, residual)
        logs = self._residual_log_density(quadratic, self.covariance, self.log_normalizer)
        elevation = np.degrees(np.arcsin(sine_elevation))
        visible = np.all(elevation >= -self.config.horizon_margin_deg, axis=2)
        count = len(self.bank.norad_ids)
        logs = np.where(visible, logs+np.log(self.config.signal_prior/count), -np.inf)
        background_prior = (self.config.background_prior
                            + self.config.signal_prior*(count-visible.sum(axis=1))/count)
        background = np.log(background_prior)+self.background_log_likelihood
        return np.concatenate((logs, background[:, None]), axis=1)[:, None, :]


def propose_dot(scan, height, *, deadline_s=50.):
    start = time.monotonic()
    # This cache belongs to this scan, center, and fixed height surface only.
    geometry_cache = {}
    ports = [DotTrackLikelihood(track, scan.bank, scan.config, height, 4.,
                                geometry_cache=geometry_cache) for _, track in scan.tracks]

    def score(points):
        total = np.zeros(len(points))
        for begin in range(0, len(points), 32):
            if time.monotonic()-start >= deadline_s:
                raise TimeoutError('dot acquisition budget exhausted')
            chunk = points[begin:begin+32]
            for port in ports:
                values = port(chunk, np.empty((1, 0)))[:, 0, :]
                maximum = values.max(axis=1)
                total[begin:begin+len(chunk)] += maximum+np.log(
                    np.exp(values-maximum[:, None]).sum(axis=1))
        return total

    cached = MemoizedPointScorer(score)
    seeds, scores, requested, spacing = coarse_to_fine(cached)
    proposal = AcquisitionResult(
        tuple(Seed(float(p[0]), float(p[1]), float(s)) for p, s in zip(seeds, scores, strict=True)),
        requested, len(ports), spacing, time.monotonic()-start,
    )
    return proposal, dict(requested_points=requested, unique_points=cached.evaluated_points)


if __name__ == '__main__':
    import argparse
    import hashlib
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument('unit')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise FileExistsError(output)
    started = time.monotonic()
    scan, height, _ = prepare(args.unit)
    points = fibonacci_disk(32, 250.)
    differences, visibility_matches = [], []
    for _, track in scan.tracks:
        old = FixedHeightTrackLikelihood(track, scan.bank, scan.config, height, 4.)
        new = DotTrackLikelihood(track, scan.bank, scan.config, height, 4.)
        a, b = old(points, np.empty((1, 0))), new(points, np.empty((1, 0)))
        finite = np.isfinite(a) & np.isfinite(b)
        differences.append(float(np.max(np.abs(a[finite]-b[finite]))))
        visibility_matches.append(bool(np.array_equal(np.isfinite(a), np.isfinite(b))))
    assert all(visibility_matches) and max(differences) < 1e-6
    proposal, counts = propose_dot(scan, height)
    prior = HERE.parent/'2026_10_01_localization_approaches/benchmark-v1/primary/A1'
    baseline_path = next(prior.glob('*/'+args.unit+'.json'))
    expected = json.loads(baseline_path.with_suffix('.seal.json').read_text())['prediction_sha256']
    assert 'sha256:'+hashlib.sha256(baseline_path.read_bytes()).hexdigest() == expected
    baseline = json.loads(baseline_path.read_text())['proposal']
    actual = asdict(proposal)
    result = dict(unit=args.unit, qualification='acquisition equivalence diagnostic; no GPS',
                  max_branch_score_difference=max(differences), all_visibility_matches=True,
                  proposal=actual, counts=counts, inputs=scan.inputs,
                  baseline_receipt_sha256=expected,
                  seeds_identical=all(a['east_km'] == b['east_km'] and
                                      a['north_km'] == b['north_km']
                                      for a, b in zip(actual['seeds'], baseline['seeds'],
                                                      strict=True)),
                  max_seed_score_difference=max(abs(a['cumulative_log_score']-
                                                    b['cumulative_log_score'])
                                                for a, b in zip(actual['seeds'], baseline['seeds'],
                                                                strict=True)),
                  total_seconds=time.monotonic()-started, source_sha256={})
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename:
            source = Path(filename).resolve()
            if source.suffix == '.py' and source.is_relative_to(HERE.parents[1]):
                result['source_sha256'][str(source)] = hashlib.sha256(
                    source.read_bytes()).hexdigest()
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in result.items()
                      if k not in ('inputs', 'source_sha256', 'proposal')}))
    print('Acquisition seconds:', proposal.wall_seconds)
