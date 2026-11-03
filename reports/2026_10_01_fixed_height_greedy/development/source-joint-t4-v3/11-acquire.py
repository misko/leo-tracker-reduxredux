"""Bounded fixed-height global proposals for later full-nuisance fitting."""
from __future__ import annotations

import sys
import time
from math import lgamma, log, pi
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPORT = HERE.parent / "2026_09_30_broad_prior_acquisition"
BASE = HERE.parent / "2026_09_30_gaussian_sum_64_scan"
sys.path.append(str(ROOT / "src"))
sys.path.append(str(BASE))
sys.path.append(str(REPORT))
sys.path.append(str(REPORT / "spatial"))
from physics import (  # noqa: E402
    LIGHT_KM_S, WGS84_A_KM, WGS84_F, _spread_indices, enu_state_ecef_km,
)
from rf import VectorizedTrackLikelihood  # noqa: E402
from leo.analysis.robust_likelihood import student_t_logpdf  # noqa: E402


@dataclass(frozen=True)
class Seed:
    east_km: float
    north_km: float
    cumulative_log_score: float


@dataclass(frozen=True)
class AcquisitionResult:
    seeds: tuple[Seed, ...]
    evaluated_point_count: int
    track_count: int
    final_spacing_km: float
    wall_seconds: float
    qualification: str = (
        "proposal only: fixed height, clock, receiver drifts, and satellite epochs; "
        "full nuisance fit and all-scan evidence still required"
    )


