"""Random-block bidirectional prediction between a new curve and its family.

Refit receiver/position on other families only. Compare held-family prediction
with and without target training blocks under one shared causal phase/orbit and
one shared receiver covariance. No target enters calibration equations.
"""
import argparse,copy,hashlib,time
from pathlib import Path
import numpy as np
from scipy.linalg import cho_solve
from scipy.special import logsumexp
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from annotate_track_predictively import fit_training
from annotate_predictive_only import calibration_covariance
from predictive_new_family import NewFamily
from leo.analysis.research.predictive_track import receiver_design,mixture_prediction
from leo.analysis.research.predictive_track import gaussian_log_density
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from leo.analysis.research.grouped_prediction import replay_split
from annotation_partition_plan import require_distinct_annotation
from prototype_dsx01_continuous_position import latlon


def prediction_masks(train,held,target):
    train,held,target=(np.asarray(a,bool) for a in (train,held,target))
    if train.ndim!=1 or train.shape!=held.shape or train.shape!=target.shape or np.any(train&held):
        raise ValueError('matching disjoint randomized train and held masks required')
    return {
        'family_to_target':(train&~target,held&target),
        'target_to_target':(train&target,held&target),
        'combined_to_target':(train,held&target),
        'family_to_family':(train&~target,held&~target),
        'combined_to_family':(train,held&~target),
    }


def bias_only_projection(y,means,covs,lp,family_train,target_train,target_held,bias_sigma=300.):
    """Expose only the target constant-bias update; diagnostic, not a density.

    Family phase weights and shared means depend only on incumbent training
    observations. The target may estimate its own already-declared constant
    bias. Shared latent means are never shifted by target values here.
    """
    y=np.asarray(y);a=np.asarray(family_train,bool);b=np.asarray(target_train,bool);h=np.asarray(target_held,bool)
    if not (a.shape==b.shape==h.shape==y.shape) or np.any(a&b) or np.any((a|b)&h) or not b.any() or not h.any():
        raise ValueError('disjoint family training, target training and target held sets required')
    select=b|h;is_train=b[select];is_held=h[select];predictions=[];weights=[];biases=[]
    for mean,cov,prior in zip(means,covs,lp,strict=True):
        mu=mean[select].copy();variance=cov[np.ix_(select,select)].copy();logweight=prior
        if a.any():
            cc=cov[np.ix_(a,a)];cross=cov[np.ix_(select,a)];root=np.linalg.cholesky(cc);res=y[a]-mean[a]
            mu+=cross@cho_solve((root,True),res);variance-=cross@cho_solve((root,True),cross.T)
            logweight+=gaussian_log_density(res,cc)
        train_cov=variance[np.ix_(is_train,is_train)];root=np.linalg.cholesky((train_cov+train_cov.T)/2)
        delta=float(bias_sigma**2*np.sum(cho_solve((root,True),y[b]-mu[is_train])))
        predictions.append(mu[is_held]+delta);biases.append(delta);weights.append(logweight)
    weights=np.exp(np.asarray(weights)-logsumexp(weights));prediction=weights@np.asarray(predictions);residual=y[h]-prediction
    return dict(held_indices=np.flatnonzero(h),held_mean_hz=prediction,held_residual_hz=residual,
        rms_hz=float(np.sqrt(np.mean(residual**2))),bias_hz=float(weights@biases),
        target_changes_shared_mean_or_phase_weights=False,diagnostic_not_a_predictive_density=True)


