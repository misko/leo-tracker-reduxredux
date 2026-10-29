"""Bounded causal diagnostics of two large wholly unassociated graph curves."""

import argparse
from pathlib import Path
import numpy as np

import debug_fast_graph_unassociated as report
from benchmark_graph_covariance import load_case, baseline_pair, refit

TARGETS={'DS24-0018':'RX2-CH3-T000','DS24-0089':'RX1-CH3-T001'}


def qualifies(pair,baseline):
    from algo02_scan import pair_passes
    return pair_passes(pair,include_linear=True) and all(
        set(baseline[a]['proposed_associated_ids'])<=set(r['proposed_associated_ids']) for a,r in pair.items())


def candidate_screen(p,x,track,norad):
    from investigate_ds23_0268_remaining_tracks import family_frequency,corrected_observation
    from leo.analysis.research.retained_track_likelihood import profile
    from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
    i=next(i for i,t in enumerate(p.scan.tracks) if t['key']==track['key'])
    j=int(np.flatnonzero(p.scan.norads==norad)[0])
    f,e=family_frequency(p,x,j,times=track['times'])
    y=corrected_observation(p,x,i);terms=profile(y,track['rf_hz']/11.5e9*f,*p.scan.white[i])
    noise=batch_noise_screen(terms['innovations'],track['times'])
    return dict(norad=norad,times_s=track['times'],prediction_hz=track['rf_hz']/11.5e9*f,
        corrected_observation_hz=y,residual_hz=terms['residual'][0],rms_hz=terms['rms'][0],
        offset_hz=terms['bias'][0],alias=terms['alias'][0],minimum_elevation_deg=e.min(),
        noise={k:float(v[0]) for k,v in noise.items()})


def run(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False);d=load_case(args.root,args.case)
    p,x=d['problems']['c0'];t=next(t for t in d['scan'].tracks if TARGETS[args.case] in t['key'])
    k=next(k for k,r in enumerate(p.rows) if r['component']==t['key']);j=p.rows[k]['candidate_index']
    summary=dict(case=args.case,target=t,original_row=p.rows[k],keep=p.keep[p.slices[k]],
        baseline=baseline_pair(d),active_orbit_support=j in p.supported,
        nominal_family_members=[dict(row=r,active_points=int(p.keep[sl].sum())) for r,sl in zip(p.rows,p.slices) if r['candidate_index']==j],
        identity_never_assumed=True,causal_catalogue_only=True,arms={})
    for arm,(p,x) in d['problems'].items():
        original=candidate_screen(p,x,t,p.rows[k]['candidate_norad'])
        active=report.screen(p,x,t,np.arange(len(t['times'])),False)
        catalogue=report.screen(p,x,t,np.arange(len(t['times'])),True)
        summary['arms'][arm]=dict(original=original,active=active,catalogue=catalogue)
        print(args.case,arm,'original',original['norad'],original['rms_hz'],original['noise'],flush=True)
        print('active', {k:v for k,v in active.items() if k in ['norad','rms_hz','failed_gates','phase_s','offset_hz','noise']},flush=True)
        print('catalogue', {k:v for k,v in catalogue.items() if k in ['norad','rms_hz','failed_gates','phase_s','offset_hz','noise']},flush=True)
    report.write(out/'diagnostic.json',summary)


def recovery(args):
    from algo02_scan import pair_passes
    out=args.output;out.mkdir(parents=True,exist_ok=False);d=load_case(args.root,args.case)
    p,x=d['problems']['c0'];k=next(k for k,r in enumerate(p.rows) if TARGETS[args.case] in r['component'])
    baseline=baseline_pair(d);keep=d['keep'].copy();keep[p.slices[k]]=True
    trials={}
    for policy in ('nominal','active'):
        pair,problems=refit(d,keep,policy=policy)
        preserves=all(set(baseline[a]['proposed_associated_ids'])<=set(r['proposed_associated_ids']) for a,r in pair.items())
        passed=pair_passes(pair,include_linear=True)
        for arm,(q,z) in problems.items():
            pair[arm]['target_prediction']=candidate_screen(q,z,d['scan'].tracks[p.members[k]],p.rows[k]['candidate_norad'])
        trials[policy]=dict(arms=pair,paired_gates_pass=passed,preserves_original_points=preserves,
                           accepted=passed and preserves)
        print(args.case,policy,'gates',passed,'preserves',preserves,flush=True)
        for arm,r in pair.items():
            print(arm,'endpoint',r['endpoint_east_north_km'],'phase',r['final_phase_change_s'],
                'failed',[(g['component'],g.get('profile_rms_hz'),g.get('conditional_residual_gate'))
                for g in r['gates']['tracks']+r['linear_gates'] if not g['compatible']],flush=True)
    report.write(out/'recovery.json',dict(case=args.case,target=p.rows[k]['component'],baseline=baseline,trials=trials,
        original_candidate_and_alias_preserved=True,additional_points=int(keep.sum()-d['keep'].sum()),
        phase_prior_unchanged=True,no_GPS_in_inference=True,phase_rounds=5,position_steps=48))


