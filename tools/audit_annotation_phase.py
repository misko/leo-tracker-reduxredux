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
from phase_reference_checks import phase_refresh


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
                    t=p.scan.tracks[i];f,e=family_frequency(p,x,j,times=t['times']);approx,_=p.conditional_frequency(x)
                    difference=p.q[sl]*(f-approx[sl]);linear=c['conditional_residual_hz'][sl];exact=linear-difference
                    target_phase=float(p.state(x)['phases'][j]);ref=float(p.reference[p.labels.index(j)])
                    target_held=held[sl];target_train=keep[sl];rms=lambda y,m:float(np.sqrt(np.mean(y[m]**2)))
                    _,check=phase_refresh(p.state(x)['phases'][p.labels],p.reference)
                    results.append(dict(scan=job['label'],track_id=r['track_id'],component=r['component'],seed=fold['seed'],arm=arm,norad=proposal['norad'],
                        nominated=proposal['norad']==vote['norad'],objective_replay_difference=delta,
                        phase_s=target_phase,reference_s=ref,unclipped_reference_change_s=abs(target_phase-ref),
                        recorded_final_phase_change_s=v['final_phase_change_s'],phase_outside_reference_window=abs(target_phase)>15,
                        maximum_unclipped_phase_change_s=check['phase_change_s'],
                        maximum_linearization_error_hz=float(np.max(abs(difference))),
                        training_linear_RMS_hz=rms(linear,target_train),training_exact_RMS_hz=rms(exact,target_train),
                        held_linear_RMS_hz=rms(linear,target_held),held_exact_RMS_hz=rms(exact,target_held),
                        exact_minimum_elevation_deg=float(e.min()),times_s=t['times'],training_mask=target_train,held_mask=target_held,
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
