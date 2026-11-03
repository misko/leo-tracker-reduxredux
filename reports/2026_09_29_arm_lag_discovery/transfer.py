"""Frozen proposal transfer to metadata-selected DS8/DS9 saved dwells."""
import json
from pathlib import Path
import sys
import evaluate

HERE=Path(__file__).resolve().parent
source=Path('/var/tmp/leo-arm-ds89-validation/inputs')
manifest=json.loads((source/'inputs.json').read_text());assert manifest['complete']
baseline=HERE.parent/'2026_09_28_arm_ds89_validation/baseline-v1/rows.jsonl'
for dataset in ('DS8','DS9'):
    stage=Path('/var/tmp/leo-lag-discovery-'+dataset.lower()+'-v1');stage.mkdir(exist_ok=False)
    rows=[r for r in manifest['rows'] if r['dataset_id']==dataset]
    assert len(rows)==(260 if dataset=='DS8' else 420)
    for row in rows:(stage/row['file']).symlink_to(source/row['file'])
    (stage/'inputs.json').write_text(json.dumps({'complete':True,'rows':rows,
         'source_manifest_sha256':evaluate.a.sha(source/'inputs.json'),'dataset_id':dataset},indent=2)+'\n')
    evaluate.a.INPUTS=stage;evaluate.a.BASELINE=baseline
    sys.argv=['evaluate.py','--output',dataset.lower()+'-32-v1']
    evaluate.main()
