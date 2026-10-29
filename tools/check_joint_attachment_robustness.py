"""Independent-family and starting-position checks for a sealed attachment."""
import argparse
from pathlib import Path
import time
import numpy as np
from debug_fast_graph_unassociated import read,write
from test_joint_high_channel_recovery import context,physical,ARMS
from probe_high_channel_correlated_noise import position_trial,calibrate
from benchmark_graph_covariance import refit
from provisional_family_recovery import witnesses,without_family,predict


def held_prediction(d,held,restore_modes):
    from probe_high_channel_correlated_noise import prediction_geometry
    from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
    from correlated_curve_prediction import gaussian
    result={}
    for a,(p,x) in d['problems'].items():
        fn,view,_,order,_=prediction_geometry(p,[],d['powers'],held,dict(white_hz=p.scan.radio_sigma_hz,amplitude_hz=0.,timescale_s=1.))
        _,raw,cov,g=fn(x)
        if restore_modes[a]:
            assert len({e['candidate_index'] for e in held})==1
            assert held[0]['candidate_index'] not in p.supported
            from prototype_dsx01_continuous_position import latlon
            modes=paired_frequency_modes(view.sky,view.mode_bank,view.flat_times,view.flat_labels,view.reference,*latlon(x))
            design=view.q[:,None]*modes;cov+=design@design.T
        score=gaussian(raw[order],cov[np.ix_(order,order)])
        result[a]=dict(objective=score['objective'],points=len(raw),restored_independent_orbit_prior=restore_modes[a],
            minimum_elevation_deg=float(g['elevation'].min()),residual_hz=raw[order],sigma_hz=np.sqrt(np.diag(cov))[order])
    return result


def main(args):
    began=time.monotonic();args.output.mkdir(parents=True,exist_ok=False)
    d,baseline=context(args.root,args.case,args.source)
    record=read(args.parent/'covariance_physical.json');extras=record['extras'];model=record['model']
    from algo02_scan import pair_passes
    if args.mode=='start':
        d['start']=args.start;pair=position_trial(d,extras,model)
        gates={a:physical(r['target_raw_hz'],r['target_covariance_hz2'],r['target_times_s'],r['target_owners']) for a,r in pair.items()}
        accepted=pair_passes(pair,include_linear=True) and all(v['compatible'] for v in gates.values())
        accepted=accepted and all(set(baseline[a]['proposed_associated_ids'])<=set(pair[a]['proposed_associated_ids']) for a in ARMS)
        result=dict(kind='start',start=args.start,accepted=accepted,arms=pair,physical=gates,
            endpoint_difference_m={a:float(1000*np.linalg.norm(np.asarray(pair[a]['endpoint_east_north_km'])-record['proposal'][a]['endpoint_east_north_km'])) for a in ARMS})
    else:
        from investigate_ds23_adaptive_failures import phase_widths
        from probe_ds23_causal_phase_mean import forecast_phase_mean
        p,_=d['problems']['c0'];_,receipts=phase_widths(d['scan'],p.labels)
        means=forecast_phase_mean(receipts,d['model']['shrinkage'])
        candidates=[item for item in witnesses(d) if item[0]!=record['candidate']]
        if args.index>=len(candidates):
            write(args.output/'result.json',dict(kind='family',status='no_additional_eligible_family',available=[c[0] for c in candidates]));return
        norad,held=candidates[args.index]
        fold=without_family(d,norad,means)
        train_ids={oid for i,sl in zip(p.members,p.slices) for oid,keep in zip(d['scan'].tracks[i]['observation_ids'],fold['keep'][sl]) if keep}
        train_ids.update(oid for e in fold['entries'] for oid in e['observation_ids'])
        held_ids={oid for e in held for oid in e['observation_ids']};assert not held_ids&train_ids
        # Nominal physical priors retain uncertainty for the completely withheld
        # family. This may invalidate old singleton support, reported explicitly.
        policy='active' if args.held_prior_predictive else 'nominal'
        before,problems=refit(fold,fold['keep'],policy=policy)
        fold=dict(fold,problems=problems,support_policy=policy);fold.pop('problem_factory',None)
        targets=read(args.parent/'result.json')['targets']
        excluded=set(read(args.parent/'nomination.json')['candidates'])|{norad}
        calibration=calibrate(fold,targets,sorted(excluded));model=calibration['best_correlated']
        assert not any(r['norad']==norad for r in calibration['rows'])
        after=position_trial(fold,extras,model)
        restore={a:held[0]['candidate_index'] in d['problems'][a][0].supported for a in ARMS}
        before_prediction=held_prediction(fold,held,restore) if args.held_prior_predictive else predict(fold,held)
        # Reconstitute curved calibration at each after endpoint; the new target
        # only changes position, never fits calibration directly.
        from ds23_frequency_events import make_event_problem,attach_event_predictive
        from probe_ds23_frequency_events import cached
        after_problems={}
        for a,r in after.items():
            from functools import partial
            from probe_ds23_history_calibrated_phase import make_problem
            q=make_event_problem(fold['scan'],fold['node'],fold['keep'],a,np.asarray(r['phase_reference']),fold['powers'],fold['means'],fold['model'],[],
                base_problem_factory=partial(make_problem,support_policy=policy))
            attach_event_predictive(q,fold['entries'],fold['powers']);cached(q)
            after_problems[a]=(q,np.asarray(r['endpoint_east_north_km']))
        after_view=dict(fold,problems=after_problems)
        after_prediction=held_prediction(after_view,held,restore) if args.held_prior_predictive else predict(after_view,held)
        result=dict(kind='family',norad=norad,held_points=len(held_ids),held_training_overlap=0,
            valid_training_fits=pair_passes(before,include_linear=True) and pair_passes(after,include_linear=True),
            before=before,after=after,calibration=calibration,
            before_prediction=before_prediction,after_prediction=after_prediction,
            gains={a:before_prediction[a]['objective']-after_prediction[a]['objective'] for a in ARMS},
            held_orbit_prior_predictive_only=args.held_prior_predictive,
            caveat='Conditional fixed target nomination. Held family excluded from all curved/predictive training, restored causal phase and nominal orbital prior. Invalid training fits cannot confirm recovery.')
    result['seconds']=time.monotonic()-began;write(args.output/'result.json',result)
    print({k:v for k,v in result.items() if k in ('kind','start','accepted','endpoint_difference_m','norad','valid_training_fits','gains','seconds')},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('start','family'))
    for name in ('root','source','parent','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--case',required=True);p.add_argument('--index',type=int,default=0)
    p.add_argument('--held-prior-predictive',action='store_true')
    p.add_argument('--start',nargs=2,type=float,default=[0,0]);main(p.parse_args())
