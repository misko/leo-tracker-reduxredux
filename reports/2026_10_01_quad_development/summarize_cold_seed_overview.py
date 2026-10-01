"""Combine completed cold start-count stages without pooling timing trials."""
import json
from pathlib import Path
import numpy as np
from screen_seed_prefix import sealed,digest

HERE=Path(__file__).resolve().parent


def main():
    output=HERE/'cold-seed-cross-dataset-overview-v1.json'
    if output.exists():raise FileExistsError(output)
    rows=[];checks={};inputs={}
    names=['cold-seed-limit-summary-v1.json']+[
        f'cross-dataset-cold-seed-{stage}-v1.json' for stage in ('single','pair','quad')]
    for name in names:
        path=HERE/name;data=sealed(path);inputs[str(path)]=digest(path)
        for key in ('sources','inputs'):
            for p,h in data[key].items():
                assert digest(p)==h,p
                inputs[p]=h
                if Path(p).name=='sources.json':
                    freeze=sealed(Path(p))
                    for mapping in ('source_sha256','inputs'):
                        for q,expected in freeze[mapping].items():
                            assert digest(q)==expected,q
                            inputs[q]=expected
        for row in data['rows']:
            rows.append(dict(row,measurement_batch='historical_DS9' if name==names[0] else 'cross_dataset_extension'))
        for comparison in data['comparisons']:
            assert comparison['unit'] not in checks
            checks[comparison['unit']]=comparison
    expected={f'{d}-B01-{s}' for d in ('DS9','DS10','DS11') for s in ('S1','D1','Q')}
    assert set(checks)==expected and len(rows)==18
    comparisons=[]
    for ds in ('DS9','DS10','DS11'):
        for suffix,size in (('S1',1),('D1',2),('Q',4)):
            unit=f'{ds}-B01-{suffix}'
            arms={r['seed_limit']:r for r in rows if r['unit']==unit}
            assert set(arms)=={1,3} and sum(r['unit']==unit for r in rows)==2
            valid=all(r['accepted'] for r in arms.values()) and checks[unit]['all_checks_pass']
            comparison=dict(unit=unit,size=size,checks=checks[unit],both_accepted_equivalent=valid,
                one=arms[1],three=arms[3])
            if valid:
                comparison.update(observed_wall_saving_s=arms[3]['wall_seconds']-arms[1]['wall_seconds'],
                    observed_wall_saving_fraction=1-arms[1]['wall_seconds']/arms[3]['wall_seconds'],
                    error_change_m=arms[1]['error_m']-arms[3]['error_m'])
            comparisons.append(comparison)
    result=dict(comparisons=comparisons,inputs=inputs,sources={str(Path(__file__).resolve()):digest(__file__)},
        qualification='Nine related first-block windows, one measurement per arm. DS9 historical and DS10/DS11 later extension; timings are not pooled randomized trials. All use exposed development observations and an unsurveyed reference. Process/fit failures and equivalence gates preserved.')
    with output.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,3,figsize=(12,7),constrained_layout=True)
    for column,ds in enumerate(('DS9','DS10','DS11')):
        selected=[r for r in comparisons if r['unit'].startswith(ds+'-')]
        for arm,label,offset in (('one','One start',-.18),('three','Three starts',.18)):
            axes[0,column].bar(np.arange(3)+offset,[r[arm]['wall_seconds'] for r in selected],.36,label=label)
            for j,r in enumerate(selected):
                if r[arm]['accepted']:axes[1,column].bar(j+offset,r[arm]['error_m'],.36,color='tab:blue' if arm=='one' else 'tab:orange')
                else:axes[1,column].text(j+offset,0,'failed',rotation=90,ha='center')
        axes[0,column].set_title(ds+(' (historical)' if ds=='DS9' else ''))
        axes[0,column].set_ylabel('Fresh inference wall time (s)');axes[0,column].legend(fontsize=8)
        axes[1,column].set_ylabel('Accepted reference error (m)')
        for ax in axes[:,column]:ax.set_xticks(range(3),['Single','Pair','Quad']);ax.grid(axis='y',alpha=.2)
    fig.suptitle('Cold start-count evidence: first block per dataset; uncontrolled host/cache conditions')
    fig.savefig(output.with_suffix('.png'),dpi=160)
    print(json.dumps(comparisons,indent=2))


if __name__=='__main__':main()
