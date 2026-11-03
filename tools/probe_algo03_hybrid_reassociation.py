"""RF-selected family-pattern hybrids, retaining every current observation."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from functools import lru_cache
from pathlib import Path
import time

import numpy as np

import probe_algo03_complete_reassociation as engine
from ds23_predictive_reassociation import family_pattern_product
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_20_algo03_hybrid_reassociation'
PARENT=ROOT/'reports/2026_10_20_algo03_complete_reassociation_v2'


def screen(index):
    scan,_,keep,_,old=engine.context('DS23-0268');model=old['hyperparameters_from_pre_RF_TLE_only']
    node=read(OUT/'all_hypotheses.json')['nodes'][index];powers=np.array(old['weights'])
    labels=sorted({r['candidate_index'] for r in node['seed']['rows']});_,receipts=phase_widths(scan,labels)
    means=forecast_phase_mean(receipts,model['shrinkage']);scores=[]
    for anchor in read(OUT/'screen_request.json')['anchors']:
        ref=np.zeros(len(labels))
        for _ in range(5):
            p=engine.build(scan,node,keep,'c0',ref,powers,means,model)
            phase=np.clip(p.state(anchor)['phases'][p.labels],-15,15)
            change=float(max(abs(phase-ref)));ref=phase
        c=p.calculate(anchor);visibility=float(np.sum(np.maximum(0,-c['elevation'][keep])**2)/4)
        scores.append(dict(anchor=anchor,negative_twice_elbo=c['negative_twice_elbo'],
                           visibility_penalty=visibility,cost=c['negative_twice_elbo']+visibility,
                           phase_change_s=change))
    result=dict(index=index,scores=scores)
    write(OUT/f'screen_{index:03d}.json',result)
    return result


def trial(index):
    # Each worker has its own process/module state. The unchanged full paired
    # engine reads the selected hypothesis list in this explicit experiment.
    engine.OUT=OUT
    return engine.trial(index)


def main():
    if OUT.exists():raise FileExistsError('preserve hybrid reassociation experiment')
    OUT.mkdir();nodes=read(PARENT/'hypotheses.json')['nodes']
    scan,_,keep,_,old=engine.context('DS23-0268')
    active={r['component'] for r in old['policy_arms']['c0']['gates']['tracks']}
    hybrids,receipt=family_pattern_product(nodes,active,maximum=512)
    write(OUT/'all_hypotheses.json',dict(nodes=hybrids,receipt=receipt))
    completed=read(PARENT/'execution.json')['receipts'];best=min(completed,key=lambda r:r['c0_loss'])
    anchor=read(PARENT/f"trial_{best['index']:02d}.json")['arms']['c0']['endpoint_east_north_km']
    write(OUT/'screen_request.json',dict(anchors=[[0.,0.],anchor],
        second_anchor='lowest normalized c0 loss in all parent trials, irrespective of acceptance; RF only',
        anchor_source_trial=best['index'],anchor_source_sha256=sha(PARENT/f"trial_{best['index']:02d}.json"),
        fixed_position_nuisance_phase_rounds=5,maximum_top_candidates_per_anchor=12,
        no_GPS_selection=True,predictive_tracks_excluded_only_from_cheap_proposal_screen=True))
    write(OUT/'protocol.json',dict(case='DS23-0268',source_sha256=sha(Path(__file__)),
        unchanged_engine_sha256=sha(ROOT/'tools/probe_algo03_complete_reassociation.py'),
        helper_sha256=sha(ROOT/'tools/ds23_predictive_reassociation.py'),workers=24,
        all_family_pattern_hypotheses=receipt['hypotheses'],maximum_hypotheses=512,
        shortlist='top12 curved-only fixed-position screens at each of two RF anchors, plus incumbent',
        final_full_data_inputs_unchanged=True,paired_EM_rounds=5,paired_position_steps=48,
        no_GPS_or_postscan_TLE_or_point_removal=True))
    started=time.monotonic();screens=[]
    with ProcessPoolExecutor(max_workers=24) as executor:
        for future in as_completed([executor.submit(screen,i) for i in range(len(hybrids))]):
            screens.append(future.result())
    chosen={0}
    for k in range(2):
        chosen.update(r['index'] for r in sorted(screens,key=lambda r:r['scores'][k]['cost'])[:12])
    chosen=sorted(chosen)
    write(OUT/'hypotheses.json',dict(nodes=[hybrids[i] for i in chosen],hybrid_indices=chosen,
        all240screened=True,no_geographic_error_used_for_shortlist=True))
    protocol=read(OUT/'protocol.json');protocol['hypotheses']=len(chosen);write(OUT/'protocol.json',protocol)
    print('screened',len(hybrids),'full paired finalists',len(chosen),flush=True)
    receipts=[]
    with ProcessPoolExecutor(max_workers=24) as executor:
        for future in as_completed([executor.submit(trial,i) for i in range(len(chosen))]):
            receipts.append(future.result())
    baseline=old['policy_arms']['c0']['negative_twice_elbo'];penalty=2*np.log(len(hybrids)+1)
    qualified=[r for r in receipts if r['valid'] and r['stable']]
    best=min(qualified,key=lambda r:r['c0_loss']) if qualified else None
    accepted=best is not None and baseline-best['c0_loss']>penalty
    write(OUT/'execution.json',dict(receipts=receipts,all_terminal=True,seconds=time.monotonic()-started,
        proposed=len(hybrids),full_finalists=len(chosen),baseline_c0_loss=baseline,
        best_qualified_trial=best,search_penalty=penalty,accepted=bool(accepted)))
    print('complete','best',best,'accepted',accepted,flush=True)


if __name__=='__main__':main()
