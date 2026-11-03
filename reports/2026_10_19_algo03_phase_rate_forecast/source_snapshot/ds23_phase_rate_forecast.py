"""One extra causal phase-forecast feature: old/current phase disagreement rate.

Features use only the two already available element sets. Later TLE updates
are chronological prediction proxies, never orbit truth. RF and GPS are absent.
The existing phase distribution scales/tails stay fixed in this mean test.
"""

from functools import lru_cache
import numpy as np
from sgp4.api import Satrec
from learn_ds23_causal_phase_forecast import distribution_cost
from leo.sky.frames import julian_day_from_utc_ns

BETAS=np.array([-4.,-2.,-1.,-.5,-.25,0.,.25,.5,1.,2.,4.])


def phase_difference(older_position,current_position,current_velocity):
    pa,pb,vb=map(lambda v:np.asarray(v,float),(older_position,current_position,current_velocity))
    if any(v.shape!=(3,) or not np.isfinite(v).all() for v in (pa,pb,vb)) or vb@vb<=0:
        raise ValueError("finite TEME states and nonzero reference velocity required")
    return float((pa-pb)@vb/(vb@vb))


@lru_cache(maxsize=65536)
def disagreement_rate(older_lines,current_lines,target_ns):
    satellites=[Satrec.twoline2rv(*lines) for lines in (older_lines,current_lines)]
    phases=[]
    for delta_ns in (-30_000_000_000,30_000_000_000):
        jd,fr=julian_day_from_utc_ns(np.array([target_ns+delta_ns]))
        states=[s.sgp4(float(jd[0]),float(fr[0])) for s in satellites]
        if any(s[0] for s in states):
            raise ValueError("causal phase-rate propagation failed")
        phases.append(phase_difference(states[0][1],states[1][1],states[1][2]))
    return (phases[1]-phases[0])/60.


def prediction(rows,model,beta):
    sigma=np.array([r["predicted_sigma_s"] for r in rows])
    ordinary=model["shrinkage"]*np.array([r["unit_forecast_s"] for r in rows])
    rate=np.array([r["rate_feature_s"] for r in rows])
    limit=np.minimum(15.,3*sigma)
    return np.clip(ordinary+beta*rate,-limit,limit)


def cost(rows,model,beta):
    if not rows:
        return 0.
    target=np.array([r["next_innovation_s"] for r in rows])
    sigma=np.array([r["predicted_sigma_s"] for r in rows])
    return float(distribution_cost(target-prediction(rows,model,beta),sigma,model["multiplier"],model["nu"]).sum())


def fit_beta(rows,model):
    if not rows:
        return dict(beta=0.,candidates=[])
    candidates=[dict(beta=float(beta),cost=cost(rows,model,beta)) for beta in BETAS]
    penalty=np.log(len(rows))
    chosen=min(candidates,key=lambda r:(r["cost"]+(penalty if r["beta"] else 0.),abs(r["beta"])))
    return dict(beta=chosen["beta"],candidates=candidates,penalty=penalty)


def qualify(rows,boundary,prefix_model,full_model):
    train=[r for r in rows if r["validation_time_ns"]<=boundary]
    test=[r for r in rows if r["validation_time_ns"]>boundary]
    prefix=fit_beta(train,prefix_model)
    gain=cost(test,prefix_model,0.)-cost(test,prefix_model,prefix["beta"])
    qualified=len(train)>=30 and len(test)>=30 and prefix["beta"]!=0 and gain>np.log(len(test))
    full=fit_beta(rows,full_model)
    return dict(qualified=bool(qualified),beta=full["beta"] if qualified else 0.,prefix=prefix,all_past=full,
        validation_gain=float(gain),training_count=len(train),validation_count=len(test),
        chronological_holdout_before_RF=True,same_phase_variance_tails_and_mean_clip=True)
