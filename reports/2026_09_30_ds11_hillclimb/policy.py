"""Audit the frozen qualification-only source/IID fallback policy."""
import json
from pathlib import Path
import sys

import aggregate
import harness


def select(challenger, incumbent):
    if incumbent is None or not incumbent.get('qualified', False):
        return None, 'failure'
    if challenger is not None and challenger.get('qualified', False):
        return challenger, 'challenger'
    return incumbent, 'iid_fallback'


def evaluate(base, stages, output):
    plan=json.loads((base/'plan.json').read_text())
    results={}
    hashes={}
    for stage in stages:
        for receipt_path in (harness.HERE/'source_balance'/'runs'/stage).glob('source_receiver_equal_??.receipt.json'):
            receipt=json.loads(receipt_path.read_text())
            index=receipt['index']
            assert index not in results
            path=receipt_path.with_name(receipt_path.name.replace('.receipt.json','.json'))
            result=json.loads(path.read_text()) if path.exists() else None
            if result:
                assert result['session']==plan['inputs'][index]['session_id']
                assert result['variant']=='source_receiver_equal'
                for name,expected in result['sources'].items():
                    assert harness.digest(name)==expected,name
                hashes[str(path)]=harness.digest(path)
            hashes[str(receipt_path)]=harness.digest(receipt_path)
            valid=bool(receipt['exit_code']==0 and result and aggregate.validate_result(result))
            original_path=base/'runs'/f'{index:02d}_iid.json'
            original=json.loads(original_path.read_text())
            incumbent=original['selected']
            hashes[str(original_path)]=harness.digest(original_path)
            challenger=result['selected'] if valid else None
            selected,kind=select(challenger,incumbent)
            results[index]=dict(index=index,session=plan['inputs'][index]['session_id'],
                qualified=selected is not None,selection=kind,raw_challenger_qualified=valid,
                error_m=harness.distance(selected['estimate_deg']) if selected else None,
                baseline_error_m=harness.distance(incumbent['estimate_deg']) if incumbent else None,
                common_iid_held_gain=challenger['common_iid']['held']-challenger['incumbent_common_iid']['held'] if challenger else 0,
                runtime_s=receipt['wall_s'])
    assert set(results)==set(range(len(plan['inputs'])))
    rows=[results[i] for i in range(len(results))]
    # Do not silently summarize over missing baseline outputs.
    assert all(r['baseline_error_m'] is not None for r in rows), 'Baseline failure retained; full-panel metrics unavailable'
    parts={'all':rows}
    if len(rows)==32:
        parts['screen']=[r for r in rows if r['index'] in harness.SCREEN]
        parts['replication']=[r for r in rows if r['index'] not in harness.SCREEN]
    summaries={key:dict(aggregate.summarize_rows(part),
                       raw_challenger_qualified=sum(r['raw_challenger_qualified'] for r in part),
                       iid_fallbacks=sum(r['selection']=='iid_fallback' for r in part))
               for key,part in parts.items()}
    check=summaries['all']
    passed=(len(rows)==12 and check['qualified']==12 and check['paired_wins']>=6
            and check['median_m']<check['baseline_median_m']
            and check['p90_m']<check['baseline_p90_m'])
    hashes[str(Path(__file__))]=harness.digest(__file__)
    hashes[str(harness.HERE/'additional-policy.md')]=harness.digest(harness.HERE/'additional-policy.md')
    with output.open('x') as stream:
        json.dump(dict(policy='qualified source_receiver_equal else original IID',
                       summaries=summaries,additional_replication_passed=passed if len(rows)==12 else None,
                       rows=rows,source_sha256=hashes),stream,indent=2)
    print(json.dumps(summaries,indent=2))


if __name__=='__main__':
    additional=len(sys.argv)>1 and sys.argv[1]=='additional'
    evaluate(harness.HERE/'additional' if additional else harness.BASE,
             ['additional'] if additional else ['wave1','wave1_replication'],
             harness.HERE/('policy-additional12.json' if additional else 'policy-original32.json'))
