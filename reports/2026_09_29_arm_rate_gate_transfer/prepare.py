#!/usr/bin/env python3
"""Seal the existing metadata-only DS8/DS9 transfer panel and its provenance."""
import hashlib,json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
INPUTS=Path('/var/tmp/leo-arm-ds89-validation/inputs')
BASELINE=ROOT/'reports/2026_09_28_arm_ds89_validation/baseline-v1/rows.jsonl'
LAG=ROOT/'reports/2026_09_29_arm_lag_discovery'
PSD=ROOT/'reports/2026_09_29_arm_psd_proposal'

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    receipt=json.loads((INPUTS/'inputs.json').read_text())
    if not receipt['complete'] or len(receipt['rows'])!=680:raise ValueError('DS8/DS9 input receipt is incomplete')
    inventory={(r['session_id'],r['visit_index']):r for r in receipt['rows']}
    baseline={}
    for line in BASELINE.read_text().splitlines():
        row=json.loads(line);ctx=row['context']
        if row['method']=='original' and row['repeat']==0 and row['status']=='ok':
            baseline[(ctx['session_id'],ctx['visit_index'])]=ctx
    panels={}
    for dataset in ('ds8','ds9'):
        feature=LAG/f'{dataset}-32-v1/rows.jsonl'
        reference=PSD/f'host-{dataset}-full-v2'
        manifest=json.loads((reference/'manifest.json').read_text())
        selected=manifest['selected']
        if not manifest['complete'] or len(selected)!=32:raise ValueError(f'{dataset} reference is incomplete')
        counts={}
        for index,ctx in enumerate(selected):
            key=(ctx['session_id'],ctx['visit_index'])
            if key not in inventory or inventory[key]['sha256']!=ctx['sha256']:raise ValueError(f'{dataset} input binding differs')
            if key not in baseline or baseline[key]['sha256']!=ctx['sha256']:raise ValueError(f'{dataset} baseline binding differs')
            group=(str(ctx['rate_hz']),ctx['target']['edge']);counts[group]=counts.get(group,0)+1
            if index<8 and ctx['rate_hz']!=2500000:raise ValueError(f'{dataset} is not front-loaded at 2.5 MS/s')
            source=INPUTS/ctx['file']
            if sha(source)!=ctx['sha256']:raise ValueError(f'{dataset} IQ hash differs: {source}')
        expected={(str(rate),edge):4 for rate in (2500000,5000000,7500000,10000000) for edge in ('lower','upper')}
        if counts!=expected:raise ValueError(f'{dataset} rate/edge balance differs')
        panels[dataset.upper()]={'dwells':32,'first_dwells':'eight 2.5 MS/s (four per edge)',
            'reference':str(reference.relative_to(ROOT)),'reference_manifest_sha256':sha(reference/'manifest.json'),
            'reference_rows_sha256':sha(reference/'rows.jsonl'),'features':str(feature.relative_to(ROOT)),
            'features_sha256':sha(feature),'selected':selected}
    result={'schema':'arm-rate-gate-transfer-panel/v1','scope':'read-only saved IQ; no candidate execution in preparation',
        'selection':'existing independent DS8 and DS9 panels: four evenly spaced metadata rows per rate/edge; rate order puts 2.5 MS/s first',
        'inputs':str(INPUTS/'inputs.json'),'inputs_sha256':sha(INPUTS/'inputs.json'),
        'baseline':str(BASELINE.relative_to(ROOT)),'baseline_sha256':sha(BASELINE),'panels':panels}
    (HERE/'selection.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:{'dwells':v['dwells'],'first_dwells':v['first_dwells']} for k,v in panels.items()},indent=2))
if __name__=='__main__':main()
