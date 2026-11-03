"""Historical multi-revision phase targets, causal at the current scan cutoff.

Later revisions describe older historical events only. Labels are unavailable
until their last reference publication. They remain correlated orbit proxies,
not true ephemerides. No RF, satellite nominations or observer input is used.
"""

import hashlib
import numpy as np
from scipy.optimize import minimize_scalar
from sgp4.api import Satrec

from learn_ds23_causal_phase_forecast import transition,distribution_cost
from ds23_causal_phase_location import location_feature,KINDS
from leo.sky.frames import julian_day_from_utc_ns


def reference_id(norad,entry):
    digest=hashlib.sha256('\n'.join(entry['lines']).encode()).hexdigest()
    return str(norad)+'/'+digest


def build_rows(history):
    cutoff=history['cutoff_utc_ns'];rows=[];rejected={}
    def reject(key):rejected[key]=rejected.get(key,0)+1
    for number,versions in history['past_versions'].items():
        if any(max(v['epoch'],v['collected_utc_ns'])>cutoff for v in versions):
            raise ValueError('post-scan element or collection in historical consensus')
        satellites=[Satrec.twoline2rv(*v['lines']) for v in versions]
        for k in range(2,len(versions)-2):
            a,b=versions[k-2:k];refs=versions[k:k+3]
            if any(x['epoch']>=y['epoch'] or x['collected_utc_ns']>y['collected_utc_ns']
                   for x,y in zip(versions[k-2:k+2],versions[k-1:k+3],strict=True)):
                reject('nonincreasing_reference_sequence');continue
            base=transition(a,b,refs[0])
            if base is None:reject('unsupported_original_transition');continue
            target=refs[0]['collected_utc_ns'];jd,fr=julian_day_from_utc_ns(np.array([target]))
            states=[satellites[j].sgp4(float(jd[0]),float(fr[0])) for j in [k-1,k,k+1,k+2]]
            if any(s[0] for s in states):reject('reference_propagation_error');continue
            nominal=np.asarray(states[0][1]);velocity=np.asarray(states[0][2]);norm=float(velocity@velocity)
            phase=np.asarray([float((np.asarray(s[1])-nominal)@velocity/norm) for s in states[1:]])
            if abs(phase[0]-base['next_innovation_s'])>1e-9:raise ValueError('historical next-revision target changed')
            rows.append(dict(base,norad=int(number),target_utc_ns=target,
                label_available_utc_ns=refs[-1]['collected_utc_ns'],reference_phase_s=phase,
                consensus_phase_s=float(np.median(phase)),panel_a_phase_s=float(np.mean(phase[[0,2]])),
                panel_b_phase_s=float(phase[1]),reference_ids=[reference_id(number,v) for v in refs],
                reference_epochs_ns=[v['epoch'] for v in refs],reference_collections_ns=[v['collected_utc_ns'] for v in refs]))
    return rows,rejected


def temporal_split(rows,cutoff,fraction=.7,*,boundary_ns=None):
    if not rows:return dict(boundary_ns=cutoff,training=[],future=[],disjoint_future=[])
    publications=sorted({int(r['label_available_utc_ns']) for r in rows})
    boundary=publications[max(0,int(fraction*len(publications))-1)] if boundary_ns is None else int(boundary_ns)
    train=[r for r in rows if r['label_available_utc_ns']<=boundary and r['norad']%5!=0]
    # Future issue time, not just future label availability, avoids forecasting
    # events which already happened before the training model was available.
    future=[r for r in rows if r['target_utc_ns']>boundary and r['label_available_utc_ns']<=cutoff]
    disjoint=[r for r in future if r['norad']%5==0]
    train_ids={v for r in train for v in r['reference_ids']};test_ids={v for r in future for v in r['reference_ids']}
    if train_ids&test_ids:raise ValueError('reference revision crossed temporal training boundary')
    return dict(boundary_ns=boundary,training=train,future=future,disjoint_future=disjoint)


