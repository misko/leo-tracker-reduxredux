"""Retry only a representation error in the empty-predictive audit adapter."""
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import run_algo04_candidate as study
from run_algo01_ds23_sample import read,write,sha
import audit_algo04_legacy_reference as legacy

ORIGINAL=study.check
ERRORS={'AttributeError("\'DiagnosticNormal\' object has no attribute \'linear_slices\'")',"KeyError('linear_gates')"}


def checked(d,p,arm,saved,label):
    if not d['entries']:
        if not hasattr(p,'linear_slices'):p.linear_slices=[]
        if 'linear_gates' not in saved:saved=dict(saved,linear_gates=[])
    try:return ORIGINAL(d,p,arm,saved,label)
    except ValueError as exc:
        if 'baseline numerical diagnostic changed' not in str(exc):raise
        return legacy.replay(d,p,arm,saved,label,ORIGINAL)


def main():
    original_execution=read(study.OUT/'execution.json')
    missing=[c for c in study.freeze()['cases'] if not (study.RAW/c/'result.json').exists()]
    assert original_execution['all_terminal'] or all(list((study.RAW/c).glob('failed_deadline_attempt_*')) for c in missing)
    path=study.OUT/'empty_audit_repair_protocol.json'
    if path.exists():raise FileExistsError('preserve repair attempt')
    cases=[r['case'] for r in original_execution['rows'] if r.get('stage')=='setup' and
        (r.get('error') in ERRORS or 'baseline numerical diagnostic changed' in (r.get('error') or ''))]
    write(path,dict(cases=cases,source_sha256=sha(Path(__file__)),original_driver_sha256=sha(Path(study.__file__)),
        change='empty predictive entries have empty slice/gate lists; published legacy phase-reference conventions independently replayed',
        legacy_audit_source_sha256=sha(Path(legacy.__file__)),
        no_observation_prior_candidate_gate_optimizer_or_selection_change=True,
        no_geographic_evaluation_used_to_select_retries=True))
    write(study.OUT/'execution_before_empty_audit_repair.json',original_execution)
    for case in cases:
        folder=study.RAW/case;attempt=folder/'failed_empty_audit_attempt';attempt.mkdir()
        for name in ['result.json','execution.log']:(folder/name).rename(attempt/name)
    study.check=checked
    with ProcessPoolExecutor(max_workers=24) as pool:
        rows=[]
        for f in as_completed([pool.submit(study.worker,c) for c in cases]):
            row=f.result();rows.append(row);print(row,flush=True)
    write(study.OUT/'empty_audit_repair_execution.json',dict(rows=rows,all_terminal=True,all_passed=all(r['status']!='failed' for r in rows)))
    results=[read(study.RAW/c/'result.json') for c in study.freeze()['cases'] if (study.RAW/c/'result.json').exists()]
    rows=[{k:v for k,v in r.items() if k in ['case','status','seconds','stage','error']} for r in results]
    write(study.OUT/'execution.json',dict(rows=rows,all_terminal=len(rows)==410,all_passed=len(rows)==410 and all(r['status']!='failed' for r in rows),audit_adapter_repair=sha(path)))


if __name__=='__main__':main()
