"""Reconstruct nomination endpoints and inspect phase clipping with exact means."""
import argparse,copy
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from annotate_track_predictively import training_factory,prior_means
from ds23_frequency_events import make_event_problem
from investigate_ds23_0268_remaining_tracks import family_frequency
from leo.analysis.research.grouped_prediction import replay_split,identity_consensus
from phase_reference_checks import phase_refresh,reference_domain


def run(args):
    results=[];annotations=[]
    for folder in args.annotations:
        r=read(folder/'result.json');pr=read(folder/'protocol.json');job=pr['job']
        inv=read(args.inventories/job['job_id']/'inventory.json');d=context(inv);base,_=d['problems']['c0']
        k=next(k for k,q in enumerate(base.rows) if q['component']==r['component']);i=base.members[k];sl=base.slices[k]
        vote=identity_consensus(r['folds'],score_name=r.get('identity_score_name','joint'))
        corrected_folds=copy.deepcopy(r['folds'])
        for fold in corrected_folds:
            train,held=replay_split(base.flat_times,fold['split']);keep=d['keep']&train;keep[sl]=train[sl]
            for proposal in fold['proposals']:
                node=copy.deepcopy(d['node']);j=proposal['candidate_index'];node['seed']['rows'][k].update(candidate_index=j,candidate_norad=proposal['norad']);node['aliases'][k]=proposal['alias']
                means,_=prior_means(d,node);factory=training_factory(d);power=np.ones(len(d['powers']))
                for arm,v in proposal['arms'].items():
                    reference=np.zeros(len(means))
                    for step in v['history']:
                        p=make_event_problem(d['scan'],node,keep,arm,reference,power,means,d['model'],[],base_problem_factory=factory)
                        x=np.asarray(step['endpoint']);phase=p.state(x)['phases'][p.labels];reference=np.clip(phase,-15,15)
                    c=p.calculate(x);delta=c['negative_twice_elbo']-v['training_objective']
                    if abs(delta)>1e-5:raise ValueError('annotation endpoint replay mismatch')
                    t=p.scan.tracks[i];approx,_=p.conditional_frequency(x);linear=c['conditional_residual_hz'][sl]
                    target_phase=float(p.state(x)['phases'][j]);ref=float(p.reference[p.labels.index(j)])
                    domain=reference_domain(p.sky['time_s'],t['times'],np.zeros(len(t['times']),int),[target_phase],padding_s=0.)
                    if domain['in_domain']:
                        f,e=family_frequency(p,x,j,times=t['times']);difference=p.q[sl]*(f-approx[sl]);exact=linear-difference
                    else:exact=None
                    target_held=held[sl];target_train=keep[sl];rms=lambda y,m:float(np.sqrt(np.mean(y[m]**2)))
                    _,check=phase_refresh(p.state(x)['phases'][p.labels],p.reference)
                    mismatches=[dict(norad=int(p.scan.norads[label]),phase_s=float(value),reference_s=float(anchor),target=label==j)
                        for label,value,anchor in zip(p.labels,p.state(x)['phases'][p.labels],p.reference,strict=True) if abs(value-anchor)>.01]
                    results.append(dict(scan=job['label'],track_id=r['track_id'],component=r['component'],seed=fold['seed'],arm=arm,norad=proposal['norad'],
                        nominated=proposal['norad']==vote['norad'],objective_replay_difference=delta,
                        phase_s=target_phase,reference_s=ref,unclipped_reference_change_s=abs(target_phase-ref),
                        recorded_final_phase_change_s=v['final_phase_change_s'],phase_outside_reference_window=abs(target_phase)>15,
                        maximum_unclipped_phase_change_s=check['phase_change_s'],
                        phase_reference_mismatches=mismatches,exact_orbit_domain=domain,exact_orbit_available=domain['in_domain'],
                        maximum_linearization_error_hz=float(np.max(abs(difference))) if exact is not None else None,
                        training_linear_RMS_hz=rms(linear,target_train),training_exact_RMS_hz=rms(exact,target_train) if exact is not None else None,
                        held_linear_RMS_hz=rms(linear,target_held),held_exact_RMS_hz=rms(exact,target_held) if exact is not None else None,
                        exact_minimum_elevation_deg=float(e.min()) if exact is not None else None,times_s=t['times'],training_mask=target_train,held_mask=target_held,
                        linear_residual_hz=linear,exact_residual_hz=exact,
                        no_reoptimization=True,diagnostic_not_reranked=True))
                    v['final_phase_change_s']=check['phase_change_s']
        annotations.append(dict(scan=job['label'],track_id=r['track_id'],original=vote,
            corrected=identity_consensus(corrected_folds,score_name=r.get('identity_score_name','joint')),
            only_convergence_metadata_corrected=True,held_scores_not_reranked=True))
        print(job['label'],'annotation phase replay complete',flush=True)
    write(args.output,dict(rows=results,annotations=annotations,no_acceptance_changes=True,all_original_nominated_candidates_replayed=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--annotations',type=Path,nargs='+',required=True)
    p.add_argument('--inventories',type=Path,required=True);p.add_argument('--output',type=Path,required=True);run(p.parse_args())
