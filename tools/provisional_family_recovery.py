"""Conditional whole-family confirmation of recovery; no GPS or new RF inputs."""
import argparse
import copy
import hashlib
from pathlib import Path
import time
import numpy as np

from debug_fast_graph_unassociated import read,write
from benchmark_graph_covariance import load_case,baseline_pair,support_recovery
from combined_family_reentry import ARMS,build,fit_pair,select_width


def confirmation(folds):
    """Two distinct paired witnesses and positive aggregate held evidence."""
    complete=[f for f in folds if f.get('valid')]
    if len({f['norad'] for f in complete})!=len(complete):
        raise ValueError('a satellite family may vote only once')
    if any(not np.isfinite(f['gains'][a]) for f in complete for a in ARMS):
        raise ValueError('finite paired predictive scores required')
    witnesses=[f['norad'] for f in complete if all(f['gains'][a]>0 for a in ARMS)]
    gains={a:sum(f['gains'][a] for f in complete) for a in ARMS}
    accepted=len(complete)>=2 and len(witnesses)>=2 and all(v>0 for v in gains.values())
    return dict(accepted=accepted,valid_folds=len(complete),witness_families=witnesses,aggregate_gain=gains)


def without_family(d,norad,causal_means):
    """Remove every curved and predictive appearance, on both receivers."""
    p,_=d['problems']['c0'];keep=d['keep'].copy();means=np.asarray(d['means']).copy()
    for row,sl in zip(p.rows,p.slices):
        if row['candidate_norad']==norad:
            keep[sl]=False;local=p.labels.index(row['candidate_index']);means[local]=causal_means[local]
    entries=[e for e in d['entries'] if e['norad']!=norad]
    return dict(d,keep=keep,means=means,entries=entries)


def witnesses(d):
    p,_=d['problems']['c0'];families={}
    for k,(row,i,sl) in enumerate(zip(p.rows,p.members,p.slices)):
        t=d['scan'].tracks[i]
        if not p.keep[sl].all() or len(t['times'])<20 or np.ptp(t['times'])<24:continue
        families.setdefault(row['candidate_norad'],[]).append(dict(track_index=i,component=t['key'],
            candidate_index=row['candidate_index'],norad=row['candidate_norad'],alias=int(p.alias[k]),
            points=len(t['times']),observation_ids=t['observation_ids']))
    return sorted(families.items(),key=lambda item:(-sum(e['points'] for e in item[1]),item[0]))[:3]


def reconstitute(d,pair,target,sigma,restore):
    p,_=d['problems']['c0'];keep=d['keep'].copy()
    if restore:keep[p.slices[target]]=True
    problems={}
    for arm,r in pair.items():
        q=build(d,keep,arm,np.asarray(r['phase_reference']),target,sigma);x=np.asarray(r['endpoint_east_north_km'])
        assert abs(q.calculate(x)['negative_twice_elbo']-r['negative_twice_elbo'])<1e-5
        problems[arm]=(q,x)
    return dict(d,keep=keep,problems=problems)


def predict(d,extras):
    from probe_high_channel_correlated_noise import prediction_geometry,noise_diagnostics
    from correlated_curve_prediction import gaussian
    records={}
    model=dict(white_hz=d['scan'].radio_sigma_hz,amplitude_hz=0.,timescale_s=1.)
    for arm,(p,x) in d['problems'].items():
        evaluate,view,_,order,_=prediction_geometry(p,[],d['powers'],extras,model)
        _,raw,cov,geometry=evaluate(x)
        prediction=gaussian(raw[order],cov[np.ix_(order,order)])
        records[arm]=dict(objective=prediction['objective'],quadratic=prediction['quadratic'],
            logdet=prediction['logdet'],points=len(raw),noise=noise_diagnostics(prediction['whitened'],view.flat_times[order]),
            minimum_elevation_deg=float(geometry['elevation'].min()),times_s=view.flat_times[order],
            residual_hz=raw[order],sigma_hz=np.sqrt(np.diag(cov))[order])
    return records


