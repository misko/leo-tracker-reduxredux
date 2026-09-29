"""Correlated contrast signal and trend with optional shared receiver cones."""

import math
import sys
from pathlib import Path

import numpy as np
from density import ContrastDensity

REPORTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPORTS / "2026_09_29_unassociated_trend"))
sys.path.insert(0, str(REPORTS / "2026_09_29_rx_cone_position"))
sys.path.insert(0, str(REPORTS / "2026_09_29_frequency_contrast"))
sys.path.insert(0, str(REPORTS.parent / "tools"))
from cones import axes, enu_los  # noqa: E402
from ds7_baseline_adapter import site  # noqa: E402
from trend_mixture import TrendMixturePosition  # noqa: E402


def routed_log_prior(log_geometry, visible, background_probability):
    """Return K satellite log masses and one background log mass, summing to one."""
    log_geometry = np.asarray(log_geometry, dtype=float)
    visible = np.asarray(visible, dtype=bool)
    if log_geometry.shape != visible.shape or log_geometry.ndim != 1:
        raise ValueError("Require matching candidate vectors")
    if np.isnan(log_geometry).any() or (log_geometry > 0).any():
        raise ValueError("Geometry compatibility must be in [0,1]")
    q = float(background_probability)
    if not np.isfinite(q) or not 0 <= q <= 1:
        raise ValueError("Require prior probability in [0,1]")
    count = int(visible.sum())
    if not count:
        raise ValueError("No visible retained candidate: outside conditional-bank domain")
    signal = math.log1p(-q) if q < 1 else -np.inf
    satellite = np.where(visible, signal - math.log(count) + log_geometry, -np.inf)
    # -expm1 retains small rejected mass when compatibility is almost one.
    rejected = float(np.mean(-np.expm1(log_geometry[visible])))
    background = q + (1 - q) * rejected
    return np.r_[satellite, math.log(background) if background > 0 else -np.inf]


class CorrelatedTrendPosition(TrendMixturePosition):
    def __init__(
        self,
        documents,
        config,
        model_factory,
        half_angle_deg=None,
        control="nominal",
        edge_deg=2.0,
        background_probability=0.2,
        decay_s=10.0,
    ):
        super().__init__(documents, config, model_factory, background_probability)
        if half_angle_deg is not None and not 0 < half_angle_deg < 180:
            raise ValueError("Require half-angle strictly between 0 and 180 degrees")
        if not np.isfinite(edge_deg) or edge_deg <= 0:
            raise ValueError("Require positive finite edge width")
        self.half_angle_deg = half_angle_deg
        self.boresights = axes(control)
        self.edge_deg = float(edge_deg)
        self.grid = config["timing_grid_s"]
        self.densities = {}
        for di, doc in enumerate(documents):
            for ti, track in enumerate(doc["tracks"]):
                mask = track["mask"]
                times = np.asarray(track["times_s"])
                self.densities[di, ti] = (
                    ContrastDensity(times[mask], decay_s),
                    ContrastDensity(times, decay_s),
                )
                self.background[di, ti] = (
                    float(
                        ContrastDensity(times[mask], decay_s, slope_scale=2000)(
                            track["y"][None, mask]
                        )[0][0]
                    ),
                    float(
                        ContrastDensity(times, decay_s, slope_scale=2000)(track["y"][None, :])[0][0]
                    ),
                )

    def angles(self, track, local):
        lat, lon = self.coordinates(local)
        receiver, _ = site(lat, lon)
        rx = int(track["receiver_id"])
        if rx not in (0, 1):
            raise ValueError("Unknown receiver")
        los = enu_los(track["candidate_position_km"], self.grid, local[2], receiver, lat, lon)
        return np.degrees(np.arccos(np.clip(los @ self.boresights[rx], -1, 1)))

    def log_geometry(self, track, local):
        if self.half_angle_deg is None:
            return np.zeros(len(track["candidate_position_km"]))
        worst = self.angles(track, local)[:, track["mask"]].max(axis=1)
        return -np.logaddexp(0, (worst - self.half_angle_deg) / self.edge_deg)

    def evaluate(self, x, gradient=True, held=False):
        x = np.asarray(x, dtype=float)
        if x.shape != (2 + len(self.documents),) or not np.isfinite(x).all():
            raise ValueError("Require shared E/N and one finite timing per recording")
        score, derivative, rows = 0.0, np.zeros_like(x), []
        for di, (doc, model) in enumerate(zip(self.documents, self.models, strict=True)):
            local = np.array([x[0], x[1], x[di + 2]])
            for ti, track in enumerate(doc["tracks"]):
                mask = track["mask"]
                prediction, visible = model.prediction(track, local)
                residual = track["y"][None, :] - prediction
                train_density, full_density = self.densities[di, ti]
                train, influence = train_density(residual[:, mask])
                geometry = self.log_geometry(track, local)
                prior = routed_log_prior(geometry, visible, self.background_probability)
                bg_train, bg_joint = self.background[di, ti]
                components = np.r_[train, bg_train] + prior
                normal = np.logaddexp.reduce(components)
                weights = np.exp(components - normal)
                score += float(normal)
                if gradient:
                    active = weights > 0
                    for axis in range(3):
                        step = 1e-4 if axis < 2 else 1e-5
                        plus, minus = local.copy(), local.copy()
                        plus[axis] += step
                        minus[axis] -= step
                        if axis == 2:
                            plus[axis] = min(5, plus[axis])
                            minus[axis] = max(-5, minus[axis])
                        pp, vp = model.prediction(track, plus)
                        pm, vm = model.prediction(track, minus)
                        assert np.array_equal(visible, vp) and np.array_equal(visible, vm)
                        span = plus[axis] - minus[axis]
                        dp = (pp[:, mask] - pm[:, mask]) / span
                        prior_plus = routed_log_prior(
                            self.log_geometry(track, plus), visible, self.background_probability
                        )
                        prior_minus = routed_log_prior(
                            self.log_geometry(track, minus), visible, self.background_probability
                        )
                        assert np.isfinite(prior_plus[active]).all()
                        assert np.isfinite(prior_minus[active]).all()
                        dg = (prior_plus[active] - prior_minus[active]) / span
                        index = axis if axis < 2 else di + 2
                        derivative[index] += float(weights[:-1] @ np.sum(influence * dp, axis=1))
                        derivative[index] += float(weights[active] @ dg)
                if held:
                    full, _ = full_density(residual)
                    joint = np.logaddexp.reduce(np.r_[full, bg_joint] + prior)
                    signal_weight = float(weights[:-1].sum())
                    rows.append(
                        {
                            "session_id": doc["session_id"],
                            "track_id": track["track_id"],
                            "training_log_score": float(normal),
                            "held_log_score": float(joint - normal),
                            "candidate_responsibilities": weights[:-1].tolist(),
                            "signal_responsibility": signal_weight,
                            "background_responsibility": float(weights[-1]),
                            "background_prior_mass": float(np.exp(prior[-1])),
                            "visible_candidates": int(visible.sum()),
                            "held_observations": int((~mask).sum()),
                        }
                    )
        return {"score": score, "gradient": derivative, "rows": rows}
