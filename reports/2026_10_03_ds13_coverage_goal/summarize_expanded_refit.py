"""Five-fold untouched-block score and convergence audit of expanded-bank refits."""
import csv,json
import numpy as np
from benchmark import ROOT,digest
from summarize_training_union import validate_partition


def aggregate(records):
    return {arm:dict(folds=len(rr),converged=sum(r['converged'] for r in rr),
        improved_folds=sum(r['change_after_refit']>0 for r in rr),
        change_after_refit=sum(r['change_after_refit'] for r in rr),
        gain_vs_clutter=sum(r['gain_vs_clutter'] for r in rr))
        for arm in ('fitted-c','zero-c') for rr in [[r for r in records if r['arm']==arm]]}


def main():
    folder=ROOT/'expanded-training-refit';rows=[];sources={};summaries={}
    for scan in ('A','B'):
        results=[];scanrows=[]
        for fold in range(5):
            path=folder/f'fold-{fold}'/f'{scan}.json';r=json.loads(path.read_text());results.append(r);sources[str(path)]=digest(path)
            origin=ROOT/'training-union'/f'fold-{fold}'/f'{scan}.json';baseline=json.loads(origin.read_text())
            assert r['source_sha256']==digest(origin)
            assert r['original_test_rows']==baseline['original_test_rows'];assert r['original_train_rows']==baseline['original_train_rows']
            for arm,a in r['arms'].items():
                before=baseline['arms'][arm];expected=[m['catalog_number'] for m in before['chosen_modes']]
                assert a['catalog_numbers']==expected
                assert len(a['heldout_group_values'])==len(set(a['heldout_group_values']))
                assert np.isclose(sum(a['heldout_group_gain_vs_clutter']),a['heldout_gain_vs_clutter'],atol=1e-6,rtol=0)
                assert np.isclose(a['heldout_log_likelihood']-before['heldout_global_log_likelihood'],a['heldout_change_after_refit'],atol=1e-6,rtol=0)
                delta=np.array(a['parameters'])-np.array(before['parameters']);np.testing.assert_array_equal(delta[:2],np.zeros(2))
                indices=np.array([6+m['satellite_index'] for m in before['chosen_modes']],int)
                row=dict(scan=scan,fold=fold,arm=arm,converged=bool(a['attempts'][-1]['success']),
                    gradient_inf=a['attempts'][-1]['projected_nuisance_gradient_inf_norm'],attempts=len(a['attempts']),
                    change_after_refit=a['heldout_change_after_refit'],gain_vs_clutter=a['heldout_gain_vs_clutter'],
                    rx0_offset_change_hz=float(delta[2]),rx0_drift_change_hz_s=float(delta[3]),
                    rx1_offset_change_hz=float(delta[4]),rx1_drift_change_hz_s=float(delta[5]),
                    rf_change_hz_ghz=float(np.array(a['coefficient'])[0]-np.array(before['coefficient'])[0]),
                    timing_change_rms_s=float(np.sqrt(np.mean(delta[indices]**2))))
                rows.append(row);scanrows.append(row)
        with np.load(ROOT/'frozen'/f'{scan}-observations.npz') as a:validate_partition(results,a['canonical_rows'])
        summaries[scan]=aggregate(scanrows)
    with (folder/'comparison.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    (folder/'summary.json').write_text(json.dumps(dict(scans=summaries,records=rows,sources=sources,
        warning='Training-only calibration refit with fixed selected catalogs and roof. No rediscovery or assignment/coherence/identity revalidation after refit; no new coverage claim. Convergence failures remain explicit.'),indent=2))
    print(json.dumps(summaries,indent=2))


if __name__=='__main__':main()
