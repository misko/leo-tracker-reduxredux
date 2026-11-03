"""Aggregate untouched-fold prediction for training-only expanded selection."""
import csv,json
import numpy as np
from benchmark import ROOT,digest


def validate_partition(results,canonical_rows):
    if sorted(r['fold'] for r in results)!=list(range(5)):raise ValueError('Missing or repeated fold')
    rows=[i for r in results for i in r['original_test_rows']]
    if sorted(rows)!=sorted(map(int,canonical_rows)):raise ValueError('Held-out rows do not partition the frozen denominator')
    for r in results:
        if set(r['original_train_rows'])&set(r['original_test_rows']):raise ValueError('Training/test overlap')


def main():
    folder=ROOT/'training-union';scans={};records=[];sources={}
    for scan in ('A','B'):
        results=[]
        for fold in range(5):
            path=folder/f'fold-{fold}'/f'{scan}.json';r=json.loads(path.read_text());results.append(r)
            sources[str(path)]=digest(path)
            for arm,a in r['arms'].items():
                records.append(dict(scan=scan,fold=fold,arm=arm,union_catalogs=r['union_catalogs'],
                    selected_catalogs=a['selected_catalogs'],test_rows=len(r['original_test_rows']),
                    gain_vs_clutter=a['heldout_gain_vs_clutter'],gain_vs_bootstrap=a['heldout_gain_vs_bootstrap_bank']))
        with np.load(ROOT/'frozen'/f'{scan}-observations.npz') as frozen:validate_partition(results,frozen['canonical_rows'])
        scans[scan]={arm:dict(gain_vs_clutter=sum(r['arms'][arm]['heldout_gain_vs_clutter'] for r in results),
            gain_vs_bootstrap=sum(r['arms'][arm]['heldout_gain_vs_bootstrap_bank'] for r in results),
            positive_folds=sum(r['arms'][arm]['heldout_gain_vs_clutter']>0 for r in results)) for arm in ('fitted-c','zero-c')}
    result=dict(scope=__doc__,scans=scans,records=records,sources=sources,
        warning='Global likelihood, not three-decoder validation; no expanded nuisance refit in these totals. Baseline convergence warnings remain applicable. Not coverage or a negative-control pass.')
    (folder/'summary.json').write_text(json.dumps(result,indent=2))
    with (folder/'summary.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
    print(json.dumps(scans,indent=2))


if __name__=='__main__':main()
