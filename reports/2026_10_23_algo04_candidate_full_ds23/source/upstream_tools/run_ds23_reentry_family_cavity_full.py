"""Thirty-worker full DS23 assessment of coherent recovery then family cavities."""

import argparse
import copy
from concurrent.futures import ProcessPoolExecutor,as_completed
from functools import lru_cache
from pathlib import Path
import time

import numpy as np

import probe_ds23_reentry_family_cavity as study
from probe_ds23_uncertainty_mean import selected_context as original_selected_context
from probe_ds23_sign_carrier_position import context_signed as original_signed_context
from run_algo01_ds23_sample import ROOT,read,write,sha

PILOT=study.OUT
OUT=PILOT/'full_DS23'
PREVIOUS=ROOT/'reports/2026_10_22_ds23_family_cavity/phase_refreshed/full_DS23/position'
AUTHORITY=ROOT/'reports/2026_10_22_ds23_family_cavity_full_assessment/evidence/publication_receipt.json'


def repair_references(arms,previous):
    """Reuse previously audited fit references; no fit, threshold or data change."""
    result=copy.deepcopy(arms);repairs=[]
    for arm,r in previous.get('legacy_fit_reference_replay',{}).items():
        current=result[arm];baseline=previous['baseline_arms'][arm]
        if current.get('history')!=baseline.get('history'):continue
        if not np.array_equal(current['phase_reference'],r['archived_reference']):continue
        current['phase_reference']=r['replayed_fit_reference'];repairs.append(arm)
    return result,repairs


@lru_cache(maxsize=8)
def previous_case(case):
    protocol=read(OUT/'protocol.json');path=PREVIOUS/(case+'.json')
    if sha(path)!=protocol['previous_case_receipts'][case]['position_sha256']:raise ValueError('previous published benchmark case changed')
    return read(path)


def selected_with_recorded_reference(case):
    d,arms=original_selected_context(case);arms,repairs=repair_references(arms,previous_case(case))
    d['recorded_legacy_reference_repairs']=repairs;return d,arms


def signed_with_recorded_reference(case):
    values=list(original_signed_context(case));saved=copy.deepcopy(values[-2]);arms,repairs=repair_references(saved['policy_arms'],previous_case(case))
    saved['policy_arms']=arms;values[-2]=saved;return tuple(values)


def configure():
    study.OUT=OUT;study.selected_context=selected_with_recorded_reference;study.recovery.context_signed=signed_with_recorded_reference


def prepare():
    path=OUT/'protocol.json'
    if path.exists():return read(path)
    authority=read(AUTHORITY);cases=sorted(r['case'] for r in authority['case_result_sha256']);assert len(cases)==410
    parent=read(PILOT/'protocol.json');audits={}
    for cohort in ['engineering','random20']:
        saved=read(PILOT/(cohort+'_audit_execution.json'));assert saved['all_passed']
        audits.update({r['case']:r for r in saved['rows']})
    for folder in ['reentry','nominations','position']:(OUT/folder).mkdir(parents=True,exist_ok=True)
    for case,audit in audits.items():
        for folder,suffix,expected in [('reentry','.json',audit['reentry_sha256']),
            ('nominations','_nominations.json',audit['nominations']['source_sha256']),('position','.json',audit['positions']['source_sha256'])]:
            source=PILOT/folder/(case+suffix);target=OUT/folder/source.name
            assert sha(source)==expected
            if target.exists():assert sha(target)==expected
            else:target.symlink_to(source.resolve())
    protocol=dict(parent,cases=cases,full_population=410,dataset_total=413,unavailable=['DS23-0012','DS23-0184','DS23-0286'],
        workers=30,parent_protocol_sha256=sha(PILOT/'protocol.json'),pilot_cases_reused_exactly=sorted(audits),
        previous_case_receipts={r['case']:r for r in authority['case_result_sha256']},previous_authority_sha256=sha(AUTHORITY),
        recorded_reference_repair='Use existing0074/0365 fit-reference replay only when saved baseline history and archived reference match; no position refit or threshold change',
        stages='bounded reentry400s, nomination360s, paired position540s per scan; all failures explicit; no error-ranked fallback',
        no_GPS_or_geographic_evaluation_before_numerical_audits=True,
        source_full_driver_sha256=sha(Path(__file__)))
    write(path,protocol);return protocol


def pipeline(case):
    configure();began=time.monotonic()
    try:
        for stage in ['reentry','nominations','positions']:
            result=study.one(case,stage)
            if result['status']!='complete':raise ValueError(stage+' stage '+result['status']+': '+str(result.get('error')))
        return dict(case=case,status='complete',seconds=time.monotonic()-began,
            reentry_sha256=sha(OUT/'reentry'/(case+'.json')),nomination_sha256=sha(OUT/'nominations'/(case+'_nominations.json')),
            position_sha256=sha(OUT/'position'/(case+'.json')))
    except Exception as exc:
        import traceback
        traceback.print_exc();return dict(case=case,status='failed',error=repr(exc),seconds=time.monotonic()-began)


def audit(case):
    configure();return study.one(case,'audit')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['pipeline','audit'],required=True)
    parser.add_argument('--workers',type=int,default=30);args=parser.parse_args()
    if not 1<=args.workers<=30:raise ValueError('1to30workers required')
    OUT.mkdir(parents=True,exist_ok=True);protocol=prepare();rows=[]
    if args.stage=='audit' and not read(OUT/'pipeline_execution.json')['all_passed']:raise ValueError('full pipeline has unresolved failed cases')
    function=pipeline if args.stage=='pipeline' else audit
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for f in as_completed([pool.submit(function,c) for c in protocol['cases']]):
            r=f.result();rows.append(r);print(r['case'],r.get('status','audited'),round(r.get('seconds',0),2),flush=True)
            write(OUT/(args.stage+'_progress.json'),dict(rows=rows,completed=len(rows),total=len(protocol['cases'])))
    write(OUT/(args.stage+'_execution.json'),dict(rows=rows,all_terminal=True,
        all_passed=all(r.get('all_passed',r.get('status')=='complete') for r in rows),no_geographic_evaluation_yet=True))


if __name__=='__main__':main()
