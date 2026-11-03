"""Training-only bounded history selection with immutable catalog timing modes.

Residual OU states rank assignments; they never alter reported physical errors.
Beam scores are heuristic, not calibrated probabilities or identity evidence.
"""
from dataclasses import dataclass
import math
import numpy as np


@dataclass
class History:
    score: float
    chosen: dict
    mean: np.ndarray
    var: np.ndarray
    last: np.ndarray
    pairs: tuple


def rank_modes(times, groups, lanes, residual, gain, numbers, offsets):
    """Independent per-catalog training history ranking; no coverage claim.

    Modes compete using causal pre-update OU scores, one best peak per probe.
    Different catalogs may reuse training evidence HERE; final joint decoding
    must resolve collisions. Priors are assessed after accumulating a track,
    avoiding the joint beam's negative first-step admission barrier.
    """
    times=np.asarray(times);groups=np.asarray(groups);lanes=np.asarray(lanes)
    order=sorted(np.unique(groups),key=lambda g:float(np.min(times[groups==g])))
    group_rows=[np.flatnonzero(groups==g) for g in order]
    scores=np.full(len(numbers),-np.inf);assignments={}
    for col in range(len(numbers)):
        mean={};var={};last={};pairs=[];values={}
        for rows in group_rows:
            good=rows[np.isfinite(gain[rows,col])]
            if not len(good):continue
            lane=int(lanes[good[0]]);now=float(times[good[0]])
            if np.any(lanes[good]!=lane):raise ValueError('Probe spans multiple lanes')
            rho=math.exp(-max(0.,now-last.get(lane,now))/30.)
            mu=rho*mean.get(lane,0.);v=rho*rho*var.get(lane,100.**2)+100.**2*(1-rho*rho)
            e=residual[good,col];iv=v+200.**2
            value=gain[good,col]-.5*((e-mu)**2/iv-e**2/200.**2+np.log(iv/200.**2))
            j=int(np.argmax(value));row=int(good[j])
            if value[j]>0:
                values[row]=float(value[j]);pairs.append((row,col));k=v/iv
                mean[lane]=mu+k*(residual[row,col]-mu);var[lane]=v*(1-k);last[lane]=now
        # Only temporally coherent per-lane support can admit a timing mode.
        kept=[]
        for lane in sorted({int(lanes[r]) for r,_ in pairs}):
            rr=np.array([r for r,_ in pairs if lanes[r]==lane],int)
            for part in np.split(rr,np.flatnonzero(np.diff(times[rr])>5)+1):
                if len(part)>=10 and times[part[-1]]-times[part[0]]>=5:
                    kept.extend((int(r),col) for r in part)
        if kept:
            score=sum(values[r] for r,_ in kept)
            scores[col]=score-.5*np.log(max(1,len(group_rows)))-.5*offsets[col]**2
            assignments[col]=kept
    chosen={}
    for col,number in enumerate(numbers):
        number=int(number)
        if scores[col]>0 and (number not in chosen or scores[col]>scores[chosen[number]]):chosen[number]=col
    return chosen,scores,[p for col in chosen.values() for p in assignments[col]]


def track(times, groups, lanes, residual, gain, numbers, offsets, *, beam=16,
          group_cap=16, top_per_row=3, state=True):
    times=np.asarray(times); groups=np.asarray(groups); lanes=np.asarray(lanes)
    numbers=np.asarray(numbers); offsets=np.asarray(offsets)
    if residual.shape!=gain.shape or gain.shape!=(len(times),len(numbers)):
        raise ValueError('Inconsistent mode arrays')
    if not len(times): return History(0.,{},np.zeros((0,len(numbers))),np.zeros((0,len(numbers))),np.zeros(0),())
    shape=(int(lanes.max())+1,len(numbers))
    histories=[History(0.,{},np.zeros(shape),np.full(shape,100.**2),np.full(shape[0],np.nan),())]
    penalty=.5*np.log(max(1,len(np.unique(groups))))+.5*offsets**2
    order=sorted(np.unique(groups),key=lambda g:float(np.min(times[groups==g])))
    for group in order:
        rows=np.flatnonzero(groups==group); lane=int(lanes[rows[0]])
        if np.any(lanes[rows]!=lane): raise ValueError('Probe spans multiple lanes')
        now=float(times[rows[0]]); extensions=[]
        for h in histories:
            mean=h.mean.copy(); var=h.var.copy(); last=h.last.copy()
            dt=0. if not np.isfinite(last[lane]) else max(0.,now-last[lane])
            rho=math.exp(-dt/30.); mean[lane]*=rho
            var[lane]=rho*rho*var[lane]+100.**2*(1-rho*rho); last[lane]=now
            allowed=np.array([int(n) not in h.chosen or h.chosen[int(n)]==c for c,n in enumerate(numbers)])
            # A mode's prior and catalog birth cost are charged once, not per peak.
            birth=np.array([0. if int(n) in h.chosen else penalty[c] for c,n in enumerate(numbers)])
            partial=[(0.,frozenset(),())]
            for row in rows:
                value=gain[row].copy()
                if state:
                    iv=var[lane]+200.**2
                    value+=-.5*((residual[row]-mean[lane])**2/iv-residual[row]**2/200.**2+np.log(iv/200.**2))
                value-=birth; value[~allowed]=-np.inf
                candidates=[int(c) for c in np.argsort(value)[-top_per_row:][::-1] if np.isfinite(value[c])]
                nxt=[]
                for score,used,pairs in partial:
                    nxt.append((score,used,pairs))
                    for col in candidates:
                        catalog=int(numbers[col])
                        if catalog not in used:
                            nxt.append((score+float(value[col]),used|{catalog},pairs+((int(row),col),)))
                partial=sorted(nxt,key=lambda p:p[0],reverse=True)[:group_cap]
            for delta,_,pairs in partial:
                chosen=h.chosen.copy(); bm=mean.copy(); bv=var.copy()
                for row,col in pairs:
                    chosen[int(numbers[col])]=col
                    if state:
                        k=bv[lane,col]/(bv[lane,col]+200.**2)
                        bm[lane,col]+=k*(residual[row,col]-bm[lane,col]); bv[lane,col]*=1-k
                extensions.append(History(h.score+delta,chosen,bm,bv,last,h.pairs+pairs))
        histories=sorted(extensions,key=lambda h:h.score,reverse=True)[:beam]
    return histories[0]
