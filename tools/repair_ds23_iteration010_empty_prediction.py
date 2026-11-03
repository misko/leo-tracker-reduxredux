"""Repair the calibration-only audit path, preserving all20 confirmation cases."""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import shutil
import numpy as np

import confirm_ds23_iteration010_short_curves as confirmation
from investigate_dsx01_localization_failures import fit
from probe_ds23_frequency_events import summary
from run_algo01_ds23_sample import read,write,sha

SOURCE=confirmation.OUT
OUT=confirmation.runner.RAW/'short_confirmation20_v2'
ORIGINAL_REFIT=confirmation.experiment.binding.paths.refit


def refit_allow_empty(d,kind,arm):
    if d['entries']:return ORIGINAL_REFIT(d,kind,arm)
    reference=np.zeros(len(d['means']));x=np.zeros(2);history=[]
    for _ in range(5):
        p=confirmation.experiment.binding.paths.build(d,kind,arm,reference);result=fit(p,x,iterations=48);x=np.asarray(result['parameters'])
        phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
        history.append(dict(fit=result,phase_change_s=float(np.max(abs(phase-reference)))));reference=phase
    saved=summary(p,x,[]);saved.update(history=history,final_phase_change_s=history[-1]['phase_change_s'],
        audit=dict(no_predictive_observations=True,no_predictive_density_factor_to_replay=True,
            curved_coefficients_are_the_only_calibration_source=True))
    return saved


def one(case):
    confirmation.configure();confirmation.experiment.OUT=OUT/'short_whole_curves'
    confirmation.experiment.binding.paths.refit=refit_allow_empty
    return confirmation.experiment.one(case)


def main():
    execution=read(SOURCE/'execution.json');assert execution['all_terminal']
    OUT.mkdir(exist_ok=True);(OUT/'short_whole_curves').mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve empty-prediction repair')
    failed=[r['case'] for r in execution['rows'] if r['status']!='complete']
    if any('curved_calculate' not in r['error'] for r in execution['rows'] if r['status']!='complete'):raise ValueError('unexpected confirmation failure')
    protocol=read(SOURCE/'protocol.json')
    write(OUT/'protocol.json',dict(protocol,source_sha256=sha(Path(__file__)),original_protocol_sha256=sha(SOURCE/'protocol.json'),
        same20cases_no_resampling=True,failed_cases=failed,only_empty_predictive_audit_path_changed=True,
        empty_cases_keep_original_five_by48_support_model_fit_and_summary=True,
        successful18case_outputs_reused_byte_exact=True,no_GPS_or_following_TLE_new_data_or_policy_change=True))
    reuse=[]
    for r in execution['rows']:
        if r['status']!='complete':continue
        for path in (SOURCE/'short_whole_curves').glob(r['case']+'*.json'):
            target=OUT/'short_whole_curves'/path.name;shutil.copyfile(path,target)
            reuse.append(dict(source=str(path),sha256=sha(path),copied_sha256=sha(target)))
    write(OUT/'reuse_receipt.json',dict(files=reuse,all_identical=all(r['sha256']==r['copied_sha256'] for r in reuse)))
    with ProcessPoolExecutor(max_workers=2) as pool:rows=list(pool.map(one,failed))
    rows=[r for r in execution['rows'] if r['status']=='complete']+rows
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,all_passed=len(rows)==20 and all(r['status']=='complete' for r in rows)))


if __name__=='__main__':main()
