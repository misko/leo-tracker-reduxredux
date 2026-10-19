"""Reuse exact completed proposal fits after the bounded large-case timeout."""

import copy
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
import numpy as np
import probe_ds23_joint_family_search as search
from probe_ds23_history_calibrated_phase import OUT as LEARNED
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha
from run_algo01_ds23_sample import final_scan
from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_algo01_0217_improvements import changed_node

CONTEXT=None


def initialize_worker():
    global CONTEXT
    case='DS23-0202';scan=final_scan(case);node=read(SOURCE/case/'result.json')['final_node']
    learned=read(LEARNED/(case+'.json'));keep=np.array(learned['results']['mean_and_distribution']['mask'],bool)
    powers=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
    CONTEXT=(scan,node,keep,powers,learned['hyperparameters_from_pre_RF_TLE_only'])


def compute_missing(changes):
    scan,node,keep,powers,model=CONTEXT;candidate=changed_node(scan,node,changes)
    p=problem(scan,candidate,'c0',keep);_,receipt=phase_widths(scan,p.labels)
    means=forecast_phase_mean(receipt,model['shrinkage'])
    result=search.proposal_refit(scan,candidate,keep,powers,means,model,2,12)
    return node_key(candidate),result


def node_key(node):
    return tuple((r['candidate_index'],a) for r,a in zip(node['seed']['rows'],node['aliases'],strict=True))


def run():
    case='DS23-0202';directory=search.OUT;started=time.monotonic()
    # Let the first bounded completion run write its final attempt receipt.
    while True:
        path=directory/'completion_attempts.json'
        attempts=read(path) if path.exists() else []
        matching=[r for r in attempts if r['case']==case and r['method']=='joint']
        if matching:break
        if time.monotonic()-started>540:raise TimeoutError('bounded completion run did not report')
        time.sleep(1)
    if matching[-1]['code']==0:
        print('large-case completion succeeded; no resumption necessary',flush=True);return
    path=directory/(case+'_partial.json');partial=read(path)
    assert partial['source_sha256']==sha(ROOT/'tools/probe_ds23_joint_family_search.py')
    assert partial['proposal_rounds']==2 and partial['proposal_steps']==12
    checkpoint=directory/(case+'_resume_checkpoint.json');write(checkpoint,partial)
    original=read(SOURCE/case/'result.json')['final_node'];cache={}
    for entry in partial['singles']+partial['joint']:
        node=copy.deepcopy(original)
        for c in entry['changes']:
            node['seed']['rows'][c['row_index']]['candidate_index']=c['candidate_index'];node['aliases'][c['row_index']]=c['alias']
        cache[node_key(node)]=entry['record']
    missing=[]
    for changes in search.joint_operations(partial['singles']):
        node=copy.deepcopy(original)
        for c in changes:
            node['seed']['rows'][c['row_index']]['candidate_index']=c['candidate_index'];node['aliases'][c['row_index']]=c['alias']
        if node_key(node) not in cache:missing.append(changes)
    print('precompute missing joint proposals with two numerical workers',len(missing),flush=True)
    precomputed=0
    with ProcessPoolExecutor(max_workers=2,initializer=initialize_worker) as pool:
        futures=[pool.submit(compute_missing,c) for c in missing]
        for future in as_completed(futures):
            key,result=future.result();cache[key]=result;precomputed+=1
            if precomputed%12==0:print('precomputed',precomputed,'of',len(missing),flush=True)
    original_fit=search.proposal_refit;hits=0;computed=0
    def cached_fit(scan,node,keep,powers,means,model,rounds,steps):
        nonlocal hits,computed
        assert rounds==2 and steps==12
        key=node_key(node)
        if key in cache:
            record=copy.deepcopy(cache[key]);assert record['active_points']==int(np.asarray(keep).sum())
            hits+=1;return record
        computed+=1;return original_fit(scan,node,keep,powers,means,model,rounds,steps)
    search.proposal_refit=cached_fit
    search.run(case,proposal_rounds=2,proposal_steps=12)
    record=read(directory/(case+'.json'));record['resume_receipt']=dict(exact_completed_proposals_reused=hits,
        new_proposals_computed=computed,parallel_precomputed=precomputed,numerical_workers=2,checkpoint_sha256=sha(checkpoint),
        inference_source_sha256=sha(ROOT/'tools/probe_ds23_joint_family_search.py'),
        learned_input_sha256=sha(LEARNED/(case+'.json')),resume_driver_sha256=sha(Path(__file__)),
        parameters_masks_aliases_noise_and_priors_unchanged=True)
    write(directory/(case+'.json'),record)
    execution=read(directory/'execution.json')
    write(directory/'before_resume_execution.json',execution)
    execution=[r for r in execution if r['case']!=case]+[dict(case=case,method='joint',code=0,
        completed_by_checkpoint_reuse=True,seconds=time.monotonic()-started)]
    write(directory/'execution.json',execution)
    print('completed after cache reuse',hits,computed,flush=True)


if __name__=='__main__':run()
