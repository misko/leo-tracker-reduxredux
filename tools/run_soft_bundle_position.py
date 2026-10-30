"""Bounded matched position trial retaining a bundle's satellite ambiguity."""
import argparse,hashlib
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from debug_fast_graph_unassociated import read,write,memberships
from diagnose_all_large_tracks import context
from predictive_graph_bundle import bundle_context
from predictive_label_mixture import LabelMixture,candidate_set
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import cached,summary
from phase_reference_checks import phase_refresh
from leo.analysis.research.predictive_track import phase_resolution_agreement
from audit_explicit_phase_endpoint import exact_gate_replay
from audit_predictive_family_inclusion import owner_changes
from algo02_scan import pair_passes
from inactive_graph_fragment import original_graph_view


def run(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False);inv=read(args.inventory);d=context(inv)
    original_count=len(d['scan'].tracks);r=read(args.validation/'result.json');pr=read(args.validation/'protocol.json');target=pr['target']
    if not r.get('graph_bundle') or len(r['folds'])!=3:raise ValueError('three-fold bundle annotation required')
    source=Path(target['bundle_source'])
    if hashlib.sha256(source.read_bytes()).hexdigest()!=target['bundle_source_sha256']:raise ValueError('bundle source changed')
    d,reconstructed=bundle_context(d,inv,source,r['track_id'])
    for key in ('track_id','track_index','observation_ids','members','member_indices'):
        if target[key]!=reconstructed[key]:raise ValueError('bundle reconstruction differs from annotation')
    candidates,evidence=candidate_set(r['folds']);mixture=LabelMixture(d,target,candidates,args.phase_step)
    sources=[args.inventory,args.validation/'protocol.json',args.validation/'result.json',source]
    write(out/'protocol.json',dict(job=inv['job'],target=target,candidates=candidates,candidate_evidence=evidence,phase_step_s=args.phase_step,
        source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},candidate_margin=20,
        uniform_family_prior=True,uniform_alias_prior_within_family=True,conditional_on_nominated_family_set=True,no_clutter_component=True,
        fixed_RF_selection_before_position=True,GPS_used=False,future_TLE=False,matched_c_arms=True,
        optimizer='Powell',phase_rounds=5,maxiter=48,maxfev=240,original_graph_count=original_count,
        start_east_north_km=[0,0],box_width_km=25,hard_identity_assigned=False,soft_points_counted_as_hard_associations=False,
        compatible_posterior_mass_requirement=.99,no_production_change=True))
    baseline={a:memberships(p,x,d['entries'])[3] for a,(p,x) in d['problems'].items()};all_audits=[];pairs={}
    for role,include in [('control',False),('soft_mixture',True)]:
        pair={}
        for arm in ('c0','fitted_c'):
            x=np.zeros(2);reference=np.zeros(len(d['means']));history=[]
            for _ in range(5):
                kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
                p=make_event_problem(d['scan'],d['node'],d['keep'],arm,reference,d['powers'],d['means'],d['model'],[],**kw)
                attach_event_predictive(p,d['entries'],d['powers']);cached(p)
                def objective(z):
                    c=p.calculate(z);penalty=float(np.sum(np.minimum(0,c['elevation'][p.keep])**2)/4)
                    return c['negative_twice_elbo']+penalty+(mixture.evaluate(p,z,d['powers'],d['entries']) if include else 0.)
                opt=minimize(objective,x,method='Powell',bounds=[(-12.5,12.5)]*2,
                    options=dict(maxiter=48,maxfev=240,ftol=1e-10,xtol=1e-5))
                x=np.asarray(opt.x);reference,check=phase_refresh(p.state(x)['phases'][p.labels],reference)
                history.append(dict(endpoint=x,objective=float(opt.fun),success=bool(opt.success),message=str(opt.message),nfev=int(opt.nfev),**check))
            row=summary(p,x,d['entries']);_,_,ids,owners=memberships(original_graph_view(p,original_count),x,d['entries'])
            if ids.intersection(target['observation_ids']):raise ValueError('ambiguous bundle leaked into hard graph associations')
            row.update(history=history,final_phase_change_s=check['phase_change_s'],proposed_associated_ids=sorted(ids),proposed_owners=owners,
                soft_observation_ids=target['observation_ids'] if include else [],hard_target_association_count=0)
            if include:
                detail=mixture.evaluate(p,x,d['powers'],d['entries'],details=True);exact=mixture.evaluate(p,x,d['powers'],d['entries'],details=True,refine_phase=True)
                row.update(mixture=detail,exact_target_components=exact,incumbent_objective=row['negative_twice_elbo'])
                row['negative_twice_elbo']+=detail['negative_twice_log_density']
                refined=[mixture,LabelMixture(d,target,candidates,args.phase_step/2),LabelMixture(d,target,candidates,args.phase_step/4)]
                offsets=np.array([[0,0],[.025,0],[-.025,0],[0,.025],[0,-.025]])
                scores=[[m.evaluate(p,x+offset,d['powers'],d['entries']) for m in refined] for offset in offsets]
                row['phase_resolution_audit']=dict(phase_resolution_agreement(scores),scores=scores,steps_s=[args.phase_step,args.phase_step/2,args.phase_step/4])
            labels={q['candidate_index'] for q,sl in zip(p.rows,p.slices,strict=True) if p.keep[sl].any()};labels.update(e['candidate_index'] for e in d['entries']);replays=[]
            for j in sorted(labels):
                p.explicit_phase_family=j;replays.append(dict(norad=int(p.scan.norads[j]),**exact_gate_replay(p,x,d['entries'])))
            changes=owner_changes(baseline[arm],owners)
            audited=not changes and all(v['all_pass'] for v in replays) and check['phase_change_s']<=.01
            if include:audited=audited and detail['compatible_mass']>=.99 and exact['compatible_mass']>=.99 and detail['receiver_calibration_change']<=1e-10 and row['phase_resolution_audit']['local_agreement']
            audit=dict(role=role,arm=arm,incumbent_ownership_changes=changes,exact_incumbent_family_replays=replays,verified=bool(audited))
            all_audits.append(audit);pair[arm]=row;write(out/(role+'-'+arm+'.json'),row)
            print(inv['job']['label'],role,arm,'audited',audited,'position',x,flush=True)
        valid=pair_passes(pair,include_linear=True) and all(v['history'][-1]['success'] and v['final_phase_change_s']<=.01 for v in pair.values())
        valid=valid and all(a['verified'] for a in all_audits if a['role']==role)
        pairs[role]=dict(arms=pair,paired_valid=bool(valid));write(out/(role+'.json'),pairs[role])
    write(out/'result.json',dict(job=inv['job'],qualified_soft_research_candidate=all(v['paired_valid'] for v in pairs.values()),
        audits=all_audits,hard_identity_assigned=False,hard_target_association_count=0,conditional_on_candidate_set=True,
        no_clutter_component=True,no_production_change=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('inventory','validation','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--phase-step',type=float,default=.1);run(p.parse_args())
