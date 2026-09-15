"""Preserve the successful corrected 30-MS/s visits alongside earlier refusals."""
import hashlib
import json
from pathlib import Path
import shutil

BASE=Path(__file__).parent
ROOT=BASE/'two-frequency-visits30-v3'
OUT=Path('/home/mouse9911/gits/leo-radio20-reboot-publish/reports/figures/2026_09_13_radio20_30ms_visit_readiness')


def read(p): return json.loads(p.read_text())
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    result={'scope':'physical_30MS_upper_edge_two_visit_qualification','native_tracking_qualified':False,
        'bounded_visits_qualified':True,'fw_commit':'56ebc20955b88fd16579defcb75e233de5720aef',
        'prior_evidence_sha256':digest(OUT/'evidence.json'),
        'operator':read(ROOT/'operator.json'),'status':read(ROOT/'stdout.json'),
        'sequence':read(ROOT/'independent-sequence-review.json'),
        'children':[read(ROOT/f'visit-{n}/independent-visit-review.json') for n in range(2)]}
    assert result['sequence']['status']=='pass' and all(c['status']=='pass' for c in result['children'])
    op=result['operator'];assert op['before']==op['after'] and op['temporary_files_removed']
    for name in ('visits.txt',): shutil.copyfile(ROOT/name,OUT/name)
    shutil.copyfile(BASE/'record_30ms_visit_result.py',OUT/'record_30ms_visit_result.py')
    result['recorder_sha256']=digest(OUT/'record_30ms_visit_result.py')
    with (OUT/'evidence-completed.json').open('x') as f: json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({'output':str(OUT/'evidence-completed.json'),'sha256':digest(OUT/'evidence-completed.json'),
        'rf_seconds':sum(c['rf_seconds'] for c in result['children']),
        'native_results':sum(c['native_results'] for c in result['children']),
        'accepted_past':sum(c['accepted_past_observations'] for c in result['children'])}))


if __name__=='__main__': main()
