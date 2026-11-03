"""Direct full-catalogue Doppler likelihood constrained to the exact Sacramento disk."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json,math,sys,time
from pathlib import Path
import numpy as np
from scipy.optimize import differential_evolution,minimize
from scipy.special import gammaln,logsumexp
HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[1]; LEGACY=ROOT/"reports/2026_09_30_gaussian_sum_64_scan"
sys.path[:0]=[str(ROOT/"src"),str(LEGACY)]
from physics import LIGHT_KM_S,WGS84_A_KM,WGS84_F,OrbitBank,PhysicsConfig,enu_state_ecef_km,geometric_candidate_union
from statistical_models import constant_contrasts,exponential_covariance,normalized_profile_logpdf
from association_runner import CompetitionGroup,score_position_associations
CENTER_LAT,CENTER_LON,RADIUS_KM=38.5816,-121.4944,250.0
def en_latlon(e,n):
    distance=math.hypot(e,n)
    if distance==0:return [CENTER_LAT,CENTER_LON]
    lat1=math.radians(CENTER_LAT);lon1=math.radians(CENTER_LON);angular=distance/6371.007180918475;bearing=math.atan2(e,n)
    lat2=math.asin(math.sin(lat1)*math.cos(angular)+math.cos(lat1)*math.sin(angular)*math.cos(bearing))
    lon2=lon1+math.atan2(math.sin(bearing)*math.sin(angular)*math.cos(lat1),math.cos(angular)-math.sin(lat1)*math.sin(lat2))
    return [math.degrees(lat2),((math.degrees(lon2)+180)%360)-180]

@dataclass(frozen=True)
class AssociationProblem:
    signal_log_likelihood:np.ndarray; background_log_likelihood:np.ndarray; candidate_labels:tuple[str,...]
    signal_log_prior:np.ndarray|None=None; background_log_prior:np.ndarray|None=None
    def __post_init__(self):
        s=np.asarray(self.signal_log_likelihood,float); b=np.asarray(self.background_log_likelihood,float)
        if s.ndim!=2 or b.shape!=(s.shape[0],) or s.shape[1]!=len(self.candidate_labels): raise ValueError("association shapes disagree")
        if not np.all(np.isfinite(s)) or not np.all(np.isfinite(b)): raise ValueError("association scores must be finite")
def digest(p): return "sha256:"+hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load_methods(): return json.loads((HERE/"method-configs.json").read_text())["arms"]
def training_masks(source):
    out={}
    for r in source.get("tracks",[]):
        m=np.asarray(r.get("training_mask",[]),bool)
        if m.shape==(len(r.get("measured_hz",[])),): out[r["track_id"]]=m
    return out
def independent_tracks(evidence):
    keep=[]; drop=[]; used=set()
    for r in sorted(evidence["tracks"],key=lambda x:(x["support_end_utc_ns"],x["support_start_utc_ns"],x["track_id"])):
        ids=set(r["physical_observation_ids"])
        if len(ids)<3 or ids&used: drop.append({"track_id":r["track_id"],"reason":"overlap_or_short"})
        else: keep.append(r); used.update(ids)
    return keep,drop
def _logpdf(r,scale,gaussian=False):
    if gaussian:return -.5*(r/scale)**2-np.log(scale)-.5*math.log(2*math.pi)
    nu=4.; z=r/scale
    return gammaln(2.5)-gammaln(2.)-.5*math.log(nu*math.pi)-np.log(scale)-2.5*np.log1p(z*z/nu)
def _spread(a,n=8): return a if len(a)<=n else a[np.unique(np.rint(np.linspace(0,len(a)-1,n)).astype(int))]

class DirectLikelihood:
    def __init__(self,evidence,source,bank,tracks,masks):
        self.bank=bank; self.labels=tuple(map(str,bank.norad_ids)); self.rows=[]; self._state_cache={}; self._geometry_log_weight=None
        for r in tracks:
            if r["track_id"] not in masks: raise ValueError("source training mask cannot be bound")
            ix=_spread(np.flatnonzero(masks[r["track_id"]]));
            if len(ix)<3: continue
            t=(np.asarray(r["times_utc_ns"],np.int64)-source["start_utc_ns"])/1e9
            self.rows.append(dict(track_id=r["track_id"],times=t[ix],y=np.asarray(r["measured_hz"],float)[ix],rx=int(r["receiver_id"]),channel=int(r["channel"]),start=int(r["support_start_utc_ns"]),end=int(r["support_end_utc_ns"]),rf=float(r["rf_hz"])))
        if not self.rows: raise ValueError("no training tracks")
    def _states(self,t,tau):
        key=(t.tobytes(),float(tau))
        if key in self._state_cache:return self._state_cache[key]
        q=t+tau; g=self.bank.times_s; h=g[1]-g[0]
        if q.min()<g[1] or q.max()>g[-2]: raise ValueError("orbit time support")
        k=np.clip(np.searchsorted(g,q,side="right")-1,0,len(g)-2); u=(q-g[k])/h
        p0=self.bank.positions_ecef_km[:,k];p1=self.bank.positions_ecef_km[:,k+1];v0=self.bank.velocities_ecef_km_s[:,k];v1=self.bank.velocities_ecef_km_s[:,k+1]
        p=(2*u**3-3*u**2+1)[None,:,None]*p0+(u**3-2*u**2+u)[None,:,None]*h*v0+(-2*u**3+3*u**2)[None,:,None]*p1+(u**3-u**2)[None,:,None]*h*v1
        left=np.clip(k-1,0,len(g)-4);v=np.zeros_like(p)
        for j in range(4):
            kj=left+j;b=np.ones(len(q))
            for z in range(4):
                if z!=j:b*=(q-g[left+z])/(g[kj]-g[left+z])
            v+=b[None,:,None]*self.bank.velocities_ecef_km_s[:,kj]
        if len(self._state_cache)>=256:self._state_cache.pop(next(iter(self._state_cache)))
        self._state_cache[key]=(p,v);return p,v
    def _pred(self,row,e,n,tau,epoch=0.):
        rx=enu_state_ecef_km(e,n,0.,CENTER_LAT,CENTER_LON);p,v=self._states(row["times"],tau+epoch);line=p-rx;unit=line/np.linalg.norm(line,axis=2,keepdims=True)
        pred=-11_200_000_000./LIGHT_KM_S*np.sum(v*unit,axis=2); b=WGS84_A_KM*(1-WGS84_F);up=rx/np.array([WGS84_A_KM**2,WGS84_A_KM**2,b**2]);up/=np.linalg.norm(up)
        return pred,np.degrees(np.arcsin(np.clip(unit@up,-1,1)))
    def association_problem(self,theta,arm):
        e,n,tau=map(float,theta[:3]);dr=np.asarray(theta[3:5]) if arm=="M3" else np.zeros(2);scale=float(np.exp(theta[3])) if arm=="C2" else 100.;rows=[];bg=[]
        geometry_log_weight=None;base_cache={}
        if arm=="M5":
            fisher=np.zeros((len(self.labels),2,2));step=.1
            for r in self.rows:
                base,elevation=self._pred(r,e,n,tau);base_cache[r["track_id"]]=(base,elevation)
                if self._geometry_log_weight is None:
                    de=(self._pred(r,e+step,n,tau)[0]-self._pred(r,e-step,n,tau)[0])/(2*step);dn=(self._pred(r,e,n+step,tau)[0]-self._pred(r,e,n-step,tau)[0])/(2*step)
                    jac=np.stack((de-de.mean(axis=1)[:,None],dn-dn.mean(axis=1)[:,None]),axis=2)/100.;fisher+=np.einsum("nti,ntj->nij",jac,jac)
            if self._geometry_log_weight is None:
                determinant=np.maximum(np.linalg.det(fisher),1e-18);self._geometry_log_weight=.5*np.log(determinant);self._geometry_log_weight-=logsumexp(self._geometry_log_weight)
            geometry_log_weight=self._geometry_log_weight
        for r in self.rows:
            scores=[];elev=None
            for ep in ((-.5,0.,.5) if arm=="M4" else (0.,)):
                if arm=="M5" and ep==0.:pred,elev=base_cache[r["track_id"]]
                else:pred,elev=self._pred(r,e,n,tau,ep)
                y=r["y"]-dr[r["rx"]]*(r["rf"]/11_200_000_000.)*(r["times"]-r["times"].mean());res=y[None]-pred;res-=np.median(res,axis=1)[:,None]
                if arm=="M2":
                    cov=exponential_covariance(r["times"],sigma_hz=100.,correlation_fraction=.2,correlation_time_s=10.)
                    q=constant_contrasts(res.shape[1]);chol=np.linalg.cholesky(q@cov@q.T);projected=res@q.T;solved=np.linalg.solve(chol,projected.T).T
                    score=-.5*(solved.shape[1]*math.log(2*math.pi)+2*np.log(np.diag(chol)).sum()+np.sum(solved*solved,axis=1))
                else: score=np.sum(_logpdf(res,scale),axis=1)
                if arm=="M8" and res.shape[1]>=6:
                    for cut in range(3,res.shape[1]-2):
                        rr=res.copy();rr[:,:cut]-=np.median(rr[:,:cut],axis=1)[:,None];rr[:,cut:]-=np.median(rr[:,cut:],axis=1)[:,None];score=np.maximum(score,np.sum(_logpdf(rr,scale),axis=1)-.5*math.log(res.shape[1]))
                scores.append(score)
            score=logsumexp(np.stack(scores),axis=0)-math.log(len(scores));visible=np.all(elev>=-2,axis=1);score=np.where(visible,score,-1e12)
            if arm=="M5":score+=geometry_log_weight
            rows.append(score)
            if arm=="M2": bg_cov=exponential_covariance(r["times"],sigma_hz=1000.,correlation_fraction=.2,correlation_time_s=10.);bg.append(float(normalized_profile_logpdf(r["y"],bg_cov)))
            else: bg.append(float(np.sum(_logpdf(r["y"]-np.median(r["y"]),1000.))))
        return AssociationProblem(np.stack(rows),np.asarray(bg),self.labels)
    def score_position(self,theta,arm):
        if theta[0]**2+theta[1]**2>RADIUS_KM**2:return {"negative_log_posterior":1e12+(math.hypot(theta[0],theta[1])-RADIUS_KM)**2}
        p=self.association_problem(theta,arm); candidate_prior=0. if arm=="M5" else -math.log(len(self.labels)); per=logsumexp(np.column_stack((p.signal_log_likelihood+candidate_prior+math.log(.8),p.background_log_likelihood+math.log(.2))),axis=1)
        reg=.5*np.sum((np.asarray(theta[3:5])/.5)**2) if arm=="M3" else .5*((theta[3]-math.log(100))/.7)**2 if arm=="C2" else 0.
        return {"negative_log_posterior":float(-per.sum()+reg),"association_problem":p}
    def association_groups(self,problem):
        pending=set(range(len(self.rows))); groups=[]
        for i in range(len(self.rows)):
            if i not in pending: continue
            pending.remove(i); a=self.rows[i]; partner=None
            for j in sorted(pending):
                b=self.rows[j]
                if a["rx"]==b["rx"] and a["channel"]==b["channel"] and max(a["start"],b["start"])<=min(a["end"],b["end"]): partner=j;break
            indices=[i]
            if partner is not None: pending.remove(partner);indices.append(partner)
            att="response-independent-same-rx-overlap-v1" if len(indices)==2 else "response-independent-singleton-v1"
            groups.append(CompetitionGroup("group-"+"-".join(map(str,indices)),tuple(self.rows[z]["track_id"] for z in indices),problem.candidate_labels,problem.signal_log_likelihood[indices],problem.background_log_likelihood[indices],att))
        return tuple(groups)
    def score_grouped_association(self,theta,arm):
        if theta[0]**2+theta[1]**2>RADIUS_KM**2:return {"negative_log_posterior":1e12+(math.hypot(theta[0],theta[1])-RADIUS_KM)**2}
        raw=self.association_problem(theta,"C1");problem=AssociationProblem(raw.signal_log_likelihood+math.log(.8)-math.log(len(self.labels)),raw.background_log_likelihood+math.log(.2),raw.candidate_labels); result=score_position_associations(self.association_groups(problem),arm)
        return {"negative_log_posterior":float(-result.log_score),"association_problem":problem,"group_count":result.group_count,"exact_probability_semantics":result.exact_probability_semantics}

def _starts():return [(0.,0.,0.)]+[(r*math.cos(a),r*math.sin(a),0.) for r in (80.,160.,240.) for a in np.linspace(0,2*math.pi,8,endpoint=False)]
def run_model(unit,arm,evidence_root):
    begun=time.monotonic();method=load_methods()[arm];ep=Path(evidence_root)/f"{unit}.json";op=Path(evidence_root)/f"{unit}-orbits.json";e=json.loads(ep.read_text());om=json.loads(op.read_text());sp=Path(e["source"]["path"]);source=json.loads(sp.read_text());bp=Path(om["state_file"])
    if not om["tle"]["causal"] or om["session_id"]!=e["session_id"] or digest(sp)!=e["source"]["sha256"] or digest(bp)!=om["state_sha256"]:raise ValueError("causal binding failure")
    receipt={"schema":"sacramento-model-prediction/v2","unit_id":unit,"arm":arm,"method":method,"status":"running","reference_coordinate_accessed":False,"prior":{"center":[CENTER_LAT,CENTER_LON],"radius_km":RADIUS_KM,"density":"exact uniform disk"},"inputs":{str(p):digest(p) for p in (ep,op,sp,bp)}}
    if arm=="C0":receipt.update(status="completed",qualified=True,point_latlon_deg=[CENTER_LAT,CENTER_LON],point_estimate={"east_km":0.,"north_km":0.,"tau_s":0.},wall_seconds=time.monotonic()-begun);return receipt
    with np.load(bp,allow_pickle=False) as d:bank=OrbitBank(tuple(map(int,d["satellite_ids"])),d["knot_times_s"],d["positions_ecef_km"],d["velocities_ecef_km_s"])
    cfg=PhysicsConfig(prior_center_lat_deg=CENTER_LAT,prior_center_lon_deg=CENTER_LON,support_radius_km=RADIUS_KM);union=geometric_candidate_union(bank,cfg);wanted=set(union.norad_ids);ix=np.array([i for i,x in enumerate(bank.norad_ids) if x in wanted]);bank=OrbitBank(tuple(bank.norad_ids[i] for i in ix),bank.times_s,bank.positions_ecef_km[ix],bank.velocities_ecef_km_s[ix]);tracks,drop=independent_tracks(e);like=DirectLikelihood(e,source,bank,tracks,training_masks(source))
    bounds=[(-250,250),(-250,250),(-5,5)]+([(-3,7)] if arm=="C2" else [(-2,2),(-2,2)] if arm=="M3" else [])
    objective=(lambda x:like.score_grouped_association(x,arm)["negative_log_posterior"]) if arm in {"G1","M1","G2"} else (lambda x:like.score_position(x,arm)["negative_log_posterior"])
    if arm=="M9":res=differential_evolution(lambda x:like.score_position(x,"C1")["negative_log_posterior"],bounds[:3],seed=20260930,popsize=8,maxiter=12,polish=True,workers=1)
    else:
        seeded=[]
        for s in _starts():
            x=np.array(s+((math.log(100.),) if arm=="C2" else (0.,0.) if arm=="M3" else ()));simplex=np.tile(x,(len(x)+1,1));steps=[12.,12.,.5]+([.3] if arm=="C2" else [.1,.1] if arm=="M3" else [])
            for j,step in enumerate(steps): simplex[j+1,j]+=step
            seeded.append((objective(x),x,simplex))
        refinement_count=1 if arm in {"G1","M1","G2"} else 2
        rr=[minimize(objective,x,method="Nelder-Mead",bounds=bounds,options={"initial_simplex":simplex,"maxiter":60,"xatol":.5,"fatol":.5}) for _,x,simplex in sorted(seeded,key=lambda z:z[0])[:refinement_count]]
        res=min(rr,key=lambda z:z.fun)
    chosen_arm="C1" if arm=="M9" else arm;final=like.score_grouped_association(res.x,arm) if arm in {"G1","M1","G2"} else like.score_position(res.x,chosen_arm);p=final["association_problem"]
    held_masks={k:~v for k,v in training_masks(source).items()};held=None
    try:
        held_like=DirectLikelihood(e,source,bank,tracks,held_masks);held=float(held_like.score_position(res.x,chosen_arm)["negative_log_posterior"])
    except ValueError: pass
    point={"east_km":float(res.x[0]),"north_km":float(res.x[1]),"tau_s":float(res.x[2])}; qualified=bool(res.success and np.isfinite(res.fun) and np.all(np.isfinite(res.x)) and math.hypot(res.x[0],res.x[1])<=RADIUS_KM)
    receipt.update(status="completed" if qualified else "optimizer_unqualified",qualified=qualified,objective=float(res.fun),held_refit_negative_log_diagnostic=held,held_diagnostic_limitation="held offsets and associations are reprofiled; this is not a frozen-training predictive score",optimizer={"diagnostic_converged":bool(res.success),"message":str(res.message),"nfev":int(res.nfev)},candidate_count=len(bank.norad_ids),retained_tracks=len(like.rows),excluded_tracks=drop,association_summary={"rows":p.signal_log_likelihood.shape[0],"candidates":p.signal_log_likelihood.shape[1],"best_candidate_log_scores":np.max(p.signal_log_likelihood,axis=1).tolist(),"background_log_scores":p.background_log_likelihood.tolist()},wall_seconds=time.monotonic()-begun)
    if qualified: receipt.update(point_estimate=point,point_latlon_deg=en_latlon(point["east_km"],point["north_km"]))
    else: receipt["diagnostic_unqualified_point"]=point
    return receipt