def family_inputs(d,p,targets):
    labels={t['candidate_index'] for t in targets}
    if len(labels)!=1:raise ValueError('one challenged family required')
    j=next(iter(labels));scan=copy.copy(d['scan']);scan.tracks=list(scan.tracks);scan.rx_basis=list(scan.rx_basis)
    entries=[];keep=d['keep'].copy();target_ids={o for t in targets for o in t['observation_ids']};occupied=set()
    def add(i,alias,mask,role):
        track=d['scan'].tracks[i];ids=[o for o,k in zip(track['observation_ids'],mask,strict=True) if k]
        if not ids:return
        if occupied.intersection(ids):raise ValueError('family observations duplicate')
        occupied.update(ids)
        scan.tracks[i]=dict(track,times=np.asarray(track['times'])[mask],values=np.asarray(track['values'])[mask],observation_ids=ids)
        scan.rx_basis[i]=np.asarray(scan.rx_basis[i])[mask]
        entries.append(dict(track_index=i,component=track['key'],candidate_index=j,norad=int(scan.norads[j]),alias=int(alias),points=len(ids),observation_ids=ids,role=role))
    for row,i,sl,alias in zip(p.rows,p.members,p.slices,p.alias,strict=True):
        if row['candidate_index']==j:
            mask=d['keep'][sl].copy();keep[sl]=False
            add(i,alias,mask,'incumbent_calibration')
    for e in d['entries']:
        if e['candidate_index']==j:add(e['track_index'],e['alias'],np.ones(len(d['scan'].tracks[e['track_index']]['times']),bool),'incumbent_predictive')
    if occupied&target_ids:raise ValueError('target already present in incumbent family')
    for e in targets:add(e['track_index'],e['alias'],np.ones(len(d['scan'].tracks[e['track_index']]['times']),bool),'target')
    if len(entries)<2:raise ValueError('independent incumbent family evidence required')
    scan.radio_sigma_hz=150.;scan.fixed_window_noise=dict(extra_parameter_BIC_gain=0,per_observation_noise_sigma_hz={})
    return scan,entries,keep


def joint_mixture(family,p,x):
    c,cov=calibration_covariance(p,x);rows=[]
    for t,e in zip(family.tracks,family.entries,strict=True):
        u=receiver_design(t['times'],t['rf_hz'],t['receiver'],t['channel'],family.scan.rx_basis[e['track_index']],fitted_c=p.fitted_c)
        h=np.zeros((len(t['times']),len(c['coefficient'])));h[:,:u.shape[1]]=u;rows.append(h)
    h=np.concatenate(rows);f,e=paired_phase_frequency(family.bank,family.grid_times,family.grid_labels,family.phases,*latlon(x))
    m=paired_frequency_modes(family.bank,family.modes,family.grid_times,family.grid_labels,family.phases,*latlon(x))
    count=len(family.phases);n=len(family.times);m=m.reshape(count,n,3)*family.q[None,:,None]
    means=h@c['coefficient']+f.reshape(count,n)*family.q
    covariance=family.noise+h@cov@h.T+np.einsum('mni,mki->mnk',m,m)
    lp=family.logprior.copy();lp[e.reshape(count,n).min(axis=1)<0]=-np.inf
    return means,covariance,lp


