"""Five-fold matched calibration pilot, with convergence failures explicit."""
import csv,json
from benchmark import ROOT,digest


def aggregate(results):
    if sorted(r['fold'] for r in results)!=list(range(5)):
        raise ValueError('Five distinct folds are required')
    arms={}
    for name in ('fitted-c','zero-c'):
        arms[name]=dict(heldout_log_likelihood=sum(r['arms'][name]['heldout_log_likelihood'] for r in results),
            heldout_gain_vs_clutter=sum(r['arms'][name]['heldout_gain_vs_clutter'] for r in results),
            converged_folds=sum(bool(r['arms'][name]['attempts'][-1]['success']) for r in results))
    return dict(test_rows=sum(r['test_rows'] for r in results),test_groups=sum(r['test_groups'] for r in results),
        arms=arms,fitted_c_gain_over_zero_c=arms['fitted-c']['heldout_log_likelihood']-arms['zero-c']['heldout_log_likelihood'])


def main():
    folder=ROOT/'training-calibration';rows=[];scans={};sources={}
    for scan in ('A','B'):
        results=[]
        for fold in range(5):
            path=folder/f'fold-{fold}'/f'{scan}.json';r=json.loads(path.read_text());results.append(r)
            sources[str(path)]=digest(path)
            row=dict(scan=scan,fold=fold,candidates=len(r['catalog_numbers']),test_rows=r['test_rows'])
            for name,short in [('fitted-c','fitted'),('zero-c','zero')]:
                arm=r['arms'][name];row[f'{short}_gain_vs_clutter']=arm['heldout_gain_vs_clutter']
                row[f'{short}_converged']=arm['attempts'][-1]['success']
                row[f'{short}_gradient_inf']=arm['attempts'][-1]['projected_nuisance_gradient_inf_norm']
            row['fitted_gain_over_zero']=r['arms']['fitted-c']['heldout_log_likelihood']-r['arms']['zero-c']['heldout_log_likelihood']
            rows.append(row)
        scans[scan]=aggregate(results)
    manifest=json.loads((ROOT/'frozen/manifest.json').read_text())
    for scan in scans:assert scans[scan]['test_rows']==manifest['scans'][scan]['distinct_peaks']
    result=dict(scope=__doc__,scans=scans,folds=rows,sources=sources,
        interpretation='Original matched four-stage budgets only; separate refined runs are not mixed into totals. Unconverged results remain provisional. Calibration likelihood is not decoder coverage or identity validation.')
    (folder/'summary.json').write_text(json.dumps(result,indent=2))
    with (folder/'summary.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
