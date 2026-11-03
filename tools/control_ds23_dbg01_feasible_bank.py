"""Cold paired fits of the existing DBG01 bank, retaining the valid incumbent."""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

import run_ds23_dbg01_iteration_004 as study
from ds23_family_cavity import unused_student_gap
from probe_ds23_family_cavity_position import fit_configuration,unused_count
from probe_ds23_reentry_family_cavity import audit_baseline
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=study.RAW/'feasible_bank_control'


def choose(trials,incumbent_loss,penalty):
    eligible=[r for r in trials if r['paired_valid']]
    best=min(eligible,key=lambda r:r['arms']['c0']['corrected_selection_loss']) if eligible else None
    gain=incumbent_loss-best['arms']['c0']['corrected_selection_loss'] if best else None
    return best if best is not None and gain>penalty else None,gain


def one(case):
    d=study.engine.current_setup(case);bank=read(study.RAW/case/'DBG01/hypothesis_bank.json')['nodes'];trials=[];checks=[]
    p=study.engine.baseline.build(d,'c0',d['arms']['c0']['phase_reference'])
    baseline=d['arms']['c0']['negative_twice_elbo']-unused_count(p,d['entries'])*unused_student_gap(d['model']['nu'])
    for k,node in enumerate(bank):
        labels=sorted({r['candidate_index'] for r in node['seed']['rows']});means=d['all_means'][labels]
        trial=fit_configuration(d,node,d['entries'],means);trial['bank_index']=k;trials.append(trial)
        dd=dict(d,node=node,means=means)
        for arm,saved in trial['arms'].items():checks.append(audit_baseline(dd,arm,saved))
        print(case,'bank',k,'paired valid',trial['paired_valid'],flush=True)
    penalty=float(2*np.log(max(1,len(bank))));selected,gain=choose(trials,baseline,penalty)
    write(OUT/(case+'.json'),dict(case=case,trials=trials,selected=selected,gain=gain,penalty=penalty,
        incumbent_corrected_loss=baseline,checks=checks,RF_selection_frozen_before_geographic_scoring=True,
        valid_incumbent_retained_if_no_RF_improvement=True,no_new_hypothesis_or_point_or_prior_change=True))
    return dict(case=case,status='complete',branches=len(bank),selected=selected is not None,checks=len(checks))


def main():
    study.configure();OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve existing-bank control')
    cases=read(study.RAW/'protocol.json')['cases']
    write(OUT/'protocol.json',dict(cases=cases,source_sha256=sha(Path(__file__)),
        cold_start=[0,0],same_existing_finite_bank_and_original_observations_and_priors=True,
        paired_both_c_arms_and_existing_near_feasible_rescue=True,
        selection='lowest corrected c0 RF loss among paired-valid candidates; gain>2log(bank size); exact valid incumbent otherwise',
        no_GPS_or_following_TLE_or_new_RF=True))
    with ProcessPoolExecutor(max_workers=2) as pool:rows=list(pool.map(one,cases))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,all_passed=True))


if __name__=='__main__':main()
