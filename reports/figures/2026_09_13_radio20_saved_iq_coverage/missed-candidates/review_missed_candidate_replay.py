"""Independent refinement and moment checks for frozen-time candidate replay."""
import copy,hashlib,json
from pathlib import Path
import numpy as np
from tests.starlink_glrt.test_tracking_resolver import oracle
from tests.starlink_glrt.test_tracking_solver import moments
from tests.starlink_glrt.test_native_solver import dense_fit
from tools.review_glrt_cpu_startup import review_startup_carrier
from validate_native_admission import rotated

BASE=Path(__file__).parent;ROOT=BASE/'missed-candidate-replay-v1'
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
refs=np.fromfile(BASE/'direct-references.ci16',dtype='<i2').reshape(4,3300,4)
bases=[]
for r in refs.astype(float):
    ref=r[:,0]+1j*r[:,1];der=r[:,2]+1j*r[:,3]
    bases.append(np.column_stack((ref,-der,1j*np.pi*1000/2500000*(2*np.arange(3300)-3299)*ref)))


def check(case,rows):
    directory=ROOT/case['label'];iq=np.fromfile(directory/'iq.ci16',dtype='<i2').reshape(-1,2)
    seed=next(r for r in rows if r['kind']==1);resolved=next(r for r in rows if r['kind']==2)
    assert seed['first']==case['proposal']['epoch']+14
    assert seed['start']==seed['first']+8 and seed['fraction']==seed['first_repeat']==0
    assert seed['source_now']==len(iq)==447851 and seed['starts']==[8,3341,6675,10008]
    hypotheses=oracle(refs[0,:,:2],iq[seed['first']:seed['first']+13316],seed['starts'])
    np.testing.assert_allclose(resolved['hypotheses'],hypotheses,rtol=2e-12,atol=2e-8)
    best=max(hypotheses,key=lambda row:row[2])
    np.testing.assert_allclose([resolved[k] for k in ('best_shift','cfo_hz','coherence')],best,rtol=2e-12,atol=2e-8)
    past=[r for r in rows if r['kind']==3]
    for row in past:
        first=row['first'];assert 0<=first and first+3300<=len(iq)
        z=rotated(iq[first:first+3300],0,row['phase_step']);phase=row['reference_phase']
        assert list(moments(z,refs[phase].astype(np.int64)).words)==row['moments']
        correction,coherence,_=dense_fit(bases[phase],z)
        np.testing.assert_allclose(row['coherence'],coherence,rtol=2e-12,atol=2e-14)
        step=row['phase_step'];step=step if step<2**31 else step-2**32
        cfo=step*2500000/2**32+np.clip(correction[1],-.25,.25)*1000
        np.testing.assert_allclose(row['cfo_hz'],cfo,rtol=2e-12,atol=2e-8)
        rejection=(32 if np.any(abs(correction)>=.25) else 0)|(64 if coherence<.05 else 0)
        assert row['rejection']==rejection and row['accepted']==int(rejection==0)
    startup=review_startup_carrier(resolved['cfo_hz'],past)
    assert len(past)==rows[-1]['retained_past']
    return dict(label=case['label'],resolver_hypotheses=17,moment_dense_fits=len(past),
        accepted=sum(r['accepted'] for r in past),startup=startup,
        maximum_coherence=max(r['coherence'] for r in past),
        rejection_counts={str(k):sum(r['rejection']==k for r in past) for k in set(r['rejection'] for r in past)})


manifest=json.loads((ROOT/'result.json').read_text());results=[];mutations=0
for case in manifest['cases']:
    directory=ROOT/case['label'];path=Path(case['source_path'])
    assert digest(path)==case['source_sha256'] and digest(directory/'iq.ci16')==case['input_sha256']
    assert digest(directory/'stdout.jsonl')==case['journal_sha256']
    source=np.memmap(path,mode='r',dtype='<i2').reshape(-1,2)
    np.testing.assert_array_equal(np.fromfile(directory/'iq.ci16',dtype='<i2').reshape(-1,2),
        source[case['source_offset']:case['source_offset']+447851])
    rows=[json.loads(line) for line in (directory/'stdout.jsonl').read_text().splitlines()]
    results.append(check(case,rows))
    if case['label'] in ('candidate-0','positive','control'):
        for field in ('coherence','cfo_hz'):
            changed=copy.deepcopy(rows);next(r for r in changed if r['kind']==3)[field]+=.001
            try:check(case,changed)
            except AssertionError:mutations+=1
            else:raise AssertionError('mutated estimate accepted')
result=dict(status='pass',scope='independent_frozen_candidate_refinement_and_moments',cases=results,
    mutations_rejected=mutations,native_tracking_qualified=False,reviewer_sha256=digest(Path(__file__)))
with (ROOT/'independent-review.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps(result,indent=2))
