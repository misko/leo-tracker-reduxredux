"""Bounded factorial activity beam with sparse starts and joint group proposals."""
import itertools,math
import numpy as np
from scipy.optimize import linear_sum_assignment


def matching(scores):
    nr,ns=scores.shape
    if not nr or not ns:return 0.,()
    rr,cc=linear_sum_assignment(-np.column_stack([np.where(np.isfinite(scores),scores,-1e20),np.zeros((nr,nr))]))
    pairs=tuple((int(r),int(c)) for r,c in zip(rr,cc) if c<ns and scores[r,c]>0)
    return sum(float(scores[r,c]) for r,c in pairs),pairs


def transition(old,new,n,dt):
    birth=1/90;death=1/35;eq=birth/(birth+death);rho=math.exp(-(birth+death)*max(dt,0))
    p01=max(eq*(1-rho),1e-15);p11=min(max(eq+(1-eq)*rho,1e-15),1-1e-15)
    n11=(old&new).bit_count();n10=(old&~new).bit_count();n01=(new&~old).bit_count();n00=n-n11-n10-n01
    return n11*math.log(p11)+n10*math.log1p(-p11)+n01*math.log(p01)+n00*math.log1p(-p01)


def decode(times,groups,receiver,channel,gain,visible,pdet,beam_width=16):
    allpairs=[];n=gain.shape[1]
    for lane in sorted(set(zip(receiver.tolist(),channel.tolist()))):
        lane_rows=np.flatnonzero((receiver==lane[0])&(channel==lane[1]))
        sequence=sorted(np.unique(groups[lane_rows]),key=lambda g:float(np.median(times[lane_rows[groups[lane_rows]==g]])))
        beam={0:(0.,None)};previous=None
        for group in sequence:
            rows=lane_rows[groups[lane_rows]==group];now=float(np.median(times[rows]));scores=gain[rows]
            useful=np.flatnonzero(np.any(scores>0,axis=0));useful_mask=sum(1<<int(j) for j in useful)
            _,map_pairs=matching(scores);joint=sum(1<<c for _,c in map_pairs)
            cache={}
            def emission(mask):
                if mask not in cache:
                    cols=[i for i in range(n) if mask&(1<<i)]
                    reward,local=matching(scores[:,cols]);pairs=tuple((int(rows[r]),cols[c]) for r,c in local)
                    active_visible=sum(bool(visible[rows[0],c]) for c in cols)
                    value=reward+active_visible*math.log1p(-pdet)-math.log1p(-math.exp(-2)*(1-pdet)**active_visible)
                    cache[mask]=(value,pairs)
                return cache[mask]
            newbeam={}
            for old,(score,path) in beam.items():
                masks={old,0,joint,old|joint,old&useful_mask}
                for bit in range(n):
                    if (old|useful_mask)&(1<<bit):masks.add(old^(1<<bit))
                if previous is None:
                    # Group-supported subsets only; never enumerate 2**all_satellites.
                    if len(useful)<=12:
                        masks.update(sum(1<<int(useful[j]) for j in range(len(useful)) if subset&(1<<j)) for subset in range(1<<len(useful)))
                for new in masks:
                    reward,pairs=emission(new)
                    prior=(new.bit_count()*math.log(.18)+(n-new.bit_count())*math.log(.82) if previous is None else transition(old,new,n,now-previous))
                    total=score+prior+reward
                    if new not in newbeam or total>newbeam[new][0]:newbeam[new]=(total,(path,pairs))
            beam=dict(sorted(newbeam.items(),key=lambda item:item[1][0],reverse=True)[:beam_width]);previous=now
        if beam:
            _,path=max(beam.values(),key=lambda item:item[0])
            while path is not None:path,pairs=path;allpairs.extend(pairs)
    return allpairs
