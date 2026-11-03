"""Held-out decoding coverage and matched-point RF residual comparisons."""
import csv,json
import numpy as np
from benchmark import ROOT,digest


def matched_residuals(first,second):
    left={(r['row_index'],r['catalog_number']):r['residual_native_hz'] for r in first}
    right={(r['row_index'],r['catalog_number']):r['residual_native_hz'] for r in second}
    common=sorted(left.keys()&right.keys())
    return dict(points=len(common),fitted_rms_hz=float(np.sqrt(np.mean([left[k]**2 for k in common]))) if common else None,
        zero_rms_hz=float(np.sqrt(np.mean([right[k]**2 for k in common]))) if common else None)


def main():
    folder=ROOT/'heldout-decoding';rows=[];matched=[];sources={}
    for scan in ('A','B'):
        results=[]
        for fold in range(5):
            path=folder/f'fold-{fold}'/f'{scan}.json';results.append(json.loads(path.read_text()));sources[str(path)]=digest(path)
        with np.load(ROOT/'frozen'/f'{scan}-observations.npz') as a:canonical=a['canonical_rows'].tolist()
        tests=[r for d in results for r in d['original_test_rows']]
        assert sorted(tests)==sorted(canonical)
        for method in ('activity','history','tracklet'):
            arm_records={}
            for arm in ('fitted-c','zero-c'):
                values=[d['arms'][arm]['methods'][method] for d in results]
                records=[r for v in values for r in v['assignments']];arm_records[arm]=records
                assert len(records)==len({r['row_index'] for r in records})
                residual=np.array([r['residual_native_hz'] for r in records])
                rows.append(dict(scan=scan,method=method,arm=arm,denominator=len(canonical),
                    raw_assigned=sum(v['raw_test_assigned'] for v in values),coherent_assigned=len(records),
                    coherent_coverage=len(records)/len(canonical),native_rms_hz=float(np.sqrt(np.mean(residual**2))),
                    decoding_seconds_sum=sum(v['decoding_s'] for v in values)))
            matched.append(dict(scan=scan,method=method,**matched_residuals(arm_records['fitted-c'],arm_records['zero-c'])))
    result=dict(scope=__doc__,coverage=rows,matched_point_same_identity=matched,sources=sources,
        warning='Fixed training parameters; joint train/test decoding uses held-out observations. Not predictive likelihood, identity-validated coverage or false-positive-controlled coverage. Shared training tracklet selection may favor that family.')
    (folder/'summary.json').write_text(json.dumps(result,indent=2))
    for name,values in [('coverage',rows),('matched-residuals',matched)]:
        with (folder/f'{name}.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(values[0]));writer.writeheader();writer.writerows(values)
    print(json.dumps({k:v for k,v in result.items() if k!='sources'},indent=2))


if __name__=='__main__':main()
