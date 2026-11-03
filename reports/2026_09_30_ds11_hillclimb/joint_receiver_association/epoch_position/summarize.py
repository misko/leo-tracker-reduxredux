"""Score all frozen family2 fits only after terminal, source-bound receipts."""
import importlib.util
import json
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'acquisition_position'))
from common import base,read,digest,verify_sources


def main():
    reference_path=base('original')/'summarize.py'
    spec=importlib.util.spec_from_file_location('reference_metrics',reference_path)
    reference=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    sources={str(p):digest(p) for p in (Path(__file__),HERE/'PROTOCOL.md',reference_path)}
    rows=[]
    for cohort,index in (('original',0),('additional',1)):
        original_path=base(cohort)/f'runs/{index:02d}_iid.json'
        sources[str(original_path)]=digest(original_path)
        row=dict(cohort=cohort,index=index,original_distance_m=reference.distance(read(original_path)['selected']['estimate_deg']))
        for arm in ('doppler','timing'):
            path=HERE/f'fit-{cohort}-{index:02d}-{arm}.json'
            receipt_path=path.with_suffix('.receipt.json')
            receipt=read(receipt_path)
            assert receipt['log_sha256']==digest(path.with_suffix('.log'))
            assert receipt['runner_sha256']==digest(HERE/'run.py')
            sources[str(receipt_path)]=digest(receipt_path)
            if receipt['exit_code'] or not path.exists():
                row[arm]=dict(qualified=False,exit_code=receipt['exit_code'])
                continue
            fit=read(path)
            verify_sources(fit)
            sources[str(path)]=digest(path)
            row[arm]=dict(qualified=fit['qualified'],distance_m=reference.distance(fit['coordinates_deg']),gradient_max=fit['gradient_max'],derivative_discrepancy=fit['derivative_audit']['discrepancy'],elapsed_s=fit['elapsed_s'])
        row['passed']=bool(all(row[a]['qualified'] for a in ('doppler','timing')) and row['timing']['distance_m']<=.95*min(row['original_distance_m'],row['doppler']['distance_m']))
        rows.append(row)
    result=dict(rows=rows,pilot_passed=all(r['passed'] for r in rows),general_ds11_improvement_established=False,sources=sources)
    with (HERE/'summary.json').open('x') as f:
        json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
