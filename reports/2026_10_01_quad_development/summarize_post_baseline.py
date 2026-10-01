"""Compare completed baseline and fixed variants without excluding failed units."""
import argparse
import json
from pathlib import Path
import numpy as np
from build_selection import digest

HERE=Path(__file__).resolve().parent


def statistics(rows):
    errors=[r['error_m'] for r in rows if r['accepted']]
    times=[r['runtime_s'] for r in rows if r.get('runtime_s') is not None]
    return dict(planned=len(rows),accepted=len(errors),
        median_error_m=float(np.median(errors)) if errors else None,
        p90_error_m=float(np.percentile(errors,90)) if errors else None,
        within1000m=sum(e<=1000 for e in errors),within3000m=sum(e<=3000 for e in errors),
        known_runtime_count=len(times),median_runtime_s=float(np.median(times)) if times else None)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--name',required=True);args=parser.parse_args()
    assert Path(args.name).name==args.name
    output=HERE/(args.name+'.json');assert not output.exists()
    sources={}
    def load(path):
        assert digest(path)==path.with_suffix('.sha256').read_text().strip()
        sources[str(path)]=digest(path);return json.loads(path.read_text())
    complete=load(HERE/'post-baseline-v1/complete.json')
    plan=load(HERE/'post-baseline-v1/plan.json')
    selection=load(HERE/'selection.json');assert sources[str(HERE/'selection.json')]==plan['selection_sha256']
    eligible=load(HERE/'post-baseline-v1/eligibility.json')
    baseline={}
    for block in dict.fromkeys(u['block_id'] for u in selection['evaluation_units']):
        path=HERE/'independent-v2'/block/'evaluation.json';data=load(path)
        assert digest(path)==eligible['baseline_evaluation_sha256'][str(path)]
        baseline.update({r['unit']:r for r in data['rows']})
    assert len(baseline)==112 and set(baseline)=={u['unit_id'] for u in selection['evaluation_units']}
    recovered=dict(baseline);recovery=[]
    for decision in eligible['rows']:
        if not decision['eligible']:continue
        unit=decision['unit'];assert not baseline[unit]['accepted']
        path=HERE/'continuation-v1'/unit/'evaluation.json';data=load(path)
        assert len(data['rows'])==1 and data['rows'][0]['unit']==unit
        row=data['rows'][0];receipt_path=path.parent/(unit+'.json')
        if receipt_path.exists():
            receipt=load(receipt_path)
            assert receipt['continuation']['source_receipt_sha256']==baseline[unit]['receipt_sha256']
            assert row['receipt_sha256']==digest(receipt_path)
        recovered[unit]=row
        recovery.append(dict(unit=unit,baseline=baseline[unit],continued=row))
    summaries={}
    for arm,table in [('baseline',baseline),('baseline_plus_continuation',recovered)]:
        summaries[arm]={str(size):statistics([r for r in table.values() if r['size']==size]) for size in [1,2,4]}
    pairs=[]
    for unit in plan['pair_units']:
        path=HERE/'constituent-pair-v2'/unit/'evaluation.json';rows=load(path)['rows']
        assert len(rows)==1 and rows[0]['unit']==unit
        original=baseline[unit];variant=rows[0]
        pairs.append(dict(unit=unit,selection='failure_selected' if unit=='DS9-B03-D2' else 'first_block_pilot',
            baseline=original,variant=variant,
            error_change_m=variant['error_m']-original['error_m'] if variant['accepted'] and original['accepted'] else None))
    primary=[p for p in pairs if p['selection']=='first_block_pilot']
    pair_summary=dict(baseline=statistics([p['baseline'] for p in primary]),
                      constituent_starts=statistics([p['variant'] for p in primary]))
    blas=[load(HERE/'cold-blas-v1'/unit/'comparison.json') for unit in plan['blas_units']]
    assert complete['pair_units']==plan['pair_units'] and complete['blas_units']==plan['blas_units']
    result=dict(summary=summaries,continuation_comparisons=recovery,pair_pilot_summary=pair_summary,
        pair_comparisons=pairs,cold_blas_comparisons=blas,input_sha256=sources,summarizer_sha256=digest(__file__),
        qualification='Development evidence. Baseline is cold; recovery and constituent variants reuse sealed fitted states with historical work charged. Failure-selected pair is separate from the three metadata-selected pilots. Error quantiles condition on acceptance; threshold denominators retain all planned outcomes. No heldout, calibrated-uncertainty or randomized-speed claim.')
    with output.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(dict(summary=summaries,pair_pilot_summary=pair_summary,cold_blas=blas),indent=2),flush=True)


if __name__=='__main__':main()
