"""Training-only feasibility of whole-identity replacements raised by the test audit.

Post-hoc diagnostic, not a new held-out validation run. Preserve all assigned
rows, require one destination timing across RX/channels, and forbid duplicate
satellite/probe ownership. A failed whole-track merge does not settle local
identity ambiguity or rule out partial reassignments.
"""
import json,sys
import numpy as np
from benchmark import ROOT,OLD,SESSIONS,ALIAS_HZ,digest
from training_bootstrap import training_view
from training_union import union_modes


def collision_groups(source_rows, destination_rows, groups):
    source=np.asarray(source_rows,int);destination=np.asarray(destination_rows,int)
    return sorted(set(map(int,np.asarray(groups)[source])) & set(map(int,np.asarray(groups)[destination])))


def main():
    sys.path.insert(0,str(OLD))
    from exhaustive_subset import load_expanded_scan,SharedPredictionPlan,rf_features,circular_residual
    data=load_expanded_scan(SESSIONS['B']);results=[];hashes={}
    for fold in range(5):
        path=ROOT/'training-union'/f'fold-{fold}'/'B.json';receipt=json.loads(path.read_text());hashes[str(path)]=digest(path)
        sources=[ROOT/'training-discovery'/f'fold-{fold}'/arm/'B-proposals.json' for arm in ('fitted-c','zero-c')]
        discoveries=[json.loads(p.read_text()) for p in sources]
        for p in sources:
            if receipt['source_sha256'][str(p)]!=digest(p):raise ValueError('Training source mismatch')
            hashes[str(p)]=digest(p)
        modes=union_modes(discoveries);mask=np.zeros(len(data.times),bool);mask[receipt['original_train_rows']]=True
        d=training_view(data,mask)
        np.testing.assert_array_equal(d.original_rows,discoveries[0]['original_rows'])
        _,features=rf_features(d.rf,d.receiver,False)
        for ai,arm in enumerate(('fitted-c','zero-c')):
            fit=receipt['arms'][arm];params=np.array(fit['parameters']);coeff=np.array(fit['coefficient']);correction=features@coeff
            chosen={p['catalog_number']:p for p in fit['chosen_modes']}
            assignments=fit['training_assignments']
            for src,dst in ((48392,66231),(62738,69036),(61638,100381)):
                selected=[r for r in assignments if r['catalog_number'] in (src,dst)]
                left=[r['row_index'] for r in selected if r['catalog_number']==src]
                right=[r['row_index'] for r in selected if r['catalog_number']==dst]
                item=dict(fold=fold,arm=arm,source=src,destination=dst,source_rows=len(left),destination_rows=len(right))
                if not left:
                    results.append(dict(item,status='source_not_selected'));continue
                conflicts=collision_groups(left,right,d.group)
                item['colliding_probe_groups']=conflicts
                rows=np.array([r['row_index'] for r in selected]);common=discoveries[ai]['common_timing_s']
                own=-.5*sum((r['residual_native_hz']/200)**2 for r in selected)
                own-=.5*sum((chosen[n]['total_timing_s']-common)**2 for n in (src,dst) if n in chosen)
                alternatives=[]
                for mode in modes:
                    if mode['catalog_number']!=dst:continue
                    index=mode['satellite_index'];params[6+index]=mode['total_timing_s']
                    prediction,visible,_=SharedPredictionPlan(d,[index]).predict(params)
                    error=circular_residual(d.measured[rows],prediction[rows]+correction[rows],ALIAS_HZ)
                    score=-.5*np.sum((error/200)**2)-.5*(mode['total_timing_s']-common)**2
                    alternatives.append(dict(total_timing_s=mode['total_timing_s'],score_change=float(score-own),
                        rms_hz=float(np.sqrt(np.mean(error**2))),outside_600_hz=int(np.sum(np.abs(error)>600)),
                        invisible_rows=int(np.sum(~visible[rows]))))
                feasible=[m for m in alternatives if not m['outside_600_hz'] and not m['invisible_rows'] and not conflicts]
                best=max(alternatives,key=lambda m:m['score_change']) if alternatives else None
                best_feasible=max(feasible,key=lambda m:m['score_change']) if feasible else None
                item.update(status='feasible_whole_identity_replacement' if best_feasible else 'no_feasible_whole_identity_replacement',
                    modes_tested=len(alternatives),best_unconstrained=best,best_feasible=best_feasible,
                    training_original_rows=d.original_rows[rows].tolist())
                results.append(item)
                print(fold,arm,src,dst,'collisions',len(conflicts),'feasible',best_feasible,'best',best,flush=True)
    output=ROOT/'heldout-identity/whole-identity-replacements.json'
    with output.open('x') as stream:json.dump(dict(scope=__doc__,results=results,source_sha256=hashes,
        score='Gaussian native-Hz residual plus timing prior only. Not the full selector objective: no satellite/segment complexity rewards.',
        assignments_changed=False),stream,indent=2,allow_nan=False)


if __name__=='__main__':main()
