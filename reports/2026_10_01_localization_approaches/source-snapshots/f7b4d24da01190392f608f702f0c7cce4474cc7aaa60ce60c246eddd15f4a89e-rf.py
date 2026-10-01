"""Vectorized whole-track RF likelihood port for the adaptive spatial map."""
from __future__ import annotations

from pathlib import Path
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[1] / "2026_09_30_gaussian_sum_64_scan"
sys.path.insert(0, str(BASE))
from physics import (  # noqa: E402
    LIGHT_KM_S,
    WGS84_A_KM,
    WGS84_F,
    _noise_covariance,
    _spread_indices,
    enu_state_ecef_km,
    gaussian_logpdf,
    helmert_contrasts,
)


class VectorizedTrackLikelihood:
    """Conditional likelihood with height, receiver drift, and epochs fixed at zero."""

    def __init__(self, track, bank, config):
        selected = _spread_indices(track.times_s, config.max_points)
        self.observation_ids = tuple(track.observation_ids[index] for index in selected)
        self.times = track.times_s[selected]
        frequencies = track.frequencies_hz[selected]
        receivers = track.receiver_indices[selected]
        self.contrasts = helmert_contrasts(receivers)
        self.observation = self.contrasts @ frequencies
        raw_covariance = _noise_covariance(self.times, config)
        covariance = self.contrasts @ raw_covariance @ self.contrasts.T
        self.covariance = (covariance + covariance.T) * 0.5
        self.precision = np.linalg.inv(self.covariance)
        sign, logdet = np.linalg.slogdet(self.covariance)
        if sign <= 0:
            raise ValueError("signal covariance is not positive definite")
        self.log_normalizer = -0.5 * (self.observation.size * np.log(2 * np.pi) + logdet)
        centered = self.times - self.times.mean()
        background_design = self.contrasts @ np.column_stack((centered, 0.5 * centered**2))
        background_covariance = (
            self.covariance
            + background_design
            @ np.diag([config.background_slope_hz_s**2, config.background_curvature_hz_s2**2])
            @ background_design.T
        )
        background_covariance = (background_covariance + background_covariance.T) * 0.5
        self.background_log_likelihood = gaussian_logpdf(self.observation, background_covariance)
        self.bank = bank
        self.config = config
        self.branch_ids = tuple(map(str, bank.norad_ids)) + ("background",)
        self._orbit_cache = {}
        self.deadline = None

    def _orbit_states(self, tau_values):
        key = np.asarray(tau_values, dtype=np.float64).tobytes()
        if key in self._orbit_cache:
            return self._orbit_cache[key]
        positions = np.empty((len(tau_values), len(self.bank.norad_ids), len(self.times), 3))
        velocities = np.empty_like(positions)
        knot_spacing = self.bank.times_s[1] - self.bank.times_s[0]
        for hypothesis, tau in enumerate(tau_values):
            query = self.times + tau
            if np.any(query < self.bank.times_s[1]) or np.any(query > self.bank.times_s[-2]):
                raise ValueError("prediction time lacks four-knot orbit support")
            interval = np.floor((query - self.bank.times_s[0]) / knot_spacing).astype(int)
            interval = np.clip(interval, 0, self.bank.times_s.size - 2)
            u = (query - self.bank.times_s[interval]) / knot_spacing
            p0 = self.bank.positions_ecef_km[:, interval]
            p1 = self.bank.positions_ecef_km[:, interval + 1]
            v0 = self.bank.velocities_ecef_km_s[:, interval]
            v1 = self.bank.velocities_ecef_km_s[:, interval + 1]
            positions[hypothesis] = (
                (2*u**3-3*u**2+1)[None,:,None]*p0
                + (u**3-2*u**2+u)[None,:,None]*knot_spacing*v0
                + (-2*u**3+3*u**2)[None,:,None]*p1
                + (u**3-u**2)[None,:,None]*knot_spacing*v1
            )
            left = np.clip(interval - 1, 0, self.bank.times_s.size - 4)
            velocity = np.zeros_like(positions[hypothesis])
            for j in range(4):
                knot_j = left + j
                basis = np.ones_like(query)
                for k in range(4):
                    if k != j:
                        basis *= (query-self.bank.times_s[left+k]) / (
                            self.bank.times_s[knot_j]-self.bank.times_s[left+k]
                        )
                velocity += basis[None,:,None]*self.bank.velocities_ecef_km_s[:,knot_j]
            velocities[hypothesis] = velocity
        self._orbit_cache[key] = positions, velocities
        return positions, velocities

    def __call__(self, points_en_km, nuisance_hypotheses):
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise TimeoutError("conditional spatial replay reached its internal wall budget")
        points = np.asarray(points_en_km, dtype=float)
        nuisance = np.asarray(nuisance_hypotheses, dtype=float)
        if nuisance.ndim != 2 or nuisance.shape[1] not in (0, 1):
            raise ValueError("conditional RF port accepts only an optional global tau column")
        tau = np.zeros(len(nuisance)) if nuisance.shape[1] == 0 else nuisance[:, 0]
        positions, velocities = self._orbit_states(tau)
        receivers = np.stack([
            enu_state_ecef_km(east, north, 0.0,
                              self.config.prior_center_lat_deg,
                              self.config.prior_center_lon_deg)
            for east, north in points
        ])
        line = positions[None, :, :, :, :] - receivers[:, None, None, None, :]
        unit = line / np.linalg.norm(line, axis=-1, keepdims=True)
        doppler = (
            self.config.doppler_sign * self.config.reference_frequency_hz / LIGHT_KM_S
            * np.sum(velocities[None, :, :, :, :] * unit, axis=-1)
        )
        means = np.einsum("phst,mt->phsm", doppler, self.contrasts)
        residual = self.observation[None, None, None, :] - means
        signal_log = self.log_normalizer - 0.5 * np.einsum(
            "...i,ij,...j->...", residual, self.precision, residual
        )
        semiminor = WGS84_A_KM * (1.0 - WGS84_F)
        up = receivers / np.array([WGS84_A_KM**2, WGS84_A_KM**2, semiminor**2])
        up /= np.linalg.norm(up, axis=1, keepdims=True)
        elevation = np.degrees(np.arcsin(np.clip(np.einsum("phstj,pj->phst", unit, up), -1, 1)))
        visible = np.all(elevation >= -self.config.horizon_margin_deg, axis=3)
        union_count = len(self.bank.norad_ids)
        signal_log += np.log(self.config.signal_prior / union_count)
        signal_log = np.where(visible, signal_log, -np.inf)
        visible_count = visible.sum(axis=2)
        background_prior = (
            self.config.background_prior
            + self.config.signal_prior * (union_count - visible_count) / union_count
        )
        background = np.log(background_prior) + self.background_log_likelihood
        return np.concatenate((signal_log, background[:, :, None]), axis=2)
