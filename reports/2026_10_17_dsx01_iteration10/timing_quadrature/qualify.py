"""Fixed synthetic shared-timing oracle and metadata-only interpolator bound."""
from itertools import product
import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from scipy.special import logsumexp,roots_hermitenorm

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parents[1]
BANK=REPORTS/'2026_10_17_dsx01_iteration5/metadata_bank'
COUNTS=REPORTS/'2026_10_17_dsx01_iteration8/coherent_pilot/source_freeze.json'
ORDERS=(3,5,17,65,257,1025)


def sha(path):return 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())
def plain(x):
    if isinstance(x,np.ndarray):return x.tolist()
    if isinstance(x,np.generic):return x.item()
    if isinstance(x,dict):return {k:plain(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [plain(v) for v in x]
    return x
def save(path,value):
    with Path(path).open('x') as stream:json.dump(plain(value),stream,indent=2,allow_nan=False);stream.write('\n')


def inputs(residual,slope,sigma):
    r,g=np.asarray(residual,float),np.asarray(slope,float)
    s=np.broadcast_to(np.asarray(sigma,float),r.shape)
    if r.ndim!=1 or len(r)==0 or g.shape!=r.shape or any(not np.isfinite(a).all() for a in (r,g,s)) or np.any(s<=0):
        raise ValueError('Aligned finite nonempty vectors and positive sigma required')
    return r,g,s


def analytic_log_marginal(residual,slope,*,sigma=125.,timing_sigma=2.):
    """N(0,diag(sigma²)+timing_sigma²*g*gᵀ), without cancellation."""
    r,g,s=inputs(residual,slope,sigma)
    if not np.isfinite(timing_sigma) or timing_sigma<=0:raise ValueError('Positive timing width required')
    z,b=r/s,g/s;norm=float(b@b)
    if norm:
        coefficient=float(z@b)/norm;orthogonal=z-coefficient*b
        quadratic=float(orthogonal@orthogonal)+coefficient**2*norm/(1+timing_sigma**2*norm)
    else:quadratic=float(z@z)
    logdet=float(2*np.log(s).sum()+np.log1p(timing_sigma**2*norm))
    return -.5*(len(r)*np.log(2*np.pi)+logdet+quadratic)


def quadrature_log_marginal(residual,slope,nodes,weights,*,sigma=125.):
    """Nodes are timing seconds; represented nonnegative weights normalize once."""
    r,g,s=inputs(residual,slope,sigma);nodes,weights=np.asarray(nodes,float),np.asarray(weights,float)
    if nodes.ndim!=1 or nodes.shape!=weights.shape or not len(nodes) or not np.isfinite(nodes).all() or not np.isfinite(weights).all() or np.any(weights<0) or not np.any(weights>0):
        raise ValueError('Aligned finite nodes and nonnegative nonzero weights required')
    logweights=np.full(len(weights),-np.inf);np.log(weights,out=logweights,where=weights>0)
    logweights-=logsumexp(logweights)
    residuals=(r[:,None]-g[:,None]*nodes)/s[:,None]
    logdensity=np.sum(-.5*residuals**2-np.log(s[:,None])-.5*np.log(2*np.pi),axis=0)
    return float(logsumexp(logweights+logdensity))


def interpolator_bounds(position,velocity,nodes,*,rf_max_hz,height_m=0.):
    """Conservative per-object |dCFO/dtau| for every stored interpolation cell."""
    p,v,t=np.asarray(position,float),np.asarray(velocity,float),np.asarray(nodes,float)
    if p.ndim!=3 or p.shape!=v.shape or p.shape[1]!=len(t) or p.shape[2]!=3 or len(t)<2 or np.any(np.diff(t)<=0):
        raise ValueError('Aligned [K,T,3] bank and increasing times required')
    if any(not np.isfinite(x).all() for x in (p,v,t)) or not np.isfinite([rf_max_hz,height_m]).all() or rf_max_hz<=0:
        raise ValueError('Finite bank/RF/height required')
    dp=p[:,1:]-p[:,:-1];dv=v[:,1:]-v[:,:-1];dt=np.diff(t)[None,:]
    squared=np.einsum('kti,kti->kt',dp,dp)
    dot=np.einsum('kti,kti->kt',p[:,:-1],dp)
    alpha=np.clip(np.divide(-dot,squared,out=np.zeros_like(dot),where=squared>0),0.,1.)
    minimum_norm=np.linalg.norm(p[:,:-1]+alpha[:,:,None]*dp,axis=2)
    minimum_range=minimum_norm-(6378.137+abs(height_m)/1000.)
    invalid=minimum_range<=0
    # No invalid cell is discarded from a purported global bound.
    if np.any(invalid):return dict(valid=False,invalid_cells=int(invalid.sum()),minimum_range_km=minimum_range.min(axis=1))
    p_rate=np.linalg.norm(dp,axis=2)/dt;v_rate=np.linalg.norm(dv,axis=2)/dt
    max_v=np.maximum(np.linalg.norm(v[:,:-1],axis=2),np.linalg.norm(v[:,1:],axis=2))
    bound=rf_max_hz/299792.458*(v_rate+p_rate*max_v/minimum_range)
    return dict(valid=True,invalid_cells=0,bound_hz_s=bound.max(axis=1),minimum_range_km=minimum_range.min(axis=1))


def freeze():
    paths=[HERE/name for name in ['PROTOCOL.md','qualify.py','test_quadrature.py']]
    paths += [BANK/'freeze.json',BANK/'metadata-bank.npz',COUNTS]
    save(HERE/'source_freeze.json',dict(files={str(p):sha(p) for p in paths},maximum_seconds=60,
        synthetic_cases=27,orders=ORDERS,analytic_calls=27,quadrature_calls=162,localization_objectives=0,propagation_calls=0,fits=0))


def verify():
    for path,value in read(HERE/'source_freeze.json')['files'].items():
        if sha(path)!=value:raise ValueError('Frozen source/input changed: '+path)


def run():
    begun=time.monotonic();verify();deadline=begun+58
    rules={};diagnostics=[]
    for order in ORDERS:
        nodes,weights=roots_hermitenorm(order);rules[order]=(2*nodes,weights)
        norm=weights.sum();positive=weights>0
        diagnostics.append(dict(order=order,represented_positive_weights=int(positive.sum()),zero_weights=int((~positive).sum()),
            unnormalized_weight_sum=float(norm),normalized_mean=float(weights@(2*nodes)/norm),
            normalized_variance=float(weights@((2*nodes)**2)/norm)))
    rows=[]
    for m,g,truth in product([1,4,24],[20.,200.,2000.],[0.,.8,1.6]):
        r=np.full(m,g*truth);slopes=np.full(m,g);exact=analytic_log_marginal(r,slopes)
        values=[]
        for order in ORDERS:
            observed=quadrature_log_marginal(r,slopes,*rules[order])
            values.append(dict(order=order,log_marginal=observed,signed_log_error=observed-exact,
                absolute_log_error=abs(observed-exact),within_descriptive_001=abs(observed-exact)<=.001))
        rows.append(dict(m=m,slope_hz_s=g,delta_true_s=truth,analytic_log_marginal=exact,
            approximate_episode_timing_width_s=125./(g*np.sqrt(m)),quadrature=values))
    if time.monotonic()>deadline:raise TimeoutError('Whole qualifier bound before optional bank read')
    metadata=read(BANK/'freeze.json');counts=read(COUNTS)
    if sha(BANK/'metadata-bank.npz')!=metadata['bank_sha256']:raise ValueError('Metadata bank hash differs')
    with np.load(BANK/'metadata-bank.npz') as bank:
        numbers=bank['numbers'];nodes=bank['nodes_s'];position=bank['position_km'];velocity=bank['velocity_km_s']
    if len(numbers)!=845 or metadata['known_observations']!=3988 or counts['candidates']!=45:
        raise ValueError('Exact frozen metadata counts845/3988/45 required')
    per_object=[];valid=True;invalid=0
    for start in range(0,len(numbers),64):
        if time.monotonic()>deadline:raise TimeoutError('Whole qualifier bank arithmetic bound')
        end=min(start+64,len(numbers));result=interpolator_bounds(position[start:end],velocity[start:end],nodes,
            rf_max_hz=metadata['rf_metadata']['maximum_hz'],height_m=metadata['prior']['altitude_m'])
        valid=valid and result['valid'];invalid+=result['invalid_cells']
        for j,number in enumerate(numbers[start:end]):
            row=dict(number=int(number),minimum_range_lower_bound_km=float(result['minimum_range_km'][j]))
            if result['valid']:row['slope_upper_bound_hz_s']=float(result['bound_hz_s'][j])
            per_object.append(row)
    slopes=[row['slope_upper_bound_hz_s'] for row in per_object] if valid else None
    bound=dict(valid_global_bound=valid,invalid_range_cells=invalid,per_candidate=per_object,
        maximum_rf_hz=metadata['rf_metadata']['maximum_hz'],height_m=metadata['prior']['altitude_m'],
        cells_checked=len(numbers)*(len(nodes)-1),scope='Stored P/V interpolator only; all surface sites, no posterior-width or visibility bound')
    if valid:bound.update(global_upper_bound_hz_s=max(slopes),candidate_bound_quantiles_hz_s=np.quantile(slopes,[0,.5,.9,1.]))
    else:bound['omission_reason']='Nonpositive range lower bounds; no global bound claimed'
    memory=[]
    for order in ORDERS:
        states=1+45+(845-45)*order
        memory.append(dict(order=order,states=states,float64_state_vector_bytes=8*states,
            full3988_float64_state_plane_bytes=8*3988*states,emission_cells=3988*states))
    verify()
    save(HERE/'results.json',dict(synthetic=rows,quadrature_rules=diagnostics,metadata_bound=bound,memory=memory,
        bank_float64_state_array_bytes=position.nbytes+velocity.nbytes,elapsed_seconds=time.monotonic()-begun,
        ledger=dict(analytic_marginals=27,synthetic_quadrature_marginals=162,quadrature_rules=6,
            metadata_bank_cell_arithmetic=len(numbers)*(len(nodes)-1),localization_objectives=0,
            propagations=0,predictor_calls=0,fits=0,measured_CFO_reads=0,original_state_reads=0,station_reference_reads=0),
        source_freeze_sha256=sha(HERE/'source_freeze.json'),qualification='Accuracy/cost evidence only; no continuous-timing population model approved'))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['freeze','run']);args=parser.parse_args()
    if args.action=='freeze':freeze()
    else:run()
