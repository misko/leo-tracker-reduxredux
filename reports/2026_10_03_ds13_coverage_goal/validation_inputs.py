"""Materialize group-safe blocked splits and complete-peak-set controls.

These inputs are not validation results. Discovery, calibration and decoding
must be rerun on each appropriate training/control input before scoring.
"""
import json
import numpy as np
from benchmark import ROOT,PROTOCOL,canonical_rows,digest,split_masks


def shuffled_peak_sets(arrays,rng):
    """Move complete probe peak sets between times within the same RX/channel.

    Output metadata follows the destination probe; measured frequencies and
    source-row lineage follow the donor. Group sizes may differ. No peak is
    lost, duplicated or shuffled independently of its within-probe companions.
    """
    groups=np.unique(arrays['group']);members={int(g):np.flatnonzero(arrays['group']==g) for g in groups}
    lanes={};donors=[];targets=[]
    for g,rows in members.items():
        for field in ('times_s','receiver','channel','rf_hz'):
            if len(np.unique(arrays[field][rows]))!=1:raise ValueError(f'Probe {g} has mixed {field}')
        key=(int(arrays['receiver'][rows[0]]),int(arrays['channel'][rows[0]]))
        lanes.setdefault(key,[]).append(g)
    for key,lane in sorted(lanes.items()):
        if len({float(arrays['rf_hz'][members[g][0]]) for g in lane})!=1:
            raise ValueError(f'RF changes within lane {key}; define a valid control before proceeding')
        for target,donor in zip(lane,rng.permutation(lane)):
            rows=members[int(donor)];donors.extend(rows);targets.extend([members[target][0]]*len(rows))
    donors=np.array(donors,int);targets=np.array(targets,int)
    result={field:arrays[field][targets] for field in ('times_s','group','receiver','channel','rf_hz')}
    result['measured_hz']=arrays['measured_hz'][donors]
    result['source_row']=donors;result['source_group']=arrays['group'][donors]
    result['canonical_rows'],result['representative']=canonical_rows(result['measured_hz'],result['group'])
    return result


def main():
    output=ROOT/'validation-inputs';output.mkdir(exist_ok=True)
    summary=dict(scope=__doc__,protocol_sha256=digest(ROOT/'frozen/protocol.json'),scans={})
    for scan_index,label in enumerate(('A','B')):
        source=ROOT/'frozen'/f'{label}-observations.npz'
        with np.load(source) as archive:a={k:archive[k] for k in archive.files}
        folds=[];masks={}
        for fold in range(PROTOCOL['cross_validation']['folds']):
            train,test=split_masks(a['times_s'],a['group'],fold)
            assert not set(a['group'][train])&set(a['group'][test])
            masks[f'train_{fold}']=train;masks[f'test_{fold}']=test
            folds.append(dict(fold=fold,train_distinct=int(train[a['canonical_rows']].sum()),
                test_distinct=int(test[a['canonical_rows']].sum()),
                embargo_distinct=int((~train&~test)[a['canonical_rows']].sum())))
        np.savez_compressed(output/f'{label}-folds.npz',**masks)
        controls=[]
        seeds=np.random.SeedSequence([PROTOCOL['negative_controls']['rng_seed'],scan_index]).spawn(20)
        for replicate,seed in enumerate(seeds):
            control=shuffled_peak_sets(a,np.random.default_rng(seed))
            assert len(control['canonical_rows'])==len(a['canonical_rows'])
            assert np.array_equal(np.sort(control['source_row']),np.arange(len(a['times_s'])))
            path=output/f'{label}-control-{replicate:02d}.npz';np.savez_compressed(path,**control)
            controls.append(dict(replicate=replicate,path=path.name,sha256=digest(path),
                unchanged_groups=int(len(np.unique(control['group'][control['group']==control['source_group']])))))
        summary['scans'][label]=dict(source_sha256=digest(source),folds=folds,controls=controls)
        print(label,'prepared 5 folds and 20 shuffled controls',flush=True)
    (output/'manifest.json').write_text(json.dumps(summary,indent=2))


if __name__=='__main__':main()
