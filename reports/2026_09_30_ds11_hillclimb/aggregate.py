"""Independently audit and summarize one frozen challenger across declared stages."""
import hashlib
import json
from pathlib import Path
import statistics
import sys

from harness import BASE, HERE, SCREEN, distance, percentile


def validate_result(record):
    valid = [s for s in record['starts'] if s['qualified']]
    selected = record['selected']
    if selected is None:
        return False
    assert valid and selected['score'] == max(s['score'] for s in valid)
    assert selected['success'] and not selected['boundary']
    assert selected['gradient'] <= .01 and selected['audit'] <= .02
    assert any(s['x']==selected['x'] and s['score']==selected['score'] for s in valid)
    return True


def summarize_rows(rows):
    good = [r for r in rows if r['qualified']]
    old = [r['baseline_error_m'] for r in rows]
    values = [r['error_m'] for r in good]
    return dict(attempts=len(rows),qualified=len(good),
                median_m=statistics.median(values) if values else None,
                baseline_median_m=statistics.median(old),
                p90_m=percentile(values,.9) if values else None,
                baseline_p90_m=percentile(old,.9),
                mean_m=statistics.mean(values) if values else None,
                baseline_mean_m=statistics.mean(old),
                max_m=max(values) if values else None,baseline_max_m=max(old),
                paired_wins=sum(r['error_m'] < r['baseline_error_m'] for r in good),
                median_paired_improvement_m=statistics.median(r['baseline_error_m']-r['error_m'] for r in good) if good else None,
                subkm=sum(e<1000 for e in values),baseline_subkm=sum(e<1000 for e in old),
                common_iid_held_gain=sum(r['common_iid_held_gain'] for r in good),
                median_runtime_s=statistics.median(r['runtime_s'] for r in rows))


def main(family,variant,stages,expected,base=BASE):
    plan=json.loads((base/'plan.json').read_text())
    rows=[]
    source_hashes={}
    for stage in stages:
        folder=HERE/family/'runs'/stage
        for receipt_path in sorted(folder.glob(f'{variant}_??.receipt.json')):
            receipt=json.loads(receipt_path.read_text())
            index=receipt['index']
            result_path=receipt_path.with_name(receipt_path.name.replace('.receipt.json','.json'))
            result=json.loads(result_path.read_text()) if result_path.exists() else None
            qualified=bool(receipt['exit_code']==0 and result and validate_result(result))
            if result:
                assert result['session']==plan['inputs'][index]['session_id']
                assert result['variant']==variant and result['index']==index
                # Every result declares exact consumed local source bytes.
                for name,h in result['sources'].items():
                    assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==h,name
                source_hashes[str(result_path)]=hashlib.sha256(result_path.read_bytes()).hexdigest()
            source_hashes[str(receipt_path)]=hashlib.sha256(receipt_path.read_bytes()).hexdigest()
            original=json.loads((base/'runs'/f'{index:02d}_iid.json').read_text())['selected']
            assert original is not None
            selected=result['selected'] if qualified else None
            rows.append(dict(index=index,stage=stage,session=plan['inputs'][index]['session_id'],
                             qualified=qualified,exit_code=receipt['exit_code'],
                             error_m=distance(selected['estimate_deg']) if selected else None,
                             baseline_error_m=distance(original['estimate_deg']),
                             common_iid_held_gain=selected['common_iid']['held']-selected['incumbent_common_iid']['held'] if selected else None,
                             runtime_s=receipt['wall_s']))
    assert len(rows)==expected and len({r['index'] for r in rows})==expected
    assert set(r['index'] for r in rows)==set(range(expected))
    subsets={'all':rows}
    if expected==32:
        subsets['screen']=[r for r in rows if r['index'] in SCREEN]
        subsets['replication']=[r for r in rows if r['index'] not in SCREEN]
    output=dict(family=family,variant=variant,stages=stages,
                summaries={name:summarize_rows(part) for name,part in subsets.items()},
                rows=sorted(rows,key=lambda r:r['index']),source_sha256=source_hashes)
    path=HERE/family/f'aggregate-{variant}-{expected}.json'
    with path.open('x') as stream:
        json.dump(output,stream,indent=2)
    print(json.dumps(output['summaries'],indent=2))


if __name__=='__main__':
    main(sys.argv[1],sys.argv[2],sys.argv[3].split(','),int(sys.argv[4]),
         HERE/'additional' if len(sys.argv)>5 and sys.argv[5]=='additional' else BASE)
