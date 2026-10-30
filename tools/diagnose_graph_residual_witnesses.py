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


def run(args):
    inv=read(args.inventory);d=context(inv);base,_=d['problems']['c0'];saved=read(args.source/'target_0.json')
    if len(saved['target_entries'])!=1:raise ValueError('one target required')
    target=saved['target_entries'][0];node,keep=configuration(d['node'],d['keep'],base.slices,[target]);means,_=prior_means(d,node)
    results=[]
    for arm,v in saved['arms'].items():
        kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
        p=make_event_problem(d['scan'],node,keep,arm,np.asarray(v['phase_reference']),d['powers'],means,d['model'],[],**kw)
        attach_event_predictive(p,d['entries'],d['powers']);cached(p);x=np.asarray(v['endpoint_east_north_km']);c=p.calculate(x)
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
        _,check=phase_refresh(phase[p.labels],p.reference,limit_s=30)
        results.append(dict(arm=arm,objective_replay_difference=difference,phase_reference_check=check,
            unavailable_exact_curves=unavailable,all_active_curves=tracks,**summarize(tracks,target['component'])))
    paths=[args.inventory,args.source/'protocol.json',args.source/'target_0.json']
    write(args.output,dict(job=inv['job'],target=target,results=results,source=str(args.source),
        source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        causal_only=True,no_position_optimization=True,full_fit_residual_diagnostic_not_holdout=True))
    print(inv['job']['label'],'residual witness diagnostic complete',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','inventory','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
