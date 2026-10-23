"""Retain the audited reference on explicitly unresolved execution deadlines.

This is an operational failure policy, not a completed scientific search.
Failed searches remain archived and prevent claiming full search completion.
"""
from pathlib import Path
import time
import run_algo04_candidate as study
import repair_algo04_empty_audit as repair
from run_algo01_ds23_sample import read,write,sha


def deadline_failure(record):
    return record['status']=='failed' and 'TimeoutError' in (record.get('error') or '')


def main():
    cases=[]
    for path in study.RAW.glob('*/result.json'):
        r=read(path)
        if deadline_failure(r):cases.append(r['case'])
    protocol=study.OUT/'deadline_fallback_protocol.json'
    if protocol.exists():raise FileExistsError('preserve deadline fallback')
    write(protocol,dict(cases=sorted(cases),source_sha256=sha(Path(__file__)),
        decision='reference retained solely on unresolved timeout; no candidate chosen by GPS',
        search_not_completed=True,not_a_scientific_acceptance=True,no_new_fit_or_threshold_change=True))
    study.check=repair.checked
    for case in cases:
        began=time.monotonic();folder=study.RAW/case;old=read(folder/'result.json')
        archive=folder/'unresolved_deadline';archive.mkdir();(folder/'result.json').rename(archive/'result.json')
        d=study.SETUP(case);cov={a:study.engine.baseline.inventory(d,a) for a in ['c0','fitted_c']}
        reference=study.pack(d,cov,'default');audits=study.audit_pair(d,'default','deadline_reference_fallback')
        write(folder/'result.json',dict(case=case,status='deadline_fallback',search_complete=False,
            reference=reference,graph=reference,candidate=reference,audits=audits,
            original_accepted_IDs_preserved=True,no_evaluation_GPS_used=True,causal_catalogue_checked=True,
            reason=old['error'],seconds=time.monotonic()-began,failed_attempt_sha256=sha(archive/'result.json')))
        print(case,'explicit reference fallback',flush=True)
    results=[read(study.RAW/c/'result.json') for c in study.freeze()['cases'] if (study.RAW/c/'result.json').exists()]
    write(study.OUT/'execution.json',dict(rows=[{k:v for k,v in r.items() if k in ['case','status','seconds','stage','error']} for r in results],
        all_terminal=len(results)==410,all_passed=len(results)==410 and all(r['status']!='failed' for r in results),
        all_scientific_searches_complete=not cases,deadline_fallback_cases=sorted(cases)))


if __name__=='__main__':main()
