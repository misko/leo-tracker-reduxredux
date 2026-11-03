"""Compare timing selectors on identical fold-0 evaluation observations."""
import argparse,csv,json
import numpy as np
from benchmark import ROOT,digest
from training_union import union_modes


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--exclusive',action='store_true');args=parser.parse_args()
    rows=[];sources={}
    for scan in ('A','B'):
        paths={name:ROOT/folder/'fold-0'/f'{scan}.json' for name,folder in
            [('tracklet-selected','heldout-decoding'),('joint-beam','independent-history'),('lane-history','independent-lane-history')]}
        if args.exclusive:paths['exclusive-history']=ROOT/'exclusive-history/fold-0'/f'{scan}.json'
        receipts={name:json.loads(p.read_text()) for name,p in paths.items()}
        sources.update({str(p):digest(p) for p in paths.values()})
        union_path=ROOT/'training-union/fold-0'/f'{scan}.json';baseline=json.loads(union_path.read_text())
        sources[str(union_path)]=digest(union_path)
        discoveries=[json.loads((ROOT/'training-discovery/fold-0'/arm/f'{scan}-proposals.json').read_text()) for arm in ('fitted-c','zero-c')]
        proposals={(m['catalog_number'],m['total_timing_s']) for m in union_modes(discoveries)}
        with np.load(ROOT/'frozen'/f'{scan}-observations.npz') as a:groups=a['group'].copy()
        test=receipts['tracklet-selected']['original_test_rows']
        for name,receipt in receipts.items():
            assert receipt['original_test_rows']==test
            for arm in ('fitted-c','zero-c'):
                if name=='tracklet-selected':
                    result=receipt['arms'][arm]['methods']['history'];chosen=baseline['arms'][arm]['chosen_modes']
                    predictive=baseline['arms'][arm]['heldout_gain_vs_clutter']
                else:
                    result=receipt['arms'][arm];chosen=result['chosen_modes'];predictive=result['heldout_gain_vs_clutter']
                    assert receipt['original_train_rows']==baseline['original_train_rows']
                    assert not set(receipt['original_train_rows'])&set(test)
                assert len(chosen)==len({m['catalog_number'] for m in chosen})
                assert all((m['catalog_number'],m['total_timing_s']) in proposals for m in chosen)
                assignments=result['assignments'];keys=[(r['row_index'],r['catalog_number']) for r in assignments]
                assert len(keys)==len({r for r,_ in keys})
                assert len(keys)==len({(int(groups[r]),n) for r,n in keys})
                assert all(r in set(test) for r,_ in keys)
                assert all(abs(r['residual_native_hz'])<=600 for r in assignments)
                original=receipts['tracklet-selected']['arms'][arm]['methods']['history']['assignments']
                before={(r['row_index'],r['catalog_number']):r['residual_native_hz'] for r in original}
                after={(r['row_index'],r['catalog_number']):r['residual_native_hz'] for r in assignments}
                common=before.keys()&after.keys();rms=lambda v:float(np.sqrt(np.mean(np.square(v)))) if v else None
                oldm={m['catalog_number']:m['total_timing_s'] for m in baseline['arms'][arm]['chosen_modes']}
                newm={m['catalog_number']:m['total_timing_s'] for m in chosen}
                rows.append(dict(scan=scan,arm=arm,selector=name,fold=0,catalogs=len(chosen),
                    changed_timings=sum(newm[n]!=oldm[n] for n in newm.keys()&oldm.keys()),
                    added_catalogs=len(newm.keys()-oldm.keys()),removed_catalogs=len(oldm.keys()-newm.keys()),
                    coherent_test_assigned=len(assignments),test_denominator=len(test),coverage=len(assignments)/len(test),
                    physical_rms_hz=result['coherent_native_rms_hz'],heldout_predictive_gain_vs_clutter=predictive,
                    same_peak_and_identity=len(common),matched_original_rms_hz=rms([before[k] for k in common]),
                    matched_new_rms_hz=rms([after[k] for k in common])))
    output=ROOT/('exclusive-history' if args.exclusive else 'independent-lane-history');result=dict(scope=__doc__,rows=rows,sources=sources,
        warning='One development fold only. Coherent decoding coverage is not identity-validated, false-positive-controlled coverage. Strict predictive score is separate from decoding. No change to main benchmark results.')
    (output/'comparison.json').write_text(json.dumps(result,indent=2))
    with (output/'comparison.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
