"""Regional orphan-mixture search only for numerically qualified hypotheses.

The coarse map is an exploratory1024-draw approximation. Final decisions use
two16384-draw integrations, original gates and identical c-arm candidate pools.
No evaluation coordinate or geographic error function is imported.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal

import numpy as np

import probe_ds23_orphan_adaptive as parent
from ds23_orphan_predictive_mixture import OrphanPrediction,orphan_rows
from ds23_orphan_adaptive_importance import AdaptiveOrphans
from probe_ds23_frequency_events import summary
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=parent.OUT/'regional_position'


def existing_node(path,job):
    case,level,index,point,high=job
    saved=read(path)
    if (saved['case']!=case or saved['level']!=level or saved['index']!=index or
        saved['high_accuracy']!=high or not np.array_equal(saved['point'],point) or saved['status']!='complete'):
        raise ValueError('completed grid node does not match the frozen request')
    return dict(case=case,index=index,status='complete',source=str(path),reused_sha256=sha(path))


def fixed(d,arm,x):
    reference=np.zeros(len(d['means']));changes=[]
    for _ in range(5):
        p=parent.context.engine.baseline.build(d,arm,reference)
        phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
        changes.append(float(max(abs(phase-reference))));reference=phase
    saved=summary(p,x,d['entries']);saved.update(final_phase_change_s=changes[-1],phase_changes_s=changes)
    return p,saved


def evaluate(job):
    case,level,index,point,high=job;path=OUT/case/f'level{level}_point{index:03d}.json'
    path.parent.mkdir(exist_ok=True)
    if path.exists():return existing_node(path,job)
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('180s orphan grid node cap')));signal.alarm(180)
    try:
        d=parent.context.engine.current_setup(case);x=np.asarray(point);observations=orphan_rows(d);arms={}
        for arm in ['c0','fitted_c']:
            p,saved=fixed(d,arm,x)
            prediction=OrphanPrediction(p,observations,d['powers'],draw_power=4,bias_sigma_hz=0.)
            oracle=AdaptiveOrphans(prediction,x);proposals=oracle.proposals()
            seeds=parent.SEEDS if high else parent.SEEDS[:1];trials=[]
            for seed in seeds:
                r=oracle.integrate(proposals,power=14 if high else 10,seed=seed,nodes=64,details=high)
                if high:
                    control=oracle.integrate(proposals,power=14,seed=seed,nodes=128)
                    r['quadrature_difference']=abs(r['relative_negative_twice_log_likelihood']-control['relative_negative_twice_log_likelihood'])
                trials.append(r)
            differences=[r['relative_negative_twice_log_likelihood'] for r in trials]
            saved.update(orphan_trials=trials,
                combined_negative_twice_objective=saved['negative_twice_elbo']+float(np.mean(differences)),
                integration_qualified=bool(high and max(differences)-min(differences)<=.5 and
                    all(t['effective_nuisance_draws']>=32 and t['quadrature_difference']<=.05 for t in trials)))
            arms[arm]=saved
        result=dict(case=case,level=level,index=index,point=x,high_accuracy=high,arms=arms,status='complete',
            paired_gates_valid=bool(valid(arms)),phase_valid=all(r['final_phase_change_s']<=.01 for r in arms.values()),
            paired_integration_qualified=all(r['integration_qualified'] for r in arms.values()))
        write(path,result);print(case,level,index,'complete',flush=True)
        return dict(case=case,index=index,status='complete',source=str(path))
    except Exception as exc:
        import traceback
        result=dict(case=case,index=index,status='failed',error=repr(exc),traceback=traceback.format_exc())
        write(path.with_name(path.stem+'_failed.json'),result);return result
    finally:signal.alarm(0)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--workers',type=int,default=12)
    args=parser.parse_args();parent.context.configure();OUT.mkdir(exist_ok=True)
    candidates=read(parent.OUT/'protocol.json')['cases'];qualified=[]
    for case in candidates:
        if all(read(parent.OUT/'refinement16384'/(case+'_'+a+'_bias0_qualification.json'))['qualified'] for a in ['c0','fitted_c']):qualified.append(case)
    protocol=dict(cases=qualified,not_qualified=[c for c in candidates if c not in qualified],
        source_sha256=sha(Path(__file__)),parent_refinement_sha256=sha(parent.OUT/'refinement16384/protocol.json'),
        hypothesis='strict existing-family prediction, no additional fragment constant; all orphan points, shared calibration uncertainty and uniform clutter',
        regional_width_km=25,regional_center=[37.906,-122.545],coarse_axis=[-12,-6,0,6,12],
        refinement_steps_km=[3,1,.25],refinements='3x3 around c0 best phase-valid exploratory score; same grid both c arms',
        exploratory_draws=1024,final_draws=16384,seeds=list(parent.SEEDS),phase_rounds=5,
        final_pool='all9 final-grid points plus both original RF endpoints, same candidate points in both c arms',
        eligibility='both original gates, phase convergence,seed loss agreement<=.5,ESS>=32,64vs128quadrature difference<=.05',
        selection='lowest high-accuracy combined objective per c arm among paired-eligible nodes; require gain>2log2 against all-clutter incumbent in both arms',
        no_GPS_or_following_TLE_or_manual_identity=True,no_new_hard_associations_without_separate_validation=True)
    if (OUT/'protocol.json').exists():
        old=read(OUT/'protocol.json')
        if dict(protocol,source_sha256=old['source_sha256'])!=old:raise ValueError('scientific grid protocol changed')
        if old['source_sha256']!=protocol['source_sha256']:
            archived=OUT/'initial_driver.py'
            if sha(archived)!=old['source_sha256']:raise ValueError('initial driver archive does not match frozen source')
            write(OUT/'orchestration_repair.json',dict(original_driver_sha256=sha(archived),
                current_driver_sha256=protocol['source_sha256'],
                repair='convert serialized source strings to Path before read; reuse exact completed grid requests',
                scientific_protocol_unchanged=True,no_geographic_scoring_or_outcome_used=True))
    else:write(OUT/'protocol.json',protocol)
    execution=[];selections=[]
    for case in qualified:
        center=np.zeros(2);last_points=None
        for level,step in enumerate([6.,3.,1.,.25]):
            if level==0:points=[np.array([a,b]) for a in [-12.,-6.,0.,6.,12.] for b in [-12.,-6.,0.,6.,12.]]
            else:points=[np.clip(center+[a,b],-12.5,12.5) for a in [-step,0.,step] for b in [-step,0.,step]]
            points=list({tuple(v):v for v in points}.values());jobs=[(case,level,k,p,False) for k,p in enumerate(points)]
            with ProcessPoolExecutor(max_workers=args.workers) as pool:rows=list(pool.map(evaluate,jobs))
            execution.extend(rows)
            if any(r['status']!='complete' for r in rows):raise ValueError('grid node failure; no geographic evaluation')
            values=[read(Path(r['source'])) for r in rows];eligible=[r for r in values if r['phase_valid']]
            if not eligible:raise ValueError('no phase-valid coarse grid nodes')
            best=min(eligible,key=lambda r:r['arms']['c0']['combined_negative_twice_objective']);center=np.asarray(best['point'])
            last_points=points
        d=parent.context.engine.current_setup(case)
        points=list({tuple(p):p for p in last_points+[np.asarray(d['arms'][a]['endpoint_east_north_km']) for a in ['c0','fitted_c']]}.values())
        with ProcessPoolExecutor(max_workers=args.workers) as pool:rows=list(pool.map(evaluate,[(case,4,k,p,True) for k,p in enumerate(points)]))
        execution.extend(rows)
        if any(r['status']!='complete' for r in rows):raise ValueError('high-accuracy node failure; no geographic evaluation')
        values=[read(Path(r['source'])) for r in rows]
        eligible=[r for r in values if r['paired_gates_valid'] and r['phase_valid'] and r['paired_integration_qualified']]
        selected={a:min(eligible,key=lambda r:r['arms'][a]['combined_negative_twice_objective']) if eligible else None for a in ['c0','fitted_c']}
        gains={a:d['arms'][a]['negative_twice_elbo']-r['arms'][a]['combined_negative_twice_objective'] if r else None for a,r in selected.items()}
        adopted=bool(eligible and all(g>2*np.log(2) for g in gains.values()))
        record=dict(case=case,adopted=adopted,selected=selected,RF_gain_vs_all_clutter=gains,
            RF_selection_sealed_before_geographic_scoring=True,hard_orphan_association_count_not_claimed=True)
        write(OUT/(case+'_selection.json'),record);selections.append(record)
    write(OUT/'execution.json',dict(rows=execution,all_terminal=True,all_passed=True))
    write(OUT/'selection.json',dict(rows=selections,all_passed=True,RF_selection_sealed_before_geographic_scoring=True))


if __name__=='__main__':main()