def constrained(args):
    from ds23_frequency_events import make_event_problem,attach_event_predictive
    from probe_ds23_frequency_events import cached,summary
    from probe_algo03_feasible_recovery import gate_slacks
    from ds23_feasible_position import feasible_fit
    from algo02_scan import pair_passes
    from probe_ds23_history_calibrated_phase import make_problem
    out=args.output;out.mkdir(parents=True,exist_ok=False);d=load_case(args.root,args.case)
    previous=report.read(args.parent/('bias_ablation.json' if args.constant_sigma!=300 else 'recovery.json'));p,_=d['problems']['c0']
    k=next(k for k,r in enumerate(p.rows) if TARGETS[args.case] in r['component'])
    keep=d['keep'].copy();keep[p.slices[k]]=True;pair={}
    def factory(*a,**kw):
        q=make_problem(*a,**kw);q.constants[:,k]*=args.constant_sigma/300
        return q
    for arm in ('c0','fitted_c'):
        before=previous['arms'][arm] if args.constant_sigma!=300 else previous['trials']['nominal']['arms'][arm]
        x=np.array(before['endpoint_east_north_km']);reference=np.array(before['phase_reference']);history=[]
        for _ in range(5):
            q=make_event_problem(d['scan'],d['node'],keep,arm,reference,d['powers'],d['means'],d['model'],[],base_problem_factory=factory)
            attach_event_predictive(q,d['entries'],d['powers']);cached(q)
            fitted=feasible_fit(lambda z:q.calculate(z)['negative_twice_elbo'],
                lambda z:list(gate_slacks(q,z,d['entries']).values()),x,q.lower,q.upper,iterations=40)
            x=np.array(fitted['parameters']);phase=np.clip(q.state(x)['phases'][q.labels],-15,15)
            history.append(dict(fit=fitted,phase_change_s=float(np.max(abs(phase-reference)))))
            reference=phase
        r=summary(q,x,d['entries']);curved,pred,ids,_=report.memberships(q,x,d['entries'])
        r.update(history=history,final_phase_change_s=history[-1]['phase_change_s'],
            gate_slacks=gate_slacks(q,x,d['entries']),curved_points=len(curved),predictive_points=len(pred),
            proposed_associated_points=len(ids),proposed_associated_ids=sorted(ids),
            target_prediction=candidate_screen(q,x,d['scan'].tracks[p.members[k]],p.rows[k]['candidate_norad']))
        pair[arm]=r
        report.write(out/(arm+'.json'),r)
        print(args.case,arm,'feasible',fitted['feasible'],'minslack',min(r['gate_slacks'].values()),
            'phase',r['final_phase_change_s'],'position',x,flush=True)
    old=baseline_pair(d);preserves=all(set(old[a]['proposed_associated_ids'])<=set(r['proposed_associated_ids']) for a,r in pair.items())
    accepted=pair_passes(pair,include_linear=True) and preserves
    report.write(out/'constrained.json',dict(case=args.case,arms=pair,accepted=accepted,preserves_original_points=preserves,
        unchanged_gates_aliases_candidates=True,new_curve_constant_sigma_hz=args.constant_sigma,phase_rounds=5,position_steps=40,
        start='matched-arm unconstrained recovery endpoints; no GPS'))
    print('Accepted',accepted,flush=True)


def prior_ablation(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False);d=load_case(args.root,args.case)
    baseline=baseline_pair(d);p,_=d['problems']['c0']
    k=next(k for k,r in enumerate(p.rows) if TARGETS[args.case] in r['component'])
    local=p.labels.index(p.rows[k]['candidate_index']);keep=d['keep'].copy();keep[p.slices[k]]=True
    trials={}
    for name,value in [('reflected_mean',-d['means'][local]),('zero_mean',0.)]:
        means=d['means'].copy();means[local]=value
        pair,problems=refit(d,keep,policy='nominal',means=means)
        for arm,(q,x) in problems.items():
            pair[arm]['target_prediction']=candidate_screen(q,x,d['scan'].tracks[p.members[k]],p.rows[k]['candidate_norad'])
        trials[name]=dict(mean_s=value,arms=pair,accepted=qualifies(pair,baseline))
        print(args.case,name,'accepted',trials[name]['accepted'],flush=True)
    report.write(out/'prior_ablation.json',dict(case=args.case,original_mean_s=d['means'][local],
        original_sigma_s=p.phase_sigma[local],target_likelihood_power=d['powers'][k],trials=trials,
        caveat='Mechanism ablations only; not a policy change or new prior selected by GPS',
        same_observations_aliases_candidates_widths_and_budgets=True))