def run(args):
    started=time.monotonic();out=args.output;out.mkdir(parents=True,exist_ok=False);hashes={}
    def load(path):hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();return read(path)
    pr=load(args.trial/'protocol.json');validation=load(args.validation/'result.json');vp=load(args.validation/'protocol.json');require_distinct_annotation(validation,vp)
    if len(pr['targets'])!=1:raise ValueError('one independently annotated target per family challenge required')
    target=pr['targets'][0]
    if (validation['annotation']['status']!='conditionally_supported_identity' or validation['annotation']['norad']!=target['norad']
            or vp['target']['track_index']!=target['track_index'] or set(vp['target']['observation_ids'])!=set(target['observation_ids'])):
        raise ValueError('validation does not match the complete target and challenged satellite')
    inv=load(args.study/'all-large-track-recovery'/pr['job']['job_id']/'inventory.json');d=context(inv);p0,_=d['problems']['c0']
    scan,entries,keep=family_inputs(d,p0,pr['targets']);family=NewFamily(scan,entries,d['model'],phase_step=args.phase_step,allow_uncalibrated_label=True)
    is_target=np.concatenate([np.full(e['points'],e['role']=='target') for e in entries]);target_ids={o for e in entries if e['role']=='target' for o in e['observation_ids']}
    if target_ids!={o for t in pr['targets'] for o in t['observation_ids']}:raise ValueError('target point scope changed')
    write(out/'protocol.json',dict(job=pr['job'],entries=entries,source_trial=str(args.trial),validation=str(args.validation),
        source_hashes=hashes,phase_step_s=args.phase_step,fixed_noise_hz=150,random_scanwide_block_s=12,guards_s=2,
        family_excluded_from_receiver_and_position_training=True,all_predictive_rows_excluded_from_calibration=True,
        no_GPS=True,causal_only=True,regional_start=[0,0],box_width_km=25,matched_c_arms=True,
        fixed_aliases_from_saved_conditional_annotation=True,conditional_on_frozen_graph_and_other_family_identities=True,
        target_training_can_condition_latent_predictive_distribution=True,calibration_mean_never_updated_by_target=True,
        phase_prior=family.receipt,acceptance_changes=False))
    folds=[];signatures=[]
    for f in validation['folds']:
        train0,_=replay_split(p0.flat_times,f['split']);train,held=replay_split(family.times,f['split']);masks=prediction_masks(train,held,is_target)
        signatures.append(tuple(np.flatnonzero(held&is_target)));fold=dict(seed=f['seed'],split=f['split'],arms={})
        if (held&is_target).sum()<4 or (train&is_target).sum()<8:raise ValueError('insufficient target partition')
        for arm in ('c0','fitted_c'):
            p,x,meta=fit_training(d,d['node'],keep&train0,arm)
            if meta['final_phase_change_s']>.01 or meta['phase_reference_check']['phase_outside_reference_window']:raise ValueError('training phase refresh failed')
            means,cov,lp=joint_mixture(family,p,x);scores={}
            for name,(a,b) in masks.items():
                if not b.any():raise ValueError('empty held family evidence')
                scores[name]=dict(train_indices=np.flatnonzero(a),held_indices=np.flatnonzero(b),**mixture_prediction(family.values,means,cov,lp,a,b))
            bias_projection=bias_only_projection(family.values,means,cov,lp,train&~is_target,train&is_target,held&is_target)
            # Composite diagnostics by physical track; never sum as joint evidence.
            per_track=[]
            for e,sl in zip(entries,family.slices,strict=True):
                if e['role']=='target':continue
                b=np.zeros(len(held),bool);b[sl]=held[sl]
                if not b.any():continue
                pair={name:mixture_prediction(family.values,means,cov,lp,a,b) for name,a in [('family',train&~is_target),('combined',train)]}
                per_track.append(dict(component=e['component'],held_indices=np.flatnonzero(b),scores=pair))
            fold['arms'][arm]=dict(training=meta,scores=scores,per_incumbent_track=per_track,bias_only_projection=bias_projection)
            write(out/f"{f['seed']}-{arm}.json",fold['arms'][arm])
            print(f['seed'],arm,'target held RMS',round(scores['family_to_target']['rms_hz'],1),round(scores['combined_to_target']['rms_hz'],1),
                  'held family density gain',round(scores['family_to_family']['negative_twice_log_density']-scores['combined_to_family']['negative_twice_log_density'],2),'seconds',round(time.monotonic()-started,1),flush=True)
        folds.append(fold);write(out/f"seed-{f['seed']}.json",fold)
    if len(set(signatures))!=3:raise ValueError('repeated target held set')
    write(out/'result.json',dict(job=pr['job'],entries=entries,times_s=family.times,values_hz=family.values,folds=folds,
        target_mask=is_target,three_distinct_target_holdouts=True,seconds=time.monotonic()-started,no_accepted_associations=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','trial','validation','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--phase-step',type=float,default=.1);run(p.parse_args())
