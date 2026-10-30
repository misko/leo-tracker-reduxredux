"""Exact residual context for one saved graph-addition endpoint, both c arms."""
import argparse,hashlib
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from include_curved_family_annotations import configuration
from annotate_track_predictively import prior_means
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import cached
from investigate_ds23_0268_remaining_tracks import family_frequency
from phase_reference_checks import phase_refresh,reference_domain
from cross_curve_residual_witnesses import summarize
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features
from leo.analysis.research.retained_track_likelihood import profile


def run(args):
    inv=read(args.inventory);d=context(inv);base,_=d['problems']['c0'];addition=read(args.source/'target_0.json')
    for validation in read(args.source/'protocol.json').get('inactive_fragment_sources',[]):
        from inactive_graph_fragment import validated_inactive_context
        d,_=validated_inactive_context(d,inv,Path(validation))
    if len(addition['target_entries'])!=1:raise ValueError('one target required')
    target=addition['target_entries'][0]
    shared=getattr(args,'shared_family',False)
    control=getattr(args,'control',False)
    if control and not shared:raise ValueError('control prediction is implemented for shared-family targets')
    role='control' if control else 'target_0';saved=read(args.source/(role+'.json'))
    if shared:
        node,keep,means=d['node'],d['keep'],d['means'];entries=d['entries']+([] if control else [target])
    else:
        node,keep=configuration(d['node'],d['keep'],base.slices,[target]);means,_=prior_means(d,node);entries=d['entries']
    results=[]
    for arm,v in saved['arms'].items():
        kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
        p=make_event_problem(d['scan'],node,keep,arm,np.asarray(v['phase_reference']),d['powers'],means,d['model'],[],**kw)
        attach_event_predictive(p,entries,d['powers']);cached(p);x=np.asarray(v['endpoint_east_north_km']);c=p.calculate(x)
        difference=c['negative_twice_elbo']-v['negative_twice_elbo']
        if abs(difference)>1e-5:raise ValueError('objective replay mismatch')
        approx,_=p.conditional_frequency(x);phase=p.state(x)['phases'];tracks=[];unavailable=[]
        for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
            active=p.keep[sl]
            if active.sum()<4:continue
            track=p.scan.tracks[i];j=row['candidate_index'];times=track['times'][active]
            domain=reference_domain(p.sky['time_s'],times,np.zeros(len(times),int),[phase[j]],padding_s=0)
            if not domain['in_domain']:unavailable.append(dict(component=track['key'],domain=domain));continue
            f,e=family_frequency(p,x,j,times=times)
            residual=c['conditional_residual_hz'][sl][active]-p.q[sl][active]*(f-approx[sl][active])
            tracks.append(dict(component=track['key'],norad=row['candidate_norad'],receiver=track['receiver'],channel=track['channel'],
                rf_hz=track['rf_hz'],times_s=times,residual_hz=residual,minimum_elevation_deg=float(e.min()),
                phase_s=float(phase[j]),phase_reference_s=float(p.reference[p.labels.index(j)]),
                exact_difference_hz=float(np.max(abs(p.q[sl][active]*(f-approx[sl][active]))))))
        diagnostic_entries=entries+([target] if control else [])
        for entry in diagnostic_entries:
            i=entry['track_index'];track=p.scan.tracks[i];j=entry['candidate_index'];times=track['times']
            domain=reference_domain(p.sky['time_s'],times,np.zeros(len(times),int),[phase[j]],padding_s=0)
            if not domain['in_domain']:unavailable.append(dict(component=track['key'],domain=domain));continue
            view,values,*_=linear_geometry(p,[entry]);g=geometry_features(view,x,0.)
            begin=p.hardware.shape[1]+p.smooth.shape[1];end=begin+len(p.labels)+3*len(p.supported)
            f,e=family_frequency(p,x,j,times=times)
            approximate=view.q*g['intercept']+g['features'][:,begin:end]@c['coefficient'][begin:end]
            difference_hz=view.q*f-approximate
            raw=values-view.q*g['intercept']-g['features']@c['coefficient']-difference_hz
            terms=profile(raw,np.zeros(len(raw)),*p.scan.white[i],bias_sigma=300.)
            tracks.append(dict(component=track['key'],norad=entry['norad'],receiver=track['receiver'],channel=track['channel'],
                rf_hz=track['rf_hz'],times_s=times,residual_hz=terms['residual'][0],innovations_hz=terms['innovations'][0],
                minimum_elevation_deg=float(e.min()),phase_s=float(phase[j]),phase_reference_s=float(p.reference[p.labels.index(j)]),
                exact_difference_hz=float(np.max(abs(difference_hz))),predictive_only=True,profile_bias_hz=float(terms['bias'][0])))
        _,check=phase_refresh(phase[p.labels],p.reference,limit_s=30)
        results.append(dict(arm=arm,objective_replay_difference=difference,phase_reference_check=check,
            unavailable_exact_curves=unavailable,all_active_curves=tracks,**summarize(tracks,target['component'])))
    paths=[args.inventory,args.source/'protocol.json',args.source/'target_0.json',args.source/(role+'.json')]
    write(args.output,dict(job=inv['job'],target=target,results=results,source=str(args.source),
        source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        causal_only=True,no_position_optimization=True,shared_predictive_target=shared,target_excluded_from_position=control,
        role=role,full_fit_residual_diagnostic_not_holdout=True))
    print(inv['job']['label'],'residual witness diagnostic complete',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','inventory','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--shared-family',action='store_true',help='Replay an inactive graph target included through its existing shared predictive family')
    p.add_argument('--control',action='store_true',help='Predict target at the no-addition position, excluding it from all likelihoods')
    run(p.parse_args())
