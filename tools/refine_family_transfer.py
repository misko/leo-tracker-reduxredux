"""Grid convergence checks at saved family-transfer endpoints; no position refit."""
import argparse
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from ds23_frequency_events import make_event_problem
from probe_ds23_frequency_events import cached
from predictive_new_family import NewFamily
from validate_family_position_transfer import validation_inputs,held_entries


def run(args):
    args.output.mkdir(parents=True,exist_ok=False);pr=read(args.input/'protocol.json');result=read(args.input/'result.json')
    previous_scores={}
    if args.previous_grid:
        prior=read(args.previous_grid/'result.json')
        if prior['source']!=str(args.input):raise ValueError('previous grid belongs to another transfer run')
        previous_scores={(r['fold'],r['variant'],r['arm'],r['norad']):r for r in prior['rows']}
    inv=read(args.study/'all-large-track-recovery'/pr['job']['job_id']/'inventory.json');d=context(inv);base,_=d['problems']['c0']
    labels=np.array(base.labels)[base.flat_labels];scan,held_scan,powers,factory=validation_inputs(d);target=NewFamily(scan,pr['targets'],d['model']);rows=[]
    write(args.output/'protocol.json',dict(input=str(args.input),phase_steps=[.1,*args.phase_steps],previous_grid=str(args.previous_grid) if args.previous_grid else None,absolute_score_tolerance=.01,position_refitted=False,GPS_used=False))
    for fold in result['folds']:
        train=d['keep']&np.isin(labels,fold['split']['training_families']);held=d['keep']&np.isin(labels,fold['split']['held_families']);entries=held_entries(base,held_scan,held)
        for variant,pair in fold['variants'].items():
            for arm,row in pair.items():
                def build(ref):return cached(make_event_problem(scan,d['node'],train,arm,ref,powers,d['means'],d['model'],[],base_problem_factory=factory))
                if 'phase_reference' in row:reference=np.array(row['phase_reference'])
                else:
                    reference=np.zeros(len(d['means']))
                    for previous_step in row['history'][:-1]:
                        probe=build(reference);reference=np.clip(probe.state(np.array(previous_step['x']))['phases'][probe.labels],-15,15)
                p=build(reference);x=np.array(row['endpoint_east_north_km']);c=p.calculate(x)
                value=c['negative_twice_elbo']+float(np.sum(np.minimum(0,c['elevation'][p.keep])**2)/4)
                if variant=='plus_target':value+=target.evaluate(p,x,powers,[])
                if not np.isclose(value,row['history'][-1]['objective'],atol=1e-5,rtol=0):raise ValueError('saved training objective replay mismatch')
                for old in row['held_families']:
                    key=(fold['split']['fold'],variant,arm,old['norad']);saved=previous_scores.get(key)
                    if saved and saved['converged']:
                        rows.append(saved);continue
                    j=old['candidate_index'];steps=list(saved['steps']) if saved else [dict(step_s=.1,score=old['negative_twice_log_density'])]
                    for step in args.phase_steps:
                        if not 0<step<steps[-1]['step_s']:raise ValueError('phase steps must decrease and be positive')
                        predictor=NewFamily(held_scan,entries[j],d['model'],phase_step=step,allow_uncalibrated_label=True)
                        score=predictor.evaluate(p,x,powers,[]);change=score-steps[-1]['score'];steps.append(dict(step_s=step,score=score,change=change))
                        if abs(change)<=.01:break
                    rows.append(dict(fold=fold['split']['fold'],variant=variant,arm=arm,norad=old['norad'],points=old['points'],steps=steps,
                        converged=abs(steps[-1]['change'])<=.01,score=steps[-1]['score']))
                write(args.output/f"fold-{fold['split']['fold']}-{variant}-{arm}.json",[r for r in rows if r['fold']==fold['split']['fold'] and r['variant']==variant and r['arm']==arm])
                print(pr['job']['label'],fold['split']['fold'],variant,arm,'done',flush=True)
    write(args.output/'result.json',dict(job=pr['job'],rows=rows,source=str(args.input),position_refitted=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['study','input','output']:p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--phase-steps',type=float,nargs='+',default=[.05,.025])
    p.add_argument('--previous-grid',type=Path)
    run(p.parse_args())
