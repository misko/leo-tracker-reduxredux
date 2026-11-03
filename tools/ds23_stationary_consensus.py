"""Conditional causal RF consensus, requiring declared stationarity.

This estimator never receives reference coordinates or computes accuracy.
It is a separate multi-scan mode, not a replacement single-scan algorithm.
"""

import numpy as np


def spatial_median(points):
    x=np.asarray(points,float)
    if x.ndim!=2 or x.shape[1]!=2 or not len(x) or not np.isfinite(x).all():
        raise ValueError("nonempty finite east/north RF positions required")
    point=np.median(x,axis=0)
    for _ in range(10000):
        distance=np.linalg.norm(x-point,axis=1)
        close=distance<1e-10
        if close.any():
            # Modified Weiszfeld update handles an iterate at an observation.
            outside=x[~close];d=distance[~close]
            if not len(outside):return point
            gradient=np.sum((outside-point)/d[:,None],axis=0)
            norm=float(np.linalg.norm(gradient))
            if norm<=close.sum():return point
            candidate=np.sum(outside/d[:,None],axis=0)/np.sum(1/d)
            fraction=float(close.sum()/norm)
            next_point=fraction*point+(1-fraction)*candidate
        else:
            weight=1/distance;next_point=np.sum(x*weight[:,None],axis=0)/weight.sum()
        if np.linalg.norm(next_point-point)<1e-10:return next_point
        point=next_point
    raise ValueError("spatial median failed to converge")


def causal_estimates(records,method,*,declared_stationary):
    if not declared_stationary:raise ValueError("a declared stationary interval is required")
    if method not in ("mean","spatial_median"):raise ValueError("unknown fixed RF consensus rule")
    ordered=sorted(records,key=lambda r:(r["cutoff_utc_ns"],r["case"]))
    if len({r["case"] for r in ordered})!=len(ordered):raise ValueError("one recording receipt per case required")
    outputs=[]
    for current in ordered:
        points=[];owners=[]
        for other in ordered:
            if other["stationary_segment"]!=current["stationary_segment"] or other.get("position") is None:continue
            eligible=(other["case"]==current["case"] or
                other["cutoff_utc_ns"]<current["cutoff_utc_ns"] and other["last_observation_utc_ns"]<=current["cutoff_utc_ns"])
            if eligible:points.append(other["position"]);owners.append(other["case"])
        estimate=None
        if points:
            estimate=np.mean(points,axis=0) if method=="mean" else spatial_median(points)
        outputs.append(dict(case=current["case"],estimate=estimate,RF_update=current.get("position") is not None,
            used_cases=owners,history_points=len(points),stationary_segment=current["stationary_segment"],
            cutoff_utc_ns=current["cutoff_utc_ns"],method=method))
    return outputs
