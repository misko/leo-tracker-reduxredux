#!/usr/bin/env python3
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def collect(name):
    folder=HERE/name;a=json.loads((folder/'standard-audit.json').read_text());s=json.loads((folder/'summary.json').read_text())
    emitted={}
    for line in (folder/'rows.jsonl').read_text().splitlines():
        record=json.loads(line);rate=str(record['context']['rate_hz'])
        emitted[rate]=emitted.get(rate,0)+sum(len(row['candidates']) for row in record['rows'])
    by_rate={rate:{'baseline_positive_hits':v['reference_positive_hits'],'recovered_positive_hits':v['recovered_positive_hits'],
        'emitted_candidates':emitted[rate],'emitted_positive_hits':v['native_positive_hits'],
        'unmatched_positive_hits':v['unmatched_positive_hits']} for rate,v in a['by_rate'].items()}
    if sum(emitted.values())!=s['candidate_entries']:raise ValueError(f'{name} emitted count differs')
    return {'dwells':s['dwells'],'windows':s['windows'],'emitted_candidates':s['candidate_entries'],
        'baseline_positive_hits':a['totals']['reference_positive_hits'],'recovered_positive_hits':a['totals']['recovered_positive_hits'],
        'emitted_positive_hits':a['totals']['native_positive_hits'],'unmatched_positive_hits':a['totals']['unmatched_positive_hits'],
        'by_rate':by_rate,'binary_sha256':s['binary_sha256'],'build_sha256':s['build_sha256'],
        'rows_sha256':s['rows_sha256'],'summary_sha256':sha(folder/'summary.json'),'audit_sha256':sha(folder/'standard-audit.json')}
def main():
    variants={}
    for variant in ('ungated-wave4','gate-300','gate-312'):
        variants[variant]={ds:collect(f'host-{ds}-{variant}') for ds in ('ds8','ds9')}
    for variant in ('gate-300','gate-312'):
        for ds in ('ds8','ds9'):
            cur=variants[variant][ds];base=variants['ungated-wave4'][ds]
            cur['delta_vs_ungated']={'emitted_candidates':cur['emitted_candidates']-base['emitted_candidates'],
                'recovered_positive_hits':cur['recovered_positive_hits']-base['recovered_positive_hits']}
            for rate in cur['by_rate']:
                cur['by_rate'][rate]['recovery_delta_vs_ungated']=cur['by_rate'][rate]['recovered_positive_hits']-base['by_rate'][rate]['recovered_positive_hits']
    result={'schema':'arm-rate-gate-transfer-results/v1','scope':'host saved-IQ DS8/DS9 transfer; no ARM execution',
        'selection_sha256':sha(HERE/'selection.json'),'evaluator_sha256':sha(HERE/'evaluate.py'),
        'audit_adapter_sha256':sha(HERE/'audit.py'),'variants':variants}
    (HERE/'results.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