def origin(args):
    from investigate_algo01_ds23_0217 import problem
    from investigate_ds23_adaptive_failures import phase_widths
    from probe_ds23_causal_phase_mean import forecast_phase_mean
    from probe_ds23_history_calibrated_phase import refit as initial_refit
    out=args.output;out.mkdir(parents=True,exist_ok=False);d=load_case(args.root,args.case)
    initial=report.read(args.root/args.case/'result.json');old=report.read(args.root/args.case/'algo02_result.json')
    keep=np.array(initial['final_mask'],bool);node=initial['final_node'];scan=d['scan']
    base=problem(scan,node,'c0',keep);_,receipts=phase_widths(scan,base.labels)
    model=old['hyperparameters_from_pre_RF_TLE_only'];means=forecast_phase_mean(receipts,model['shrinkage'])
    arms={a:initial_refit(scan,node,keep,a,np.array(old['weights']),means,model['multiplier'],model['nu'])
          for a in ('c0','fitted_c')}
    expected=set(old['curved_gate_history'][0]['failed'])
    actual={g['component'] for row in arms.values() for g in row['gates']['tracks'] if not g['compatible']}
    if actual!=expected:raise ValueError('First gate-round replay disagrees with archived failures')
    report.write(out/'origin.json',dict(case=args.case,gate_round_zero=arms,
        initial_target_gates={a:[g for g in row['metrics']['tracks'] if TARGETS[args.case] in g['component']]
          for a,row in initial['arms'].items()},archived_gate_history=old['curved_gate_history'],
        replay_failed_components_match=True))
    print(args.case,'origin gate replay matched',flush=True)


def bias_ablation(args):
    from ds23_frequency_events import make_event_problem,attach_event_predictive
    from probe_ds23_history_calibrated_phase import make_problem
    from probe_ds23_frequency_events import cached,summary
    from investigate_dsx01_localization_failures import fit
    out=args.output;out.mkdir(parents=True,exist_ok=False);d=load_case(args.root,args.case)
    baseline=baseline_pair(d);p,_=d['problems']['c0'];k=next(k for k,r in enumerate(p.rows) if TARGETS[args.case] in r['component'])
    keep=d['keep'].copy();keep[p.slices[k]]=True;pair={}
    def factory(*a,**kw):
        q=make_problem(*a,**kw)
        # Only the newly reentered curve: effective SD 300 -> 1000 Hz.
        q.constants[:,k]*=1000/300
        return q
    for arm in ('c0','fitted_c'):
        x=np.zeros(2);reference=np.zeros(len(d['means']));history=[]
        for _ in range(5):
            q=make_event_problem(d['scan'],d['node'],keep,arm,reference,d['powers'],d['means'],d['model'],[],base_problem_factory=factory)
            attach_event_predictive(q,d['entries'],d['powers']);cached(q)
            fitted=fit(q,x,iterations=48);x=np.asarray(fitted['parameters']);phase=np.clip(q.state(x)['phases'][q.labels],-15,15)
            history.append(dict(fit=fitted,phase_change_s=float(np.max(abs(phase-reference)))));reference=phase
        r=summary(q,x,d['entries']);curved,pred,ids,_=report.memberships(q,x,d['entries'])
        r.update(history=history,final_phase_change_s=history[-1]['phase_change_s'],curved_points=len(curved),
            predictive_points=len(pred),proposed_associated_points=len(ids),proposed_associated_ids=sorted(ids),
            target_prediction=candidate_screen(q,x,d['scan'].tracks[p.members[k]],p.rows[k]['candidate_norad']))
        pair[arm]=r
    report.write(out/'bias_ablation.json',dict(case=args.case,arms=pair,accepted=qualifies(pair,baseline),
        effective_new_curve_bias_sigma_hz=1000,old_curve_priors_unchanged=True,
        caution='Diagnostic prior ablation, not a calibrated general recovery policy'))
    print(args.case,'bias1000 accepted',qualifies(pair,baseline),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--case',choices=list(TARGETS),required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--recover',action='store_true');parser.add_argument('--constrained',action='store_true')
    parser.add_argument('--prior-ablation',action='store_true')
    parser.add_argument('--origin',action='store_true')
    parser.add_argument('--bias-ablation',action='store_true')
    parser.add_argument('--constant-sigma',type=float,default=300)
    parser.add_argument('--parent',type=Path);args=parser.parse_args()
    bias_ablation(args) if args.bias_ablation else origin(args) if args.origin else prior_ablation(args) if args.prior_ablation else constrained(args) if args.constrained else recovery(args) if args.recover else run(args)