def run(args):
    from algo02_scan import pair_passes
    from investigate_ds23_adaptive_failures import phase_widths
    from probe_ds23_causal_phase_mean import forecast_phase_mean
    started=time.monotonic();out=args.output;out.mkdir(parents=True,exist_ok=False)
    source=read(args.study/args.case/'result.json')
    if source['status']!='accepted':
        write(out/'result.json',dict(case=args.case,status='no_accepted_reentry',decisions={k:False for k in ('preconstraint','witness','combined')},folds=[]));return
    d=load_case(args.root,args.case);d,baseline,_=support_recovery(d,baseline_pair(d));target=source['proposal']['row']
    # Reproduce saved preceding evidence before deriving any new diagnostics.
    for arm in ARMS:
        assert set(baseline[arm]['proposed_associated_ids'])==set(source['support'][arm]['proposed_associated_ids'])
        assert np.linalg.norm(np.array(baseline[arm]['endpoint_east_north_km'])-source['support'][arm]['endpoint_east_north_km'])<1e-5
    old=read(args.study/args.case/'unconstrained.json')
    preconstraint=all(next(g for g in old[a]['gates']['tracks'] if g['component']==source['proposal']['component'])['compatible'] for a in ARMS)
    result=dict(case=args.case,status='running',preconstraint_target_pass=preconstraint,
        decisions=dict(preconstraint=preconstraint,witness=False,combined=False),folds=[],
        provisional_observation_ids=d['scan'].tracks[d['problems']['c0'][0].members[target]]['observation_ids'])
    write(out/'fallback.json',result)
    p,_=d['problems']['c0'];_,receipts=phase_widths(d['scan'],p.labels)
    causal=np.asarray(forecast_phase_mean(receipts,d['model']['shrinkage']))
    for norad,extras in witnesses(d):
        fold=without_family(d,norad,causal)
        removed_ids={o for e in extras for o in e['observation_ids']}
        training_ids={o for i,sl in zip(p.members,p.slices) for o,use in zip(d['scan'].tracks[i]['observation_ids'],fold['keep'][sl]) if use}
        training_ids.update(o for e in fold['entries'] for o in e['observation_ids'])
        assert not removed_ids.intersection(training_ids)
        # Both position fits start at box center, and never see held values.
        before=fit_pair(fold,target,300,restore=False)
        prior_view=reconstitute(fold,before,target,300,False)
        selected=select_width(prior_view,target)  # Re-select inside the fold.
        after=fit_pair(fold,target,selected['selected_sigma_hz'],restore=True)
        after_view=reconstitute(fold,after,target,selected['selected_sigma_hz'],True)
        predictions=dict(before=predict(prior_view,extras),after=predict(after_view,extras))
        valid=pair_passes(before,include_linear=True) and pair_passes(after,include_linear=True)
        valid=valid and all(predictions[m][a]['minimum_elevation_deg']>=0 for m in predictions for a in ARMS)
        gains={a:predictions['before'][a]['objective']-predictions['after'][a]['objective'] for a in ARMS}
        record=dict(norad=norad,valid=valid,gains=gains,held_points=len(removed_ids),
            held_components=[e['component'] for e in extras],before=before,after=after,
            prior_selection=selected,predictions=predictions,held_training_overlap=0)
        write(out/(str(norad)+'.json'),record)
        result['folds'].append(dict(norad=norad,valid=valid,gains=gains,held_points=len(removed_ids)))
        print(args.case,norad,valid,gains,flush=True)
    check=confirmation(result['folds']);result.update(status='complete',confirmation=check,seconds=time.monotonic()-started)
    result['decisions'].update(witness=check['accepted'],combined=preconstraint and check['accepted'])
    write(out/'result.json',result)


def freeze(args):
    args.output.mkdir(parents=True,exist_ok=False);old=read(args.study/'protocol.json')
    write(args.output/'protocol.json',dict(cases=sorted(old['primary_cases']+old['remaining_cases']),
        source_study=str(args.study),root=str(args.root),source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        preconstraint='restored target must pass existing unconstrained gates in both arms; all original final gates remain required',
        witness='top 3 retained families by total complete curved points, at least 20 points and 24s per component; deterministic NORAD tie break',
        confirmation='at least 2 distinct valid folds improve whole-held-family predictive density in both arms; aggregate gain positive in both arms',
        valid_fold='before and after pass all existing curved/predictive gates and phase convergence; held satellite above horizon in both',
        independence='remove held family across RX/channels and predictive entries; restore its causal phase mean; refit both positions from center; select width anew within fold',
        budgets=dict(phase_rounds=5,iterations_per_round=48,workers=3,per_scan_timeout_s=360),
        scope='conditional on fixed graph, initial identities, prior baseline selection and cached measurement scales; not blind acquisition/identity validation',
        GPS_in_inference=False,postscan_TLE=False,production_changed=False,
        evaluation='same 24 development scans; no independent fast cohort with compatible completed baselines was available in the inspected roots',
        provisional='only nominated graph target IDs are provisional; post-fit-only additions from a blocked position are not counted'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['freeze','case'])
    for name in ('root','study','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--case');a=p.parse_args();freeze(a) if a.mode=='freeze' else run(a)
