"""Audit every shuffled-control initialization fold, without claiming later stages ran."""
import json
import numpy as np
from benchmark import ROOT,PROTOCOL,digest,split_masks


def strict_abstention(receipt):
    if receipt['status']!='abstain_no_coherent_seed':return False
    if receipt['proposals'] or any(receipt['receiver_has_support']) or any(receipt['modes']):
        raise ValueError('Abstention contradicts persisted seed evidence')
    return True


def main():
    manifest=json.loads((ROOT/'validation-inputs/manifest.json').read_text());scans={};hashes={}
    for scan in 'AB':
        outcomes=[]
        for replicate in range(PROTOCOL['negative_controls']['replicates']):
            source=ROOT/'validation-inputs'/f'{scan}-control-{replicate:02d}.npz'
            expected=manifest['scans'][scan]['controls'][replicate]['sha256']
            if digest(source)!=expected:raise ValueError('Frozen control changed')
            with np.load(source) as a:
                times,groups,canonical=a['times_s'],a['group'],a['canonical_rows']
            test_union=[];folds=[]
            for fold in range(5):
                path=ROOT/'control-coherent-bootstrap'/f'replicate-{replicate:02d}'/f'fold-{fold}'/f'{scan}-checked.json'
                d=json.loads(path.read_text());hashes[str(path)]=digest(path)
                if (d['scan'],d['control'],d['fold'],d['source_sha256'])!=(scan,replicate,fold,expected):
                    raise ValueError('Control receipt lineage mismatch')
                train,test=split_masks(times,groups,fold)
                expected_train=canonical[train[canonical]]
                np.testing.assert_array_equal(expected_train,d['train_rows'])
                test_union.extend(map(int,canonical[test[canonical]]))
                folds.append(dict(fold=fold,abstains=strict_abstention(d),seed_proposals=len(d['proposals']),
                                  test_denominator=int(test[canonical].sum())))
            if sorted(test_union)!=sorted(map(int,canonical)):raise ValueError('Control test folds do not partition canonical rows')
            outcomes.append(dict(replicate=replicate,all_folds_abstain=all(f['abstains'] for f in folds),folds=folds))
        scans[scan]=dict(replicates=len(outcomes),folds=len(outcomes)*5,
            abstaining_folds=sum(f['abstains'] for r in outcomes for f in r['folds']),
            all_fold_abstaining_replicates=sum(r['all_folds_abstain'] for r in outcomes),outcomes=outcomes)
        print(scan,{k:v for k,v in scans[scan].items() if k!='outcomes'},flush=True)
    target=ROOT/'conditional-controls/all-fold-bootstrap-summary.json'
    with target.open('x') as stream:json.dump(dict(scope=__doc__,scans=scans,sources=hashes,
        limitations=['These are initialization discovery/selection controls; no nuisance fit or adaptive timing search is claimed after abstention.',
            'They show that the implemented seed-gated pipeline has no route to assignments on these inputs without adding a new fallback.',
            'They do not test false positives conditional on successful initialization, nor certify satellite identities or 90% defensible coverage.']),stream,indent=2)


if __name__=='__main__':main()
