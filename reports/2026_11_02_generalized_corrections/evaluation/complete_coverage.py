"""Prospective completion of never-started cases using the frozen worker.

This wrapper cannot retry any actual attempt. Scientific inference, selection,
cell limits and fallback behavior remain imported from the original driver.
"""
import argparse
from collections import Counter
import copy
import importlib.util
import multiprocessing
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('frozen_generalized_driver',HERE/'run.py')
driver=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=driver
spec.loader.exec_module(driver)


def attempt_evidence(result,folder):
    """Classify start evidence, without reading scores or acceptance decisions."""
    folder=Path(folder)
    reasons=[]
    if result['status']!='total_deadline_fallback':reasons.append('terminal_nonqueue_status')
    if 'wall_seconds' in result:reasons.append('worker_elapsed_receipt')
    for key in ('baseline_replay','reconstruction','numerical_trigger_diagnostics','family_ranking','prior_receipt','traceback'):
        if key in result:reasons.append('worker_field:'+key)
    if (folder/'checkpoint_at_total_deadline.json').exists():reasons.append('preserved_started_result_checkpoint')
    if list(folder.glob('*.rf.json')):reasons.append('model_arm_cell')
    if list(folder.glob('*.checkpoint.json')):reasons.append('model_arm_checkpoint')
    if folder.exists() and any(p.name!='result.json' for p in folder.iterdir()):
        reasons.append('any_nonmanager_artifact_including_temporary_or_engine_output')
    return dict(started=bool(reasons),reasons=reasons)


def eligible_records(roster,prior_results,expected_protocols):
    """Only the intersection of never-started records across all prior waves."""
    prior=[]
    roster_by_case={r['case']:r for r in roster['cases']}
    if len(roster_by_case)!=len(roster['cases']):raise ValueError('Duplicate RF roster case')
    if len(expected_protocols)!=len(prior_results):raise ValueError('Every prior ledger requires its expected protocol')
    for results_path,expected_protocol in zip(prior_results,expected_protocols):
        results_path=Path(results_path)
        packet=driver.read(results_path)
        if not packet.get('workers_joined'):raise ValueError('Prior workers are not joined')
        if packet['protocol_sha256']!=expected_protocol:raise ValueError('Prior packet protocol binding mismatch')
        by_case={row['case']:row for row in packet['rows']}
        if len(by_case)!=len(packet['rows']):raise ValueError('Duplicate prior case ID')
        if packet['available']!=len(by_case):raise ValueError('Prior packet count mismatch')
        for case,row in by_case.items():
            if case not in roster_by_case:raise ValueError('Prior case outside frozen roster')
            record=roster_by_case[case]
            if row['protocol_sha256']!=expected_protocol:raise ValueError('Prior row protocol binding mismatch')
            if row['input_sha256']!=record['input_sha256'] or row['identities']!=record['identities']:
                raise ValueError('Prior row native input/recording identity mismatch')
        prior.append((results_path,by_case))
    if set(prior[0][1])!={r['case'] for r in roster['cases']}:
        raise ValueError('Original terminal ledger must retain the complete available roster')
    selected=[];ledger=[]
    for record in roster['cases']:
        evidence=[];never_started=True
        for result_path,by_case in prior:
            if record['case'] not in by_case:
                evidence.append(dict(prior_results=str(result_path),status='not_enqueued_in_this_wave'))
                continue
            row=by_case[record['case']]
            found=attempt_evidence(row,result_path.parent/'cases'/record['case'])
            never_started &= not found['started']
            evidence.append(dict(prior_results=str(result_path),**found))
        ledger.append(dict(case=record['case'],eligible_never_started=bool(never_started),evidence=evidence))
        if never_started:selected.append(record)
    return driver.scheduled(selected),ledger


