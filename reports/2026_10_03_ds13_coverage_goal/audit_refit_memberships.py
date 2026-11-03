"""Recompute physical residuals on identical old held-out assignments after refit.

This audits frozen memberships; it is not fresh decoding or identity validation.
"""
import csv,json,sys
import numpy as np
from benchmark import ROOT,OLD,SESSIONS,ALIAS_HZ,digest
from training_bootstrap import training_view


def main():
    sys.path.insert(0,str(OLD))
    from exhaustive_subset import load_expanded_scan,SharedPredictionPlan,rf_features,circular_residual
    folder=ROOT/'expanded-training-refit';rows=[];sources={}
    for scan in ('A','B'):
        data=load_expanded_scan(SESSIONS[scan]);pooled={}
        for fold in range(5):
            rp=folder/f'fold-{fold}'/f'{scan}.json';refit=json.loads(rp.read_text())
            dp=ROOT/'heldout-decoding'/f'fold-{fold}'/f'{scan}.json';decoded=json.loads(dp.read_text())
            up=ROOT/'training-union'/f'fold-{fold}'/f'{scan}.json';union=json.loads(up.read_text())
            for path in (rp,dp,up):sources[str(path)]=digest(path)
            assert refit['source_sha256']==digest(up);assert decoded['source_sha256']==digest(up)
            assert refit['original_test_rows']==decoded['original_test_rows']
            mask=np.zeros(len(data.times),bool);mask[refit['original_test_rows']]=True;t=training_view(data,mask)
            lookup={int(r):i for i,r in enumerate(t.original_rows)};_,features=rf_features(t.rf,t.receiver,False)
            for arm in ('fitted-c','zero-c'):
                a=refit['arms'][arm];modes=union['arms'][arm]['chosen_modes'];indices=np.array([m['satellite_index'] for m in modes],int)
                columns={m['catalog_number']:c for c,m in enumerate(modes)}
                pred,visible,_=SharedPredictionPlan(t,indices).predict(np.array(a['parameters']))
                pred=pred.reshape(len(t.times),len(indices))+(features@np.array(a['coefficient']))[:,None];visible=visible.reshape(pred.shape)
                residual=circular_residual(t.measured[:,None],pred,ALIAS_HZ)
                for method,old in decoded['arms'][arm]['methods'].items():
                    dst=pooled.setdefault((arm,method),dict(before=[],after=[],outside=0,invisible=0,ids=set()))
                    for q in old['assignments']:
                        row=q['row_index'];col=columns[q['catalog_number']];rr=lookup[row]
                        if row in dst['ids']:raise ValueError('Held-out row repeated across folds')
                        dst['ids'].add(row);dst['before'].append(q['residual_native_hz']);dst['after'].append(float(residual[rr,col]))
                        dst['outside']+=int(abs(residual[rr,col])>600);dst['invisible']+=int(not visible[rr,col])
        for (arm,method),a in pooled.items():
            rows.append(dict(scan=scan,arm=arm,method=method,identical_points=len(a['ids']),
                before_rms_hz=float(np.sqrt(np.mean(np.square(a['before'])))),after_rms_hz=float(np.sqrt(np.mean(np.square(a['after'])))),
                after_outside_600hz=a['outside'],after_invisible=a['invisible']))
    with (folder/'membership-residuals.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    (folder/'membership-audit.json').write_text(json.dumps(dict(scope=__doc__,rows=rows,sources=sources),indent=2))
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
