"""Learn phase scale over ages covered by past publication intervals.

Later, already archived element sets are retrospective prediction proxies at
historical targets. They are not ephemeris truth. Each version triplet has
unit total weight regardless of the number of historical targets.
"""

import numpy as np
from sgp4.api import Satrec
from investigate_ds23_adaptive_failures import causal_phase_sigma
from learn_ds23_causal_phase_forecast import distribution_cost
from leo.sky.frames import julian_day_from_utc_ns

FRACTIONS=(0.,.25,.5,.75)


def target_times(a,b,c,cutoff):
    if not (a["epoch"]<b["epoch"]<c["epoch"]<=c["collected_utc_ns"]<=cutoff and
            a["collected_utc_ns"]<=b["collected_utc_ns"]<c["collected_utc_ns"] and
            b["epoch"]<=b["collected_utc_ns"]):
        return []
    begin,end=b["collected_utc_ns"],c["collected_utc_ns"]
    return [begin+int(f*(end-begin)) for f in FRACTIONS]


def transition(a,b,c,cutoff):
    times=target_times(a,b,c,cutoff)
    if not times:return []
    gap=(b["epoch"]-a["epoch"])/1e9
    if gap<1:return []
    jd,fr=julian_day_from_utc_ns(np.array(times,dtype=np.int64))
    states=[Satrec.twoline2rv(*v["lines"]).sgp4_array(jd,fr) for v in (a,b,c)]
    if any(np.any(state[0]) for state in states):return []
    pa,pb,pc=[state[1] for state in states];vb=states[1][2]
    denominator=np.sum(vb*vb,axis=1)
    old=np.sum((pa-pb)*vb,axis=1)/denominator
    innovation=np.sum((pc-pb)*vb,axis=1)/denominator
    rows=[]
    for k,t in enumerate(times):
        age=(t-b["epoch"])/1e9
        rows.append(dict(validation_time_ns=c["collected_utc_ns"],target_utc_ns=t,
            age_s=age,epoch_gap_s=gap,old_middle_alignment_s=float(old[k]),
            next_innovation_s=float(innovation[k]),unit_forecast_s=float(-np.clip(age/gap,0,2)*old[k]),
            predicted_sigma_s=causal_phase_sigma(old[k],age,gap),weight=1/len(times)))
    return rows


def arrays(rows,model):
    y=np.array([r["next_innovation_s"] for r in rows])
    forecast=np.array([r["unit_forecast_s"] for r in rows])
    base=np.array([r["predicted_sigma_s"] for r in rows])
    limit=np.minimum(15.,3*base)
    residual=y-np.clip(model["shrinkage"]*forecast,-limit,limit)
    proxy=np.array([abs(r["old_middle_alignment_s"])*r["age_s"]/r["epoch_gap_s"] for r in rows])
    return residual,proxy,base,np.array([r["weight"] for r in rows])


def cost(rows,model,scale=None):
    if not rows:return 0.
    residual,proxy,base,weight=arrays(rows,model)
    sigma=base*model["multiplier"] if scale is None else np.clip(np.hypot(scale["floor_s"],scale["gain"]*proxy),.02,15.)
    return float(weight@distribution_cost(residual,sigma,1.,model["nu"]))


def learn(rows,model):
    residual,proxy,_,weight=arrays(rows,model)
    bounds=np.log(np.array([[.02,2.],[.02,3.]]));lo,hi=bounds[:,0].copy(),bounds[:,1].copy()
    point=None;value=float("inf")
    for _ in range(5):
        axes=[np.linspace(lo[k],hi[k],7) for k in range(2)]
        for a in axes[0]:
            for b in axes[1]:
                floor,gain=np.exp([a,b]);sigma=np.clip(np.hypot(floor,gain*proxy),.02,15.)
                score=float(weight@distribution_cost(residual,sigma,1.,model["nu"]))
                if score<value:point,value=np.array([a,b]),score
        step=(hi-lo)/6;lo=np.maximum(bounds[:,0],point-step);hi=np.minimum(bounds[:,1],point+step)
    return dict(floor_s=float(np.exp(point[0])),gain=float(np.exp(point[1])),cost=value)


def qualify(rows,boundary,prefix_model,full_model):
    train=[r for r in rows if r["validation_time_ns"]<=boundary]
    test=[r for r in rows if r["validation_time_ns"]>boundary]
    ntrain=sum(r["weight"] for r in train);ntest=sum(r["weight"] for r in test)
    if ntrain<30 or ntest<30:return dict(qualified=False,reason="insufficient independent publication triplets")
    prefix=learn(train,prefix_model);full=learn(rows,full_model)
    gain=cost(test,prefix_model)-cost(test,prefix_model,prefix)
    return dict(qualified=bool(gain>2*np.log(ntest)),validation_gain=gain,penalty=2*np.log(ntest),
        prefix_scale=prefix,all_past_scale=full,training_triplets=ntrain,validation_triplets=ntest,
        correlated_targets_share_unit_triplet_weight=True,chronological_split_by_label_publication=True)
