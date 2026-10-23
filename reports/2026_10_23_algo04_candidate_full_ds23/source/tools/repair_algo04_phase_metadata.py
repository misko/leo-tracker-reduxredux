"""Expose a legacy phase-convergence value already recorded in its history."""
import copy
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import run_algo04_candidate as study
import repair_algo04_empty_audit as audit
from run_algo01_ds23_sample import read,write,sha

SETUP=study.SETUP


def normalize_arms(arms):
    arms=copy.deepcopy(arms)
    for saved in arms.values():
        if 'final_phase_change_s' not in saved:
            value=saved['history'][-1]['phase_change_s']
            if not np.isfinite(value) or value<0:raise ValueError('invalid archived convergence value')
            saved['final_phase_change_s']=value
    return arms


def setup(case):
    d=SETUP(case);return dict(d,arms=normalize_arms(d['arms']))


def main():
    execution=read(study.OUT/'execution.json');assert execution['all_terminal']
    cases=[r['case'] for r in execution['rows'] if r.get('error')=="KeyError('final_phase_change_s')" and r.get('stage')=='setup']
    protocol=study.OUT/'phase_metadata_repair_protocol.json'
    if protocol.exists():raise FileExistsError('preserve phase metadata repair')
    write(protocol,dict(cases=cases,source_sha256=sha(Path(__file__)),
        only_change='copy history[-1].phase_change_s to missing final_phase_change_s',
        no_refit_or_changed_threshold_in_this_metadata_conversion=True,no_GPS_selection=True))
    for case in cases:
        folder=study.RAW/case;archive=folder/'failed_phase_metadata_attempt';archive.mkdir()
        for name in ['result.json','execution.log']:(folder/name).rename(archive/name)
    study.SETUP=setup;study.engine.current_setup=setup;study.check=audit.checked
    with ProcessPoolExecutor(max_workers=min(16,max(1,len(cases)))) as pool:rows=list(pool.map(study.worker,cases))
    write(study.OUT/'phase_metadata_repair_execution.json',dict(rows=rows,all_passed=all(r['status']!='failed' for r in rows)))
    results=[read(study.RAW/c/'result.json') for c in study.freeze()['cases']]
    write(study.OUT/'execution.json',dict(rows=[{k:v for k,v in r.items() if k in ['case','status','seconds','stage','error']} for r in results],
        all_terminal=True,all_passed=all(r['status']!='failed' for r in results)))
    print(rows,flush=True)


if __name__=='__main__':main()