class FixedHeightTrackLikelihood(VectorizedTrackLikelihood):
    """Frozen vectorized likelihood with receiver height injected explicitly."""

    def __init__(self, track, bank, config, height_surface, degrees_of_freedom=None):
        super().__init__(track, bank, config)
        if degrees_of_freedom is not None and (
            not np.isfinite(degrees_of_freedom) or degrees_of_freedom <= 0
        ):
            raise ValueError("degrees_of_freedom must be finite and positive")
        self.degrees_of_freedom = degrees_of_freedom
        self.height_surface = (
            height_surface if callable(height_surface)
            else lambda _east, _north: float(height_surface)
        )
        selected=_spread_indices(track.times_s,config.max_points)
        self.receiver_indices=track.receiver_indices[selected]
        self.centered_times=self.times-self.times.mean()
        self.drift_scale=config.reference_frequency_hz/track.rf_hz
        background_design = self.contrasts @ np.column_stack(
            (self.centered_times, 0.5 * self.centered_times**2)
        )
        self.background_covariance = (
            self.covariance
            + background_design
            @ np.diag(
                [
                    config.background_slope_hz_s**2,
                    config.background_curvature_hz_s2**2,
                ]
            )
            @ background_design.T
        )
        self.background_covariance = (
            self.background_covariance + self.background_covariance.T
        ) * 0.5
        if self.degrees_of_freedom is not None:
            self.background_log_likelihood = student_t_logpdf(
                self.observation,
                self.background_covariance,
                self.degrees_of_freedom,
            )

    def _residual_log_density(self, quadratic, covariance, gaussian_normalizer):
        if self.degrees_of_freedom is None:
            return gaussian_normalizer - 0.5 * quadratic
        dimension = covariance.shape[0]
        _, logdet = np.linalg.slogdet(covariance)
        nu = self.degrees_of_freedom
        normalizer = (
            lgamma((nu + dimension) / 2)
            - lgamma(nu / 2)
            - 0.5 * (dimension * log(nu * pi) + logdet)
        )
        return normalizer - 0.5 * (nu + dimension) * np.log1p(quadratic / nu)

    def _orbit_states_per_satellite(self, offsets):
        query=self.times[None,:]+np.asarray(offsets)[:,None]
        spacing=self.bank.times_s[1]-self.bank.times_s[0]
        if np.any(query<self.bank.times_s[1]) or np.any(query>self.bank.times_s[-2]):
            raise ValueError("prediction time lacks four-knot orbit support")
        interval=np.floor((query-self.bank.times_s[0])/spacing).astype(int)
        interval=np.clip(interval,0,self.bank.times_s.size-2)
        satellites=np.arange(len(self.bank.norad_ids))[:,None]
        u=(query-self.bank.times_s[interval])/spacing
        p0=self.bank.positions_ecef_km[satellites,interval]
        p1=self.bank.positions_ecef_km[satellites,interval+1]
        v0=self.bank.velocities_ecef_km_s[satellites,interval]
        v1=self.bank.velocities_ecef_km_s[satellites,interval+1]
        position=((2*u**3-3*u**2+1)[...,None]*p0+(u**3-2*u**2+u)[...,None]*spacing*v0
                  +(-2*u**3+3*u**2)[...,None]*p1+(u**3-u**2)[...,None]*spacing*v1)
        left=np.clip(interval-1,0,self.bank.times_s.size-4); velocity=np.zeros_like(position)
        for j in range(4):
            knot_j=left+j; basis=np.ones_like(query)
            for k in range(4):
                if k!=j:
                    basis*=(query-self.bank.times_s[left+k])/(self.bank.times_s[knot_j]-self.bank.times_s[left+k])
            velocity+=basis[...,None]*self.bank.velocities_ecef_km_s[satellites,knot_j]
        return position,velocity

    def branch_loglik_at_state(self, reduced_state):
        """Return satellite then background logs for [E,N,tau,drift0,drift1,epochs...]."""
        state=np.asarray(reduced_state,dtype=float)
        count=len(self.bank.norad_ids)
        if state.shape!=(5+count,) or not np.all(np.isfinite(state)):
            raise ValueError("reduced full state has wrong shape or nonfinite values")
        receiver=enu_state_ecef_km(state[0],state[1],self.height_surface(state[0],state[1]),
                                   self.config.prior_center_lat_deg,self.config.prior_center_lon_deg)
        position,velocity=self._orbit_states_per_satellite(state[2]+state[5:])
        line=position-receiver; unit=line/np.linalg.norm(line,axis=-1,keepdims=True)
        doppler=(self.config.doppler_sign*self.config.reference_frequency_hz/LIGHT_KM_S
                 *np.sum(velocity*unit,axis=-1))
        drift=state[3+self.receiver_indices]*self.drift_scale*self.centered_times
        means=(doppler+drift[None,:])@self.contrasts.T
        residual=self.observation[None,:]-means
        quadratic=np.einsum("...i,ij,...j->...",residual,self.precision,residual)
        logs=self._residual_log_density(quadratic,self.covariance,self.log_normalizer)
        semiminor=WGS84_A_KM*(1-WGS84_F); up=receiver/np.array([WGS84_A_KM**2,WGS84_A_KM**2,semiminor**2]); up/=np.linalg.norm(up)
        visible=np.all(np.degrees(np.arcsin(np.clip(unit@up,-1,1)))>=-self.config.horizon_margin_deg,axis=1)
        logs=np.where(visible,logs+np.log(self.config.signal_prior/count),-np.inf)
        background_prior=self.config.background_prior+self.config.signal_prior*(count-visible.sum())/count
        return np.concatenate((logs,[np.log(background_prior)+self.background_log_likelihood]))

    def __call__(self, points_en_km, nuisance_hypotheses):
        points = np.asarray(points_en_km, dtype=float)
        nuisance = np.asarray(nuisance_hypotheses, dtype=float)
        if nuisance.shape != (1, 0):
            raise ValueError("proposal port fixes all nuisance coordinates")
        positions, velocities = self._orbit_states(np.zeros(1))
        receivers = np.stack([
            enu_state_ecef_km(east, north, self.height_surface(float(east),float(north)),
                              self.config.prior_center_lat_deg,
                              self.config.prior_center_lon_deg)
            for east, north in points
        ])
        line = positions[None] - receivers[:, None, None, None, :]
        unit = line / np.linalg.norm(line, axis=-1, keepdims=True)
        doppler = (self.config.doppler_sign*self.config.reference_frequency_hz/LIGHT_KM_S
                   * np.sum(velocities[None]*unit,axis=-1))
        means = np.einsum("phst,mt->phsm",doppler,self.contrasts)
        residual = self.observation[None,None,None,:]-means
        quadratic = np.einsum("...i,ij,...j->...",residual,self.precision,residual)
        signal_log = self._residual_log_density(
            quadratic, self.covariance, self.log_normalizer
        )
        semiminor=WGS84_A_KM*(1-WGS84_F)
        up=receivers/np.array([WGS84_A_KM**2,WGS84_A_KM**2,semiminor**2])
        up/=np.linalg.norm(up,axis=1,keepdims=True)
        elevation=np.degrees(np.arcsin(np.clip(np.einsum("phstj,pj->phst",unit,up),-1,1)))
        visible=np.all(elevation>=-self.config.horizon_margin_deg,axis=3)
        count=len(self.bank.norad_ids)
        signal_log=np.where(visible,signal_log+np.log(self.config.signal_prior/count),-np.inf)
        background_prior=self.config.background_prior+self.config.signal_prior*(count-visible.sum(axis=2))/count
        background=np.log(background_prior)+self.background_log_likelihood
        return np.concatenate((signal_log,background[:,:,None]),axis=2)