def balanced_temporal_split(rows,cutoff):
    """Choose a boundary from publication support, without phase outcomes."""
    if not rows:return temporal_split(rows,cutoff)
    candidates=[]
    for boundary in sorted({int(r['label_available_utc_ns']) for r in rows}):
        train=[r for r in rows if r['label_available_utc_ns']<=boundary and r['norad']%5!=0]
        future=[r for r in rows if r['target_utc_ns']>boundary and r['label_available_utc_ns']<=cutoff]
        held=[r for r in future if r['norad']%5==0]
        counts=[len({r['norad'] for r in part}) for part in [train,held]]
        candidates.append(dict(boundary_ns=boundary,minimum_distinct_satellite_support=min(counts),
            minimum_total_row_support=min(len(train),len(future)),training_satellites=counts[0],
            held_future_satellites=counts[1]))
    selected=max(candidates,key=lambda r:(r['minimum_distinct_satellite_support'],r['minimum_total_row_support'],-r['boundary_ns']))
    result=temporal_split(rows,cutoff,boundary_ns=selected['boundary_ns'])
    result['boundary_selection']=dict(selected=selected,candidates=candidates,
        only_publication_issue_times_and_satellite_ids_used=True,no_phase_outcomes_used=True)
    return result


def predict(rows,model,fit):
    sigma=np.asarray([r['predicted_sigma_s'] for r in rows]);age=np.asarray([r['age_s'] for r in rows])
    value=fit['shrinkage']*np.asarray([r['unit_forecast_s'] for r in rows])
    if fit['kind'] is not None:value=value+fit['coefficient']*location_feature(fit['kind'],sigma,age,model['multiplier'])
    limit=np.minimum(15.,3*sigma)
    return np.clip(value,-limit,limit)


def cost(rows,model,fit,target='consensus_phase_s'):
    errors=np.asarray([r[target] for r in rows])-predict(rows,model,fit)
    sigma=np.asarray([r['predicted_sigma_s'] for r in rows])
    return float(distribution_cost(errors,sigma,model['multiplier'],model['nu']).sum())


def fit_mean(rows,model,target,*,kinds=(None,)+KINDS):
    if len(rows)<30:raise ValueError('thirty historical labels required')
    baseline=dict(shrinkage=model['shrinkage'],kind=None,coefficient=0.)
    null=cost(rows,model,baseline,target);choices=[]
    for rho in [0.,.25,.5,.75,1.]:
        for kind in kinds:
            fit=dict(shrinkage=rho,kind=kind,coefficient=0.)
            if kind is not None:
                def objective(b):return cost(rows,model,dict(fit,coefficient=float(b)),target)+b*b
                result=minimize_scalar(objective,bounds=(-3.,3.),method='bounded',options=dict(xatol=1e-7))
                fit['coefficient']=float(result.x)
            value=cost(rows,model,fit,target)
            extra=int(abs(rho-model['shrinkage'])>1e-12)+int(kind is not None)
            penalty=extra*np.log(len(rows))+(2*np.log(25) if extra else 0.)+fit['coefficient']**2
            choices.append(dict(fit,cost=value,criterion=value+penalty,penalty=penalty))
    if not any(abs(c['shrinkage']-model['shrinkage'])<1e-12 and c['kind'] is None for c in choices):
        choices.append(dict(baseline,cost=null,criterion=null,penalty=0.))
    return dict(min(choices,key=lambda x:x['criterion']),choices=choices,target=target,rows=len(rows),
        prior_scale_and_tail_degrees_unchanged=True)


def panel_diagnostics(rows,model):
    if not rows:return dict(count=0,agreement_qualified=False)
    difference=np.asarray([r['panel_a_phase_s']-r['panel_b_phase_s'] for r in rows])
    scale=np.asarray([r['predicted_sigma_s']*model['multiplier'] for r in rows])
    return dict(count=len(rows),median_abs_difference_s=float(np.median(abs(difference))),
        median_abs_standardized_difference=float(np.median(abs(difference)/scale)),
        agreement_qualified=bool(np.median(abs(difference)/scale)<1.),
        reference_panels_use_distinct_revisions_but_are_not_independent_orbit_truth=True)


def runtime_means(receipts,model,fit,fallback):
    fallback=np.asarray(fallback,float);output=fallback.copy();used=[]
    if fallback.shape!=(len(receipts),):raise ValueError('one existing mean per phase receipt required')
    for k,r in enumerate(receipts):
        old,gap=r['old_new_alignment_s'],r['previous_epoch_gap_s']
        if old is None or gap is None or gap<1:continue
        age=r['age_s']+150.
        row=dict(predicted_sigma_s=r['sigma_s'],age_s=age,unit_forecast_s=-np.clip(age/gap,0,2)*old)
        output[k]=predict([row],model,fit)[0];used.append(k)
    return output,used
