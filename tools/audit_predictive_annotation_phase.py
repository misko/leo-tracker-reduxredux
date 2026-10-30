"""Replay predictive-only annotations and separate calibration/target phase errors."""
import argparse,copy,csv,hashlib,sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import numpy as np
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from annotate_track_predictively import training_factory,prior_means
from annotate_predictive_only import prediction_models
from ds23_frequency_events import make_event_problem
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features
from investigate_ds23_0268_remaining_tracks import family_frequency
from leo.analysis.research.grouped_prediction import replay_split,identity_consensus
from leo.analysis.research.predictive_track import mixture_prediction
from leo.analysis.research.retained_track_likelihood import PERIOD
from phase_reference_checks import phase_refresh,reference_domain
from stress_joint_attachment import supervise


def selected(rows,members):
    return [r for r in rows if 'DS24' in r['scopes'] and r['state']=='conditionally_supported_identity'
        and not members[r['track_id']] and not r.get('phase_audit_source')]


def one(args):
    source=read(args.source/'result.json');pr=read(args.source/'protocol.json');job=pr['job']
    inv=read(args.inventories/job['job_id']/'inventory.json');d=context(inv);base,_=d['problems']['c0']
    i=pr['target']['track_index'];track=d['scan'].tracks[i]
    if i in base.members:raise ValueError('this replay is for nonmember predictive-only annotations')
    means,_=prior_means(d,d['node']);factory=training_factory(d);folds=copy.deepcopy(source['folds']);rows=[]
    vote=identity_consensus(folds,score_name='conditional_target')
    for fold in folds:
        train,_=replay_split(base.flat_times,fold['split']);tt,th=replay_split(track['times'],fold['split']);keep=d['keep']&train
        for arm in ('c0','fitted_c'):
            old=fold['proposals'][0]['arms'][arm];reference=np.zeros(len(means))
            for step in old['history']:
                p=make_event_problem(d['scan'],d['node'],keep,arm,reference,np.ones(len(d['powers'])),means,d['model'],[],base_problem_factory=factory)
                x=np.asarray(step['endpoint']);reference=np.clip(p.state(x)['phases'][p.labels],-15,15)
            objective=p.calculate(x)['negative_twice_elbo'];phase=p.state(x)['phases'];_,check=phase_refresh(phase[p.labels],p.reference)
            for proposal in fold['proposals']:
                v=proposal['arms'][arm];j=proposal['candidate_index']
                if abs(objective-v['training_objective'])>1e-5:raise ValueError('training objective does not replay')
                mu,cov,lp,phases,elev,prior=prediction_models(d,p,x,i,j,phase_step=pr['phase_step_s'],uncalibrated_phase_mixture=pr.get('uncalibrated_phase_mixture',False))
                y=track['values']+proposal['alias']*PERIOD;score=mixture_prediction(y,mu,cov,lp,tt,th)
                original=v['scores']['conditional_target'];delta=score['negative_twice_log_density']-original['negative_twice_log_density']
                if abs(delta)>1e-5 or abs(score['rms_hz']-original['rms_hz'])>1e-5:raise ValueError('predictive score does not replay')
                exact_available=True;maximum=0.;exact_score=score;domain=None
                if prior['kind']=='existing_shared_posterior':
                    domain=reference_domain(p.sky['time_s'],track['times'],np.zeros(len(track['times']),int),[phase[j]],padding_s=0)
                    exact_available=domain['in_domain']
                    if exact_available:
                        view,*_=linear_geometry(p,[dict(track_index=i,candidate_index=j,alias=0)]);g=geometry_features(view,x,0.)
                        begin=p.hardware.shape[1]+p.smooth.shape[1];end=begin+len(p.labels)+3*len(p.supported)
                        approximate=view.q*g['intercept']+g['features'][:,begin:end]@p.calculate(x)['coefficient'][begin:end]
                        f,_=family_frequency(p,x,j,times=track['times']);difference=view.q*f-approximate;maximum=float(np.max(abs(difference)))
                        exact_score=mixture_prediction(y,mu+difference,cov,lp,tt,th)
                    else:exact_score=None;maximum=None
                rows.append(dict(scan=job['label'],track_id=source['track_id'],seed=fold['seed'],arm=arm,norad=proposal['norad'],nominated=proposal['norad']==vote['norad'],
                    prior_kind=prior['kind'],objective_replay_difference=objective-v['training_objective'],score_replay_difference=delta,
                    phase_reference_check=check,recorded_phase_change_s=v['final_phase_change_s'],maximum_target_mean_difference_hz=maximum,
                    exact_orbit_available=exact_available,domain=domain,held_original_RMS_hz=score['rms_hz'],
                    held_exact_mean_RMS_hz=exact_score['rms_hz'] if exact_score is not None else None,
                    exact_covariance_recomputed=False,original_exact_phase_mixture=prior['kind']!='existing_shared_posterior'))
                v['final_phase_change_s']=check['phase_change_s']
    write(args.output,dict(job=job,track_id=source['track_id'],rows=rows,original=vote,
        corrected=identity_consensus(folds,score_name='conditional_target'),held_scores_not_reranked=True,no_reoptimization=True,
        source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.source/'result.json',args.source/'protocol.json')}))
    print(job['label'],source['track_id'],'predictive replay complete',flush=True)


def run(args):
    rows=list(csv.DictReader(args.ledger.open()));members={r['track_id']:r['engine_member'] for r in read(args.queue/'protocol.json')['rows']}
    jobs=selected(rows,members)
    if len(jobs)>24 or not 1<=args.workers<=8:raise ValueError('bounded to 24 annotations and eight workers')
    args.output.mkdir(parents=True,exist_ok=False)
    write(args.output/'protocol.json',dict(jobs=jobs,workers=args.workers,seconds_per_job=180,source_ledger=str(args.ledger),
        ledger_sha256=hashlib.sha256(args.ledger.read_bytes()).hexdigest(),no_optimization=True,GPS_used=False))
    def work(j):
        tid=j['track_id'];cmd=[sys.executable,__file__,'one','--source',str(Path(j['annotation_source']).parent),
            '--inventories',str(args.inventories),'--output',str(args.output/(tid+'.json'))]
        result=dict(track_id=tid,scan=j['label'],command=cmd,**supervise(cmd,args.output/(tid+'.log'),180))
        write(args.output/(tid+'-terminal.json'),result);return result
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for f in as_completed([pool.submit(work,j) for j in jobs]):print(f.result(),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['one','run'])
    for name in ('source','inventories','ledger','queue','output'):p.add_argument('--'+name,type=Path,required=name in ('inventories','output'))
    p.add_argument('--workers',type=int,default=8);a=p.parse_args();run(a) if a.mode=='run' else one(a)
