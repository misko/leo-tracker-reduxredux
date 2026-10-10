"""Posthoc cached-score check only; no models, fits or reference coordinates."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def read(path,expected):
    data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=expected:raise ValueError('changed receipt')
    return json.loads(data)


def main():
    import evaluation
    from leo.contracts.digests import canonical_digest
    plan=json.loads((HERE/'protocol.json').read_text())
    collection=evaluation.collect(plan,canonical_digest(plan),HERE/'results')
    cells={(c['label'],c['hypothesis'],c['mode'],c['arm']):c for c in collection['cells']}
    rows=[]
    for member in plan['members']:
        for arm in ('zero-c','fitted-c'):
            binding=member['hypotheses'][arm]
            full=read(ROOT/binding['raw_path'],binding['raw_sha256'])
            if full['status']!='qualified' or not full['audit']['qualified']:
                raise ValueError('full state is not qualified')
            for mode in ('train0','train1'):
                cell=cells[(member['label'],arm,mode,arm)]
                if cell['status']!='qualified' or not cell['audit']['qualified']:
                    raise ValueError('fixed state is not qualified')
                if cell['solver']['vector'][:2]!=full['solver']['vector'][:2]:
                    raise ValueError('geometry changed')
                fold=mode[-1];score=full['scores'][fold]
                if score['status']!='complete':raise ValueError('missing original subset score')
                candidate=score['nll']+full['audit']['prior_penalty']
                difference=cell['audit']['objective']-candidate
                raw_name=member['label']+'/'+arm+'--'+mode+'--'+arm+'.json'
                rows.append(dict(label=member['label'],arm=arm,mode=mode,
                    returned_training_objective=cell['audit']['objective'],
                    original_full_state_subset_nll=score['nll'],
                    original_full_state_prior=full['audit']['prior_penalty'],
                    available_state_training_objective=candidate,
                    returned_minus_available=difference,
                    known_better_available_state=difference>1e-6,
                    stationarity=cell['audit']['stationarity'],
                    full_receipt_path=binding['raw_path'],full_receipt_sha256=binding['raw_sha256'],
                    fixed_receipt_path=raw_name,fixed_receipt_sha256=collection['raw_sha256'][raw_name]))
    result=dict(scope='Posthoc cached diagnostic; no objective calls or reference coordinates',
                rows=rows,comparisons=len(rows),
                dominated=sum(r['known_better_available_state'] for r in rows))
    (HERE/'CACHED_OBJECTIVE_AUDIT.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(comparisons=result['comparisons'],dominated=result['dominated'],
        failures=[r for r in rows if r['known_better_available_state']])))


if __name__=='__main__':main()
