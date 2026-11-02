"""One supported case, no position optimization, before the parent seal."""
import argparse
import importlib.util
from pathlib import Path
import signal
import sys
import time
import numpy as np

spec=importlib.util.spec_from_file_location('age_prior_preflight_driver',Path(__file__).with_name('run.py'))
driver=importlib.util.module_from_spec(spec);sys.modules[spec.name]=driver;spec.loader.exec_module(driver)


def preflight(case):
    began=time.monotonic();signal.signal(signal.SIGALRM,driver.timeout);signal.setitimer(signal.ITIMER_REAL,60.)
    roster=driver.read(driver.ROOT/'rf_roster.json');inventory=driver.read(driver.REPORT/'covariance/derived_inventory.json')
    row=next(r for r in roster['cases'] if r['case']==case)
    support=next(r for r in inventory['rows'] if r['case']==case)
    if support['status']!='ready':raise ValueError('A supported orbit-only case is required')
    if driver.sha(row['input_path'])!=row['input_sha256']:raise ValueError('Frozen input changed')
    root=Path(row['input_path']).parent.parent
    driver.e.configure(root,driver.ROOT/'preflight_engine');driver.e.ROOTS[case[:4]]=root
    d,z,replay=driver.e.load_case(case);diagnostic_problems={}
    baseline,control=driver.baseline_parity(d,z,row,diagnostic_problems=diagnostic_problems)
    covariance=driver.module('age_matched_covariance',driver.REPORT/'covariance/age_covariance.py')
    dd,receipt=covariance.candidate_context(d,z,dict(case=case,input_path=row['input_path'],selected_family=row['target_family']))
    expected={k:support[k] for k in ('pair_count','history_sha256','nominal_elements_sha256','temporal_extent_sha256','coefficient_covariance') if k in support}
    driver.check_support(receipt,expected)
    if receipt['status']!='ready':raise ValueError('Supported orbital covariance failed reconstruction')
    arms={};common=d['problems']['fitted_c']
    for arm in driver.ARMS:
        p,context=driver.e.build(dd,z,arm,common[0].reference);native=driver.evidence.native_inventory(p,context)
        if native['owners']!=z['baseline_owners'][arm]:raise ValueError('Age covariance changed native owners')
        values=p.calculate(common[1])
        arms[arm]=dict(start_objective=driver.objective(p,context,common[1]),
            start_curved_RMS_hz=float(np.sqrt(np.mean(values['conditional_residual_hz'][p.keep]**2))),
            native_ids_sha256=native['native_ids_sha256'],fitted_owners_sha256=native['fitted_owners_sha256'])
    signal.setitimer(signal.ITIMER_REAL,0.)
    for arm,(p,x) in diagnostic_problems.items():control[arm]['nuisance']=driver.nuisance.optional_snapshot(p,x,target_family=row['target_family'])
    repo=driver.REPORT.parents[1].resolve()
    runtime={}
    for loaded in list(sys.modules.values()):
        name=getattr(loaded,'__file__',None)
        if not name:continue
        source=Path(name).resolve()
        if source.suffix=='.py' and source.is_relative_to(repo) and source.is_file():runtime[str(source)]=driver.sha(source)
    result=dict(case=case,status='passed',no_position_optimization=True,no_geography_read=True,seconds=time.monotonic()-began,
        baseline_replay=baseline,selected_A_control_replay=control,prior_receipt=receipt,start_arms=arms,
        runtime_repo_source_sha256=dict(sorted(runtime.items())))
    driver.write(driver.ROOT/'preflight.json',result)
    print(dict(case=case,status=result['status'],seconds=result['seconds'],pair_count=receipt['pair_count']))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--case',default='DS24-0010')
    preflight(ap.parse_args().case)
