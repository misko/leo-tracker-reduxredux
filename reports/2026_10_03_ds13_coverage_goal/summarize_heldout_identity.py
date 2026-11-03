"""Check identity-audit partitions before reporting five-fold totals."""
import json
import numpy as np
from benchmark import ROOT,digest


def checked_partition(item, expected_rows):
    names=('accepted_rows','ambiguous_rows','untested_rows')
    rows=[r for name in names for r in item[name]]
    if len(rows)!=len(set(rows)) or set(rows)!=set(expected_rows):
        raise ValueError('Identity audit must partition decoded rows exactly')
    return [len(item[name]) for name in names]


def main():
    summary={}
    for scan in 'AB':
        paths=[ROOT/'heldout-identity'/f'fold-{fold}'/f'{scan}.json' for fold in range(5)]
        results=[json.loads(p.read_text()) for p in paths]
        with np.load(ROOT/'frozen'/f'{scan}-observations.npz') as a:denominator=len(a['canonical_rows'])
        if sum(r['test_denominator'] for r in results)!=denominator:raise ValueError('Incomplete test denominator')
        arms={}
        for arm in ('fitted-c','zero-c'):
            methods={}
            for method in ('activity','history','tracklet'):
                total=np.zeros(3,int);seen=set()
                for fold,result in enumerate(results):
                    path=ROOT/'heldout-decoding'/f'fold-{fold}'/f'{scan}.json'
                    if result['source_sha256'][str(path)]!=digest(path):raise ValueError('Decoder changed')
                    decoding=json.loads(path.read_text())
                    expected=[r['row_index'] for r in decoding['arms'][arm]['methods'][method]['assignments']]
                    if seen.intersection(expected):raise ValueError('Test rows repeated across folds')
                    seen.update(expected);total+=checked_partition(result['arms'][arm][method],expected)
                methods[method]=dict(local_identity_pass=int(total[0]),locally_ambiguous=int(total[1]),
                    insufficient_test_only_support=int(total[2]),denominator=denominator,
                    local_pass_fraction=float(total[0]/denominator))
            arms[arm]=methods
        summary[scan]=dict(arms=arms,sources={str(p):digest(p) for p in paths})
        print(scan,json.dumps(arms),flush=True)
    summary['scope']='Local held-out-only identity challenge, not globally validated defensible coverage. Short held-out segments untested, not rejected.'
    with (ROOT/'heldout-identity/summary.json').open('x') as stream:json.dump(summary,stream,indent=2)


if __name__=='__main__':main()
