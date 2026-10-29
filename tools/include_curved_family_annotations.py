"""Matched original-model single/combined recovery of separately nominated curves."""
import argparse
import copy
import hashlib
from pathlib import Path
import time
import numpy as np
from debug_fast_graph_unassociated import read,write,memberships
from diagnose_all_large_tracks import context
from leo.analysis.research.grouped_prediction import identity_consensus
from annotate_track_predictively import prior_means
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import cached,summary
from investigate_dsx01_localization_failures import fit
from algo02_scan import pair_passes


def configuration(node,keep,slices,targets):
    """Atomically restore target rows; preserve all other labels and memberships."""
    result=copy.deepcopy(node);mask=np.array(keep,bool,copy=True);seen=set()
    for t in targets:
        k=t['row']
        if k in seen:raise ValueError('target row repeated')
        seen.add(k);row=result['seed']['rows'][k]
        if row['component']!=t['component']:raise ValueError('target row/component mismatch')
        row.update(candidate_index=t['candidate_index'],candidate_norad=t['norad'])
        result['aliases'][k]=t['alias'];mask[slices[k]]=True
    return result,mask


def fit_variants(targets,joint_only=False):
    if not targets:raise ValueError('at least one target required')
    if joint_only:
        if len(targets)<2:raise ValueError('joint-only requires at least two targets')
        return [('control',[]),('combined',targets)]
    variants=[('control',[])]+[(f'target_{k}',[t]) for k,t in enumerate(targets)]
    if len(targets)>1:variants.append(('combined',targets))
    return variants


def run(args):
    began=time.monotonic();out=args.output;out.mkdir(parents=True,exist_ok=False);inv=read(args.inventory);d=context(inv);base,_=d['problems']['c0']
    targets=[];receipts=[]
    for folder in args.validation:
        r=read(folder/'result.json');a=identity_consensus(r['folds'],score_name=r.get('identity_score_name','joint'))
        if r['job']['job_id']!=inv['job']['job_id'] or a['status']!='conditionally_supported_identity':raise ValueError('supported same-scan validation required')
        k=next(k for k,row in enumerate(base.rows) if row['component']==r['component']);i=base.members[k];t=d['scan'].tracks[i]
        if i not in d['scan'].curved:raise ValueError('target lacks active curved classification')
        aliases={p['alias'] for f in r['folds'] for p in f['proposals'] if p['norad']==a['norad']}
        if len(aliases)!=1:raise ValueError('target alias changes across partitions')
        j=int(np.flatnonzero(d['scan'].norads==a['norad'])[0]);sl=base.slices[k]
        targets.append(dict(row=k,track_id=r['track_id'],component=t['key'],candidate_index=j,norad=a['norad'],alias=next(iter(aliases)),
            track_index=i,points=len(t['times']),original_candidate=base.rows[k]['candidate_norad'],original_kept_points=int(d['keep'][sl].sum()),
            original_alias=int(base.alias[k]),receiver=t['receiver'],channel=t['channel'],time_start_s=float(t['times'].min()),time_end_s=float(t['times'].max())))
        receipts.append(dict(source=str(folder),annotation=a))
    if len({t['norad'] for t in targets})!=1:raise ValueError('one satellite family required')
    configuration(d['node'],d['keep'],base.slices,targets)
    write(out/'protocol.json',dict(job=inv['job'],targets=targets,annotations=receipts,original_noise_weights_and_receiver_priors=True,
        orbital_policy='original support rule; family has one shared phase and supported three-mode physical correction',
        curved_targets_calibrate_receiver=True,noncurved_targets_rejected=True,phase_rounds=5,iterations=48,start=[0,0],box_width_km=25,
        GPS_used=False,future_TLE=False,identities_and_aliases_frozen_after_individual_randomized_nomination=True,
        no_pruning_or_residual_gate_relaxation=True,combined_is_not_independent_identity_validation=True,
        joint_only=getattr(args,'joint_only',False)))
    variants=fit_variants(targets,getattr(args,'joint_only',False))
    for name,extras in variants:
        node,keep=configuration(d['node'],d['keep'],base.slices,extras);means,new_prior_receipts=prior_means(d,node);pair={}
        for arm in ('c0','fitted_c'):
            reference=np.zeros(len(means));x=np.zeros(2);history=[]
            for _ in range(5):
                kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
                p=make_event_problem(d['scan'],node,keep,arm,reference,d['powers'],means,d['model'],[],**kw)
                attach_event_predictive(p,d['entries'],d['powers']);cached(p);f=fit(p,x,iterations=48);x=np.asarray(f['parameters'])
                phase=np.clip(p.state(x)['phases'][p.labels],-15,15);delta=float(np.max(abs(phase-reference)));reference=phase
                history.append(dict(fit=f,phase_change_s=delta))
            row=summary(p,x,d['entries']);_,_,ids,_=memberships(p,x,d['entries']);old=set(inv['policy'][arm]['proposed_associated_ids'])
            calc=p.calculate(x);diagnostics=[]
            for t in extras:
                k=t['row'];i=p.members[k];sl=p.slices[k];track=d['scan'].tracks[i];raw=calc['conditional_residual_hz'][sl]
                diagnostics.append(dict(component=t['component'],norad=t['norad'],times_s=track['times'],CFO_hz=track['values'],
                    predicted_CFO_hz=track['values']-raw,residual_hz=raw,original_kept_mask=d['keep'][sl],
                    gate=next(g for g in row['gates']['tracks'] if g['component']==t['component'])))
            row.update(history=history,final_phase_change_s=delta,proposed_associated_ids=sorted(ids),added_points=len(ids-old),lost_points=len(old-ids),
                targets=diagnostics,new_prior_receipts=new_prior_receipts,active_orbit_families=[int(d['scan'].norads[j]) for j in p.supported])
            pair[arm]=row
        valid=pair_passes(pair,include_linear=True) and all(v['lost_points']==0 for v in pair.values())
        write(out/(name+'.json'),dict(job=inv['job'],arms=pair,paired_valid=valid,target_entries=extras,no_production_change=True,seconds=time.monotonic()-began))
        print(inv['job']['label'],name,'valid',valid,'seconds',round(time.monotonic()-began,1),flush=True)
    if len(targets)==1:
        source=out/'target_0.json';write(out/'combined.json',read(source))
        write(out/'single_combined_reuse.json',dict(source='target_0.json',source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
              reason='Single-target combined configuration is identical; reuse exact completed fit',independent_fit=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['inventory','output']:p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--validation',type=Path,nargs='+',required=True);p.add_argument('--joint-only',action='store_true');run(p.parse_args())