def fibonacci_disk(count: int, radius_km: float) -> np.ndarray:
    index=np.arange(count,dtype=float)
    radius=radius_km*np.sqrt((index+.5)/count)
    angle=index*np.pi*(3-np.sqrt(5))
    return np.column_stack((radius*np.cos(angle),radius*np.sin(angle)))


def distinct_top(points, scores, count, separation_km):
    selected=[]
    for index in np.argsort(scores)[::-1]:
        if all(np.linalg.norm(points[index]-points[other])>=separation_km for other in selected):
            selected.append(int(index))
            if len(selected)==count:
                break
    return np.asarray(selected,dtype=int)


def coarse_to_fine(score_points, *, radius_km=250., coarse_count=1024, basin_count=8,
                   spacings=(16.,8.,4.,2.,1.)):
    points=fibonacci_disk(coarse_count,radius_km)
    scores=score_points(points)
    evaluated=len(points)
    seed_indices=distinct_top(points,scores,basin_count,40.)
    seeds=points[seed_indices]
    anchors=np.array(seeds,copy=True)
    for spacing in spacings:
        offsets=np.array(
            [(east,north) for east in range(-2,3) for north in range(-2,3)],float
        )*spacing
        next_seeds=[]; next_scores=[]
        for seed,anchor in zip(seeds,anchors,strict=True):
            proposed=seed+offsets
            proposed=proposed[(np.linalg.norm(proposed,axis=1)<=radius_km)
                              &(np.linalg.norm(proposed-anchor,axis=1)<=10.)]
            local_scores=score_points(proposed); evaluated+=len(proposed)
            best=int(np.argmax(local_scores)); next_seeds.append(proposed[best]); next_scores.append(local_scores[best])
        seeds=np.asarray(next_seeds); scores=np.asarray(next_scores)
    order=np.argsort(scores)[::-1]
    return seeds[order],scores[order],evaluated,float(spacings[-1])


def propose(
    scan,
    height_surface,
    *,
    max_tracks=8,
    deadline_s=85.,
    degrees_of_freedom=None,
) -> AcquisitionResult:
    started=time.monotonic()
    ports=[FixedHeightTrackLikelihood(
        track,scan.bank,scan.config,height_surface,degrees_of_freedom
    )
           for _,track in scan.tracks[:max_tracks]]
    def score(points):
        total=np.zeros(len(points))
        for start in range(0,len(points),32):
            if time.monotonic()-started>=deadline_s:
                raise TimeoutError("global acquisition proposal reached its wall budget")
            chunk=points[start:start+32]
            for port in ports:
                values=port(chunk,np.empty((1,0)))[:,0,:]
                maximum=np.max(values,axis=1)
                total[start:start+len(chunk)] += (
                    maximum + np.log(np.exp(values-maximum[:,None]).sum(axis=1))
                )
        return total
    seeds,scores,evaluated,spacing=coarse_to_fine(score)
    return AcquisitionResult(tuple(Seed(float(p[0]),float(p[1]),float(s))
                                   for p,s in zip(seeds,scores,strict=True)),
                             evaluated,len(ports),spacing,time.monotonic()-started)
