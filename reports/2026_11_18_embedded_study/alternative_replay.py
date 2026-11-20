"""Two alternative position estimators on the predeclared anonymous DS26 panel."""

import argparse
import json
import time
from pathlib import Path

import numpy as np
from scipy.special import logsumexp

import cold_replay as cold


def soft_grid(d, bias, fitted):
    """A 9 by 9 map, with a clutter term and a mixture over anonymous satellite IDs.

    Integrate independent Gaussian track timing errors. Share receiver/side offsets
    and optionally c, estimated in three EM updates per cell. Treat long correlated
    observations as one shape and one frequency level per track.
    """
    mean, cov = d["mean"], d["cov"]
    n, k, _ = mean.shape
    columns = 5 if fitted else 4
    design = np.eye(4)[d["group"]]
    if fitted:
        design = np.column_stack([design, d["rf"]])
    initial = np.r_[bias, [0.] if fitted else []]
    sd = np.r_[[32000.]*4, [200000.] if fitted else []]
    precision = 1 / sd**2
    a = cold.SHAPE_SD**-2
    b = cold.LEVEL_SD**-2
    h = mean[...,3]
    curvature = a*cov[...,3,3] + b*h*h + cold.PHASE_SD_S**-2
    effective_b = b * (1 - b*h*h/curvature)
    determinant = np.log(curvature*cold.PHASE_SD_S**2)
    null = np.full(n, np.log(.15) - 6.)
    prior = np.log(.85 / k)
    best = None
    for x in np.linspace(-12.5, 12.5, 9):
        for y in np.linspace(-12.5, 12.5, 9):
            m = mean[...,0] - x*mean[...,1] - y*mean[...,2]
            cross = cov[...,0,3] - x*cov[...,1,3] - y*cov[...,2,3]
            v = (cov[...,0,0] + x*x*cov[...,1,1] + y*y*cov[...,2,2] - 2*x*cov[...,0,1]
                 - 2*y*cov[...,0,2] + 2*x*y*cov[...,1,2])
            beta = initial.copy()
            for step in range(4):
                dr = cold.wrap(m - (design@beta)[:,None])
                numerator = a*cross + b*dr*h
                chi = np.maximum(0., a*v + b*dr*dr - numerator*numerator/curvature)
                logw = prior - .5*(chi + determinant)
                evidence = np.logaddexp(null, logsumexp(logw,axis=1))
                if step == 3:
                    break
                w = np.exp(logw-evidence[:,None])
                information = design.T @ (np.sum(w*effective_b,axis=1)[:,None] * design)
                rhs = design.T @ np.sum(w*b*(dr-h*numerator/curvature),axis=1)
                beta += np.linalg.solve(information+np.diag(precision),rhs-precision*(beta-initial))
            score = evidence.sum() - .5*np.sum(((beta-initial)/sd)**2)
            if best is None or score > best[0]:
                best = (score,x,y,beta.copy(),logw.copy(),numerator/curvature)
    score,x,y,beta,logw,phase = best
    choice = np.argmax(logw,axis=1)
    rows = np.flatnonzero(np.max(logw,axis=1) > null)
    if len(rows)<4 or len(np.unique(d["ids"][rows,choice[rows]]))<3:
        return dict(status="insufficient")
    raw = d["raw"][rows,choice[rows]]
    residual = (raw[:,:,0] - x*raw[:,:,1] - y*raw[:,:,2] - phase[rows,choice[rows],None]*raw[:,:,3]
                - (design@beta)[rows,None])
    residual -= cold.PERIOD * np.rint(residual.mean(axis=1,keepdims=True) / cold.PERIOD)
    return dict(status="estimate",xy=[float(x),float(y)],tracks=len(rows),
                satellites=len(np.unique(d["ids"][rows,choice[rows]])),
                rms_hz=float(np.sqrt(np.mean(residual**2))),rms_kind="selected absolute",
                score=float(score),on_boundary=bool(max(abs(x),abs(y))>12.49))


def consensus(d, bias, vote):
    """Propose from six satellite families, score by agreement across whole families."""
    _, start, winners, loss = vote
    selected = np.flatnonzero(loss < 12.)
    families = d["ids"][selected,winners[selected]]
    distinct = np.unique(families)
    empty = {arm:dict(status="insufficient") for arm in ("c0","fitted_c")}
    if len(distinct) < 6:
        return empty
    candidates = [start]
    rng = np.random.default_rng(10413)
    for _ in range(16):
        draw = rng.choice(distinct,6,replace=False)
        subset = selected[np.isin(families,draw)]
        fit = cold.solve(d,subset,winners,bias,start,fitted_c=False)
        if fit["status"]=="estimate":
            candidates.append(fit["xy"])
    best = None
    for x,y in candidates:
        c = cold.phase_cost(d["mean"][selected,winners[selected]], d["cov"][selected,winners[selected]],
                            x,y,bias[d["group"][selected]])
        family_loss = np.array([np.median(c[families==j]) for j in distinct])
        score = np.sum(1/(1+family_loss/2.))
        if best is None or score>best[0]:
            best = (score,(x,y),family_loss)
    _, start, losses = best
    inliers = selected[np.isin(families,distinct[losses<5.])]
    return {arm:cold.solve(d,inliers,winners,bias,start,fitted_c=(arm=="fitted_c"))
            for arm in ("c0","fitted_c")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--smoke",action="store_true")
    parser.add_argument("--remaining",action="store_true")
    args = parser.parse_args()
    rows = []
    labels = ["DS26-0002"] if args.smoke else cold.panel()
    if args.remaining:
        members = cold.read(cold.WORK/"plans/science.json")["cohorts"]["DS26"]["members"]
        initial = set(labels)
        labels = sorted(r["dataset_label"] for r in members if r["dataset_label"] not in initial)
    for case in labels:
        path = cold.GRAPHS / f"{case}.json"
        if not path.exists():
            rows.append(dict(case=case,status="missing"))
            continue
        graph = cold.read(path)
        bank,_ = cold.build_bank(case,graph["metadata"])
        d = cold.descriptors(graph,bank)
        if d is None:
            rows.append(dict(case=case,status="no_curved_tracks"))
            continue
        bias = cold.bias_vote(d)
        vote = cold.grid_vote(d,bias)
        before = time.perf_counter()
        soft = {arm:soft_grid(d,bias,arm=="fitted_c") for arm in ("c0","fitted_c")}
        middle = time.perf_counter()
        robust = consensus(d,bias,vote)
        after = time.perf_counter()
        rows.append(dict(case=case,status="processed",results=dict(soft_grid=soft,consensus=robust),
                         seconds=dict(soft_grid=middle-before,consensus=after-middle)))
    args.output.write_text(json.dumps(dict(rows=rows),allow_nan=False))


if __name__=="__main__":
    main()
