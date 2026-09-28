"""Doppler-only candidate-direction features for a cross-fitted M1 reception model.

Inputs are branch-local association hypotheses whose weights have already been
fit from Doppler training observations.  Reception values are deliberately not
accepted by the weighting API.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Mapping

import numpy as np

from leo.sky.frames import (
    ecef_to_enu_matrix,
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    look_angles,
    teme_to_ecef,
)
from leo.sky.propagation import ElementSetCatalogue, propagate_grid
from leo.sky.sampling import SamplingGrid


@dataclass(frozen=True, slots=True)
class DopplerHypothesis:
    track_id: str
    candidate_id: int
    utc_ns: int
    log_weight: float
    observation_id: str = ""


def unit_enu(azimuth_deg: np.ndarray, elevation_deg: np.ndarray) -> np.ndarray:
    """Convert clockwise-from-north azimuth/elevation to ENU unit vectors."""
    az=np.deg2rad(np.asarray(azimuth_deg,float)); el=np.deg2rad(np.asarray(elevation_deg,float))
    return np.stack((np.cos(el)*np.sin(az),np.cos(el)*np.cos(az),np.sin(el)),axis=-1)


def _softmax(log_weight: np.ndarray) -> np.ndarray:
    x=np.asarray(log_weight,float)
    if x.ndim!=1 or not len(x) or not np.all(np.isfinite(x)):raise ValueError("finite 1-D Doppler log weights required")
    q=np.exp(x-np.max(x));return q/q.sum()


def marginal_direction(azimuth_deg, elevation_deg, doppler_log_weight) -> dict:
    """Marginalize direction using Doppler-only association probability."""
    u=unit_enu(azimuth_deg,elevation_deg); w=_softmax(np.asarray(doppler_log_weight))
    if len(u)!=len(w):raise ValueError("direction and weight lengths differ")
    mean=np.sum(w[:,None]*u,axis=0); second=np.sum(w[:,None]*u*u,axis=0)
    return {"east":float(mean[0]),"north":float(mean[1]),"up":float(mean[2]),
            "east_variance":float(second[0]-mean[0]**2),"posterior_resultant":float(np.linalg.norm(mean)),
            "effective_hypotheses":float(1/np.sum(w*w))}


def candidate_look_angles(catalogue: ElementSetCatalogue, candidate_ids: Iterable[int], utc_ns: Iterable[int], *, latitude_deg: float, longitude_deg: float, altitude_m: float=0.0) -> dict[tuple[int,int],tuple[float,float]]:
    """Propagate candidate/time pairs and return branch-local azimuth/elevation."""
    pairs=list(dict.fromkeys(zip(map(int,candidate_ids),map(int,utc_ns),strict=True)))
    lookup={int(x):i for i,x in enumerate(catalogue.satellite_numbers)}
    output={}
    observer=geodetic_to_ecef_km(latitude_deg,longitude_deg,altitude_m); enu=ecef_to_enu_matrix(latitude_deg,longitude_deg)
    for cid,t in pairs:
        if cid not in lookup:raise ValueError(f"candidate {cid} absent from frozen catalogue")
        # Public propagator grids require three knots; only the centre is used.
        grid=SamplingGrid((t-1_000_000,t,t+1_000_000),1,.001)
        p=propagate_grid(catalogue,grid,[lookup[cid]])
        if not p.usable[0]:raise ValueError(f"candidate {cid} failed propagation")
        jd,fr=julian_day_from_utc_ns(np.asarray(grid.utc_ns,np.int64));gmst=greenwich_mean_sidereal_time_rad(jd,fr)
        pos,vel=teme_to_ecef(p.position_teme_km,p.velocity_teme_km_s,gmst[None,:])
        az,el,_,_=look_angles(pos,vel,observer,enu);output[(cid,t)]=(float(az[0,1]),float(el[0,1]))
    return output


def branch_direction_features(catalogue: ElementSetCatalogue, hypotheses: Iterable[DopplerHypothesis], *, branch_id: str, latitude_deg: float, longitude_deg: float, diagnostic_truth: bool=False) -> list[dict]:
    """Create one M1 feature per track without pooling candidates across branches."""
    if branch_id.lower() in {"truth","reference","gps"} and not diagnostic_truth:
        raise ValueError("truth-derived directions require diagnostic_truth=True")
    grouped=defaultdict(list)
    for h in hypotheses:
        if not isinstance(h,DopplerHypothesis):raise TypeError("only DopplerHypothesis inputs are accepted")
        grouped[h.track_id].append(h)
    flat=[h for rows in grouped.values() for h in rows]
    angles=candidate_look_angles(catalogue,[h.candidate_id for h in flat],[h.utc_ns for h in flat],latitude_deg=latitude_deg,longitude_deg=longitude_deg)
    answer=[]
    for track_id,rows in sorted(grouped.items()):
        az,el=zip(*(angles[(h.candidate_id,h.utc_ns)] for h in rows),strict=True)
        answer.append({"branch_id":branch_id,"track_id":track_id,"diagnostic_truth":diagnostic_truth,
                       **marginal_direction(az,el,[h.log_weight for h in rows]),"candidate_count":len(rows),
                       "observation_ids":sorted({h.observation_id for h in rows if h.observation_id})})
    return answer


def reception_design_rows(direction_rows: Iterable[Mapping], signed_rx_proxy: Mapping[str,float]) -> list[dict]:
    """Join held-out reception outcomes only after Doppler direction marginalization."""
    result=[]
    for row in direction_rows:
        tid=str(row["track_id"])
        if tid in signed_rx_proxy:result.append({**row,"signed_rx_proxy":float(signed_rx_proxy[tid])})
    return result
