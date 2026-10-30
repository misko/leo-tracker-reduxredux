"""RF-feasible continuation of a causal new-family predictive likelihood."""
import argparse,hashlib
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write,memberships
from diagnose_all_large_tracks import context
from predictive_new_family import NewFamily,resolution_audit
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import cached,summary
from probe_algo03_feasible_recovery import gate_slacks
from ds23_feasible_position import feasible_fit
from phase_reference_checks import phase_refresh
from algo02_scan import pair_passes


def require_qualified_control(control,audit):
    rows={r['arm']:r for r in audit['rows'] if r['role']=='control'}
    if not control['paired_valid'] or set(rows)!={'c0','fitted_c'} or not all(r['verified'] for r in rows.values()):
        raise ValueError('both control arms require qualified exact RF/owner replay')


def margin_slacks(slacks,margin):
    """Sensitivity constraint only; never relax the original residual gates."""
    if not np.isfinite(margin) or not 0 <= margin < 1:
        raise ValueError('gate margin must be finite and in [0, 1)')
    return np.asarray(slacks,float)-margin


def run(args):
    margin=args.gate_margin; margin_slacks([0.],margin)
    source=args.source;pr=read(source/'protocol.json');control=read(source/'control.json');audit=read(source/'exact_owner_replay.json')
    require_qualified_control(control,audit)
    inv=read(args.study/'all-large-track-recovery'/pr['job']['job_id']/'inventory.json');d=context(inv);out=args.output;out.mkdir(parents=True,exist_ok=False)
    for validation in pr.get('inactive_fragment_sources',[]):
        from inactive_graph_fragment import validated_inactive_context
        d,_=validated_inactive_context(d,inv,Path(validation))
    family=NewFamily(d['scan'],pr['targets'],d['model'],phase_step=pr['phase_step_s'],allow_uncalibrated_label=pr.get('uncalibrated_label',False),
        integrate_orbit_uncertainty=pr['family_prior']['integrate_orbit_uncertainty'],integrate_receiver_uncertainty=pr['family_prior']['integrate_receiver_uncertainty'])
    protocol=dict(pr,optimizer='RF-feasible SLSQP continuation',start='matched exact-RF-qualified regional control',maxiter=48,phase_rounds=5,
        maxfun=None,source_regional_maxfun=pr.get('maxfun'),
        normalized_gate_margin=margin,gate_margin_is_sensitivity_not_calibrated_confidence=True,
        control_uses_same_optimizer=True,source_control_archived=True,source_trial=str(source),target_constraints_checked_at_endpoint=True,
        constraints='unchanged incumbent curved and predictive RF slacks; no GPS; final exact orbit replay required',
        source_hashes={str(source/name):hashlib.sha256((source/name).read_bytes()).hexdigest() for name in ('protocol.json','control.json','new_family.json','exact_owner_replay.json')})
    write(out/'protocol.json',protocol);write(out/'regional_control.json',control)
    for role,include in [('control',False),('new_family',True)]:
        pair={}
        for arm in ('c0','fitted_c'):
            base=control['arms'][arm];x=np.array(base['endpoint_east_north_km']);reference=np.array(base['phase_reference']);history=[]
            for epoch in range(5):
                kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
                p=make_event_problem(d['scan'],d['node'],d['keep'],arm,reference,d['powers'],d['means'],d['model'],[],**kw)
                attach_event_predictive(p,d['entries'],d['powers']);cached(p)
                def objective(z):return p.calculate(z)['negative_twice_elbo']+(family.evaluate(p,z,d['powers'],d['entries']) if include else 0.)
                before=float(objective(x))
                fit=feasible_fit(objective,lambda z:margin_slacks(list(gate_slacks(p,z,d['entries']).values()),margin),x,p.lower,p.upper,iterations=48)
                x=np.array(fit['parameters']);reference,check=phase_refresh(p.state(x)['phases'][p.labels],reference)
                history.append(dict(epoch=epoch,endpoint_east_north_km=x,objective_before=before,objective=fit['score'],fit=fit,
                    success=bool(fit['feasible']),message='best RF-feasible visited point; solver status recorded separately',**check))
            from inactive_graph_fragment import original_graph_view
            row=summary(p,x,d['entries']);_,_,ids,_=memberships(original_graph_view(p,pr.get('original_graph_count',len(p.scan.tracks))),x,d['entries']);old=set(inv['policy'][arm]['proposed_associated_ids'])
            if include:
                detail=family.evaluate(p,x,d['powers'],d['entries'],details=True);row['family']=detail
                row['incumbent_objective']=row['negative_twice_elbo'];row['negative_twice_elbo']+=detail['negative_twice_log_density'];row['linear_gates']+=detail['gates']
                for target in pr['targets']:
                    if ids.intersection(target['observation_ids']):raise ValueError('target duplicates retained observations')
                    ids.update(target['observation_ids'])
                row['phase_resolution_audit']=resolution_audit(family,p,x,d['powers'],d['entries'],d['model'])
            endpoint_slacks=gate_slacks(p,x,d['entries'])
            row.update(incumbent_gate_slacks=endpoint_slacks,normalized_gate_margin=margin,
                endpoint_margin_satisfied=bool(min(endpoint_slacks.values())>=margin),
                history=history,final_phase_change_s=check['phase_change_s'],proposed_associated_ids=sorted(ids),added_points=len(ids-old),lost_points=len(old-ids))
            pair[arm]=row
            print(inv['job']['label'],role,arm,'feasible',fit['feasible'],flush=True)
        valid=pair_passes(pair,include_linear=True) and all(v['lost_points']==0 and v['history'][-1]['fit']['feasible'] and v['endpoint_margin_satisfied'] for v in pair.values())
        if include:valid=valid and all(v['family']['phase_boundary_mass']<.01 and v['phase_resolution_audit']['local_agreement'] for v in pair.values())
        write(out/(role+'.json'),dict(job=inv['job'],arms=pair,baseline=inv['policy'],paired_valid=valid,target_entries=pr['targets'] if include else [],
            no_production_change=True,receiver_calibration_from_target=False,shared_predictive_uncertainty=True,phase_resolution_checked=include,
            continuation_not_independent_regional_rerun=True,matched_feasible_control=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','source','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--gate-margin',type=float,default=0.,help='Nonnegative normalized incumbent slack for a matched sensitivity trial')
    run(p.parse_args())
