"""Matched curved-model block prediction for graph recovery candidates.

Graph selection, satellite IDs and previous prior choices are fixed conditioning
assumptions. This tests transfer to other families, not independent identity.
"""
import argparse,hashlib,sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import numpy as np
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from include_curved_family_annotations import configuration
from annotate_track_predictively import fit_training
from leo.analysis.research.grouped_prediction import replay_split
from ds23_frequency_events import attach_event_predictive
from investigate_ds23_0268_remaining_tracks import family_frequency
from phase_reference_checks import reference_domain
from audit_explicit_phase_endpoint import exact_gate_replay
from prototype_dsx01_continuous_position import latlon
from stress_joint_attachment import supervise


def masks(old,train,held,target_slice,slices):
    control=np.asarray(old,bool)&np.asarray(train,bool);control[target_slice]=False
    addition=control.copy();addition[target_slice]=train[target_slice]
    for sl in slices:
        if 0<control[sl].sum()<4:control[sl]=False
        if 0<addition[sl].sum()<4:addition[sl]=False
    old_held=np.asarray(old,bool)&np.asarray(held,bool);old_held[target_slice]=False
    if (control&held).any() or (addition&held).any():raise ValueError('training/held overlap')
    return control,addition,old_held


def one(args):
    inv=read(args.inventory);d=context(inv);base,_=d['problems']['c0'];trial=read(args.trial/'target_0.json')
    if len(trial['target_entries'])!=1:raise ValueError('single target required')
    target=trial['target_entries'][0];annotation=read(args.annotation/'result.json')
    fold=next(f for f in annotation['folds'] if f['seed']==args.seed);split=fold['split']
    train,held=replay_split(base.flat_times,split);sl=base.slices[target['row']]
    control,addition,old_held=masks(d['keep'],train,held,sl,base.slices)
    if addition[sl].sum()<8 or held[sl].sum()<4:raise ValueError('insufficient target support')
    node,_=configuration(d['node'],d['keep'],base.slices,[target])
    args.output.mkdir(parents=True,exist_ok=False)
    write(args.output/'protocol.json',dict(job=inv['job'],target=target,seed=args.seed,split=split,
        training_noise_hz=150,training_powers='unit',same_candidate_node_and_alias_in_control_and_target=True,
        target_values_excluded_from_control=True,predictive_rows_used=False,
        frozen_graph_identities_and_prior_choices=True,independent_identity_validation=False,
        start=[0,0],region_width_km=25,phase_rounds=5,iterations=48,GPS_used=False,future_TLE=False,
        source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.inventory,args.trial/'target_0.json',args.annotation/'result.json')}))
    rows=[]
    for arm in ('c0','fitted_c'):
        for role,use in (('control',control),('target',addition)):
            p,x,meta=fit_training(d,node,use,arm);attach_event_predictive(p,[],np.ones(len(d['powers'])))
            c=p.calculate(x);approx,_=p.conditional_frequency(x);phase=p.state(x)['phases'];predictions=[];unavailable=[]
            for k,(row,i,ss) in enumerate(zip(p.rows,p.members,p.slices,strict=True)):
                is_target=k==target['row'];pick=held[ss] if is_target else old_held[ss]
                if not pick.any():continue
                t=p.scan.tracks[i];j=row['candidate_index'];times=t['times'][pick]
                domain=reference_domain(p.sky['time_s'],times,np.zeros(len(times),int),[phase[j]],padding_s=0)
                if not domain['in_domain']:unavailable.append(dict(component=t['key'],domain=domain));continue
                f,_=family_frequency(p,x,j,times=times)
                residual=c['conditional_residual_hz'][ss][pick]-p.q[ss][pick]*(f-approx[ss][pick])
                predictions.append(dict(component=t['key'],norad=row['candidate_norad'],target=is_target,
                    same_family=j==target['candidate_index'],train_points=int(use[ss].sum()),times_s=times,
                    observation_ids=np.asarray(t['observation_ids'])[pick],residual_hz=residual,
                    RMS_hz=float(np.sqrt(np.mean(residual**2)))))
            p.explicit_phase_family=target['candidate_index']
            try:audit=exact_gate_replay(p,x,[])
            except ValueError as exc:
                # Exact replay must fail explicitly; never report convergence
                # as a substitute for unavailable exact geometry.
                audit=dict(all_pass=False,unavailable_reason=str(exc))
            result=dict(arm=arm,role=role,**meta,endpoint_latlon=latlon(x),exact_training_gates=audit,
                qualified=bool(audit['all_pass'] and meta['final_phase_change_s']<=.01 and not unavailable),
                held_predictions=predictions,unavailable_held=unavailable)
            rows.append(result);write(args.output/(arm+'-'+role+'.json'),result)
            print(inv['job']['label'],args.seed,arm,role,'qualified',result['qualified'],flush=True)
    write(args.output/'result.json',dict(job=inv['job'],target=target,seed=args.seed,split=split,rows=rows,
        conditional_model_validation=True,no_accepted_associations=True))


def run(args):
    protocol=read(args.batch/'protocol.json');audit=read(args.audit);jobs=[]
    for j in protocol['jobs']:
        rr=[r for r in audit['rows'] if r['track_id']==j['track_id']]
        if len(rr)!=4 or not all(r['all_pass'] and r['phase_converged'] and not r['incumbent_ownership_changes'] and not r['control_ownership_changes'] for r in rr):continue
        source=args.queue/j['track_id'];ann=read(source/'result.json')
        for fold in ann['folds']:jobs.append(dict(j,seed=fold['seed'],annotation=str(source)))
    if len(jobs)>12 or not 1<=args.workers<=4:raise ValueError('bounded to twelve folds and four workers')
    args.output.mkdir(parents=True,exist_ok=False)
    write(args.output/'protocol.json',dict(jobs=jobs,selection='all exact-orbit and ownership verified candidates; no GPS selection',
        workers=args.workers,seconds_per_job=360,source_batch=str(args.batch),audit_sha256=hashlib.sha256(args.audit.read_bytes()).hexdigest()))
    def work(j):
        name=j['track_id']+'-'+str(j['seed']);cmd=[sys.executable,__file__,'one','--inventory',j['inventory'],
            '--trial',str(args.batch/j['track_id']),'--annotation',j['annotation'],'--seed',str(j['seed']),'--output',str(args.output/name)]
        row=dict(track_id=j['track_id'],scan=j['label'],seed=j['seed'],command=cmd,**supervise(cmd,args.output/(name+'.log'),360))
        write(args.output/(name+'-terminal.json'),row);return row
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for f in as_completed([pool.submit(work,j) for j in jobs]):print(f.result(),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['run','one'])
    for name in ('inventory','trial','annotation','output','batch','queue','audit'):p.add_argument('--'+name,type=Path,required=name=='output')
    p.add_argument('--seed',type=int);p.add_argument('--workers',type=int,default=4)
    a=p.parse_args();run(a) if a.mode=='run' else one(a)