def run(protocol_path,wave,prior_results):
    protocol=driver.read(protocol_path);policy=protocol['coverage_completion']
    if wave not in policy['allowed_waves']:raise ValueError('Wave outside prospective plan')
    if len(prior_results)!=policy['allowed_waves'].index(wave)+1:raise ValueError('All prior waves must be supplied')
    expected=[HERE/'results.json']+[HERE/name/'results.json' for name in policy['allowed_waves'][:len(prior_results)-1]]
    if [Path(p).resolve() for p in prior_results]!=[p.resolve() for p in expected]:
        raise ValueError('Prior ledger paths must match all chronological original/completion waves')
    for variable in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
        if driver.os.environ.get(variable)!='1':raise ValueError('Launch requires '+variable+'=1')
    for path,digest in protocol['source_sha256'].items():
        if driver.sha(path)!=digest:raise ValueError('Frozen source changed: '+path)
    original=driver.read(policy['original_protocol_path'])
    if driver.sha(policy['original_protocol_path'])!=policy['original_protocol_sha256']:
        raise ValueError('Original scientific execution protocol changed')
    for path,digest in original['source_sha256'].items():
        if driver.sha(path)!=digest:raise ValueError('Original frozen source changed: '+path)
    roster=driver.read(original['evaluation']['roster_path'])
    if driver.sha(original['evaluation']['roster_path'])!=original['evaluation']['roster_sha256']:
        raise ValueError('Original RF roster changed')
    folder=HERE/wave
    if (folder/'execution_started.json').exists() or (folder/'results.json').exists():
        raise FileExistsError('Every completion wave is a single attempt')
    digest=driver.sha(protocol_path)
    expected_protocols=[policy['original_protocol_sha256']]+[digest]*(len(prior_results)-1)
    records,eligibility=eligible_records(roster,prior_results,expected_protocols)
    configuration=copy.deepcopy(original['evaluation'])
    configuration['workers']=int(policy['workers'])
    configuration['total_seconds']=float(policy['wave_seconds'])
    if configuration['workers']!=16 or configuration['total_seconds']>1200:
        raise ValueError('Completion wrapper exceeds the prospective execution ceiling')
    driver.ROOT=folder
    driver.write(folder/'eligibility_plan.json',dict(coverage_protocol_sha256=digest,
        original_protocol_sha256=driver.sha(policy['original_protocol_path']),
        prior_results=[dict(path=str(Path(p).resolve()),sha256=driver.sha(p)) for p in prior_results],
        available_roster=len(roster['cases']),selected_cases=[r['case'] for r in records],
        eligibility=eligibility,selection_inputs='start evidence only; no scores, geometry or geography'))
    driver.write(folder/'execution_started.json',dict(protocol_sha256=digest,cases=len(records),wall_utc_ns=time.time_ns()))
    began=time.monotonic();deadline=began+configuration['total_seconds']
    pool=multiprocessing.get_context('fork').Pool(processes=configuration['workers'])
    futures=[pool.apply_async(driver.worker,((r,configuration,digest),)) for r in records]
    capped=False;errors=[]
    try:
        pool.close()
        for future in futures:
            remaining=deadline-time.monotonic()
            if remaining<=0:capped=True;break
            try:future.get(timeout=remaining)
            except multiprocessing.TimeoutError:capped=True;break
            except Exception as exc:errors.append(repr(exc))
    finally:
        if capped:pool.terminate()
        pool.join()
    rows=[]
    for record in records:
        path=folder/'cases'/record['case']/'result.json'
        result=driver.read(path) if path.exists() else driver.initial(record,digest)
        if result['status']=='running':
            if path.exists():driver.write(path.with_name('checkpoint_at_total_deadline.json'),result)
            driver.terminal_fallback(result,'total_deadline_fallback','Prospective completion-wave deadline exhausted; no actual attempt will be retried')
            driver.write(path,result)
        rows.append(result)
    driver.write(folder/'results.json',dict(protocol_sha256=digest,available=len(rows),
        original_available_roster=len(roster['cases']),workers_joined=True,
        workers_terminated_at_deadline=capped,wall_seconds=time.monotonic()-began,
        worker_errors=errors,status_counts=dict(Counter(r['status'] for r in rows)),rows=rows))
    print(wave,len(rows),dict(Counter(r['status'] for r in rows)),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--protocol',required=True,type=Path)
    ap.add_argument('--wave',required=True);ap.add_argument('--prior-results',action='append',required=True,type=Path)
    args=ap.parse_args();run(args.protocol,args.wave,args.prior_results)
